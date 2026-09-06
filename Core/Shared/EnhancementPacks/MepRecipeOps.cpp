#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeOps.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Shared/EnhancementPacks/MepFileIo.h"
#include "Utilities/JsonReader.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/FolderUtilities.h"
#include <algorithm>
#include <filesystem>

namespace fs = std::filesystem;

//--- MepRecipeSource (zip-backed source) + §7 root discovery --------------

MepRecipeSource::~MepRecipeSource()
{
	Close();
}

void MepRecipeSource::Close()
{
	if(_loaded) {
		mz_zip_reader_end(&_zip);
	}
	_loaded = false;
	_normalizedToOriginal.clear();
	_rawEntries.clear();
}

bool MepRecipeSource::LoadFile(const string& path, string& error)
{
	vector<uint8_t> bytes;
	if(!MepFileIo::ReadWholeFile(path, bytes)) {
		error = "cannot open: " + path;
		return false;
	}
	return LoadBytes(std::move(bytes), error);
}

bool MepRecipeSource::LoadBytes(vector<uint8_t> bytes, string& error)
{
	Close();
	_bytes = std::move(bytes);
	memset(&_zip, 0, sizeof(mz_zip_archive));
	if(!mz_zip_reader_init_mem(&_zip, _bytes.data(), _bytes.size(), 0)) {
		error = "not a valid zip archive";
		return false;
	}
	_loaded = true;
	for(mz_uint i = 0, len = mz_zip_reader_get_num_files(&_zip); i < len; i++) {
		if(mz_zip_reader_is_file_a_directory(&_zip, i)) {
			continue;
		}
		mz_zip_archive_file_stat stat;
		if(!mz_zip_reader_file_stat(&_zip, i, &stat)) {
			continue;
		}
		//MEP-recipe-v1 §5: an entry that escapes (or normalizes to nothing)
		//is skipped and can never become a pack root or an op source
		string original = stat.m_filename;
		string normalized;
		if(!MepPack::NormalizeRelativePath(original, normalized) || normalized.empty()) {
			continue;
		}
		if(_normalizedToOriginal.emplace(normalized, original).second) {
			_rawEntries.push_back(normalized);
		}
	}
	return true;
}

bool MepRecipeSource::Exists(const string& rel) const
{
	return _normalizedToOriginal.count(_rootPrefix + rel) > 0;
}

bool MepRecipeSource::Read(const string& rel, vector<uint8_t>& out) const
{
	auto it = _normalizedToOriginal.find(_rootPrefix + rel);
	if(it == _normalizedToOriginal.end()) {
		return false;
	}
	mz_zip_archive* zip = const_cast<mz_zip_archive*>(&_zip);
	int index = mz_zip_reader_locate_file(zip, it->second.c_str(), nullptr, 0);
	mz_zip_archive_file_stat stat;
	if(index < 0 || !mz_zip_reader_file_stat(zip, (mz_uint)index, &stat)) {
		return false;
	}
	//Per-entry decompression cap (MepFileIo) from the declared size, before
	//inflating anything
	uint64_t total = 0;
	string capError;
	if(!MepFileIo::CheckDecompressionCaps(rel, stat.m_uncomp_size, total, capError)) {
		return false;
	}
	size_t size = 0;
	void* data = mz_zip_reader_extract_to_heap(zip, (mz_uint)index, &size, 0);
	if(!data) {
		return false;
	}
	out.assign((uint8_t*)data, (uint8_t*)data + size);
	mz_free(data);
	return true;
}

vector<string> MepRecipeSource::ListRelative() const
{
	vector<string> result;
	for(const string& name : _rawEntries) {
		if(name.compare(0, _rootPrefix.size(), _rootPrefix) != 0) {
			continue;
		}
		string rel = name.substr(_rootPrefix.size());
		if(!rel.empty()) {
			result.push_back(std::move(rel));
		}
	}
	return result;
}

namespace
{
	//MEP-recipe-v1 §7 root-hit probes (mep_lint.py's PROBES/AUDIO_ALT_PROBE, plus pack.json)
	bool HasRootHit(const MepRecipeSource& src)
	{
		static const char* kProbes[] = { "pack.json", "hires.txt", "textures/hires.txt",
			"audio/hires.txt", "synth/preset.cfg", "audio/fingerprints.json" };
		for(const char* probe : kProbes) {
			if(src.HasRawEntry(probe)) {
				return true;
			}
		}
		return false;
	}

	//find_top_level_nested_zip (mep_lint.py): exactly one root-level (no '/') ".zip" entry
	string FindTopLevelNestedZip(const vector<string>& entries)
	{
		string candidate;
		int count = 0;
		for(const string& name : entries) {
			if(name.find('/') == string::npos && StringUtilities::EndsWith(StringUtilities::ToLower(name), ".zip")) {
				candidate = name;
				count++;
			}
		}
		return count == 1 ? candidate : "";
	}

	//Re-runs the root-hit + fallback checks (shared by the direct pass and
	//the post-nested-zip retry below)
	bool TryDiscover(const MepRecipeSource& src, const string& romName, string& prefix)
	{
		if(HasRootHit(src)) {
			prefix = "";
			return true;
		}
		string fallback = MepPack::FindFallbackSubfolder(src.RawEntries(), romName);
		if(!fallback.empty()) {
			prefix = fallback + "/";
			return true;
		}
		return false;
	}
}

string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName)
{
	string prefix;
	if(TryDiscover(src, romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	string nested = FindTopLevelNestedZip(src.RawEntries());
	vector<uint8_t> bytes;
	string loadError;
	if(!nested.empty() && src.Read(nested, bytes) && src.LoadBytes(std::move(bytes), loadError)
		&& TryDiscover(src, romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	src.SetRootPrefix("");
	return "";
}

//--- path-safety + glob (§4.2) + rewrite-paths (§4.4) ----------------------

namespace
{
	//True when `rel` (already safe-normalized) is a patch destination that
	//policy.apply_patch_only_if_complete withholds (MEP-recipe-v1 §6):
	//under patches/ or ending in .ips/.bps.
	bool IsPatchDest(const string& rel)
	{
		string lower = StringUtilities::ToLower(rel);
		if(StringUtilities::StartsWith(lower, "patches/")) {
			return true;
		}
		if(StringUtilities::EndsWith(lower, ".ips")) {
			return true;
		}
		return StringUtilities::EndsWith(lower, ".bps");
	}

	//MEP-recipe-v1 §5: normalizes `raw` (MepPack::NormalizeRelativePath) and
	//additionally rejects the empty result - every path this interpreter
	//writes or reads MUST be non-empty once normalized.
	bool RequireSafeRel(const string& raw, string& out)
	{
		string normalized;
		if(!MepPack::NormalizeRelativePath(raw, normalized) || normalized.empty()) {
			return false;
		}
		out = normalized;
		return true;
	}

	enum class GlobTokenKind : uint8_t
	{
		Literal,
		Star, //zero or more chars other than '/'
		StarStar, //zero or more of anything
		StarStarSlash, //zero or more whole segments ("**/")
		Question //one char other than '/'
	};

	struct GlobToken
	{
		GlobTokenKind Kind;
		char Literal;
	};

	vector<GlobToken> TokenizeGlob(const string& pattern)
	{
		vector<GlobToken> tokens;
		for(size_t i = 0; i < pattern.size();) {
			char c = pattern[i];
			if(c == '*' && i + 1 < pattern.size() && pattern[i + 1] == '*') {
				if(i + 2 < pattern.size() && pattern[i + 2] == '/') {
					tokens.push_back({ GlobTokenKind::StarStarSlash, 0 });
					i += 3;
				} else {
					tokens.push_back({ GlobTokenKind::StarStar, 0 });
					i += 2;
				}
			} else if(c == '*') {
				tokens.push_back({ GlobTokenKind::Star, 0 });
				i++;
			} else if(c == '?') {
				tokens.push_back({ GlobTokenKind::Question, 0 });
				i++;
			} else {
				tokens.push_back({ GlobTokenKind::Literal, c });
				i++;
			}
		}
		return tokens;
	}

	//NFA state values: 0 = inactive, 1 = active at a segment boundary (a
	//"**/" may end here without consuming anything), 2 = active mid-segment
	//(a "**/" must still see a '/' before it can end).
	void CloseGlobStates(const vector<GlobToken>& tokens, vector<char>& states)
	{
		for(size_t i = 0; i < tokens.size(); i++) {
			if(!states[i]) {
				continue;
			}
			switch(tokens[i].Kind) {
				case GlobTokenKind::Star:
				case GlobTokenKind::StarStar:
					states[i + 1] = 1;
					break;
				case GlobTokenKind::StarStarSlash:
					if(states[i] == 1) {
						states[i + 1] = 1;
					}
					break;
				default:
					break;
			}
		}
	}
}

bool GlobMatch(const string& pattern, const string& name)
{
	vector<GlobToken> tokens = TokenizeGlob(pattern);
	vector<char> states(tokens.size() + 1, 0);
	vector<char> next(tokens.size() + 1, 0);
	states[0] = 1;
	CloseGlobStates(tokens, states);
	for(char c : name) {
		std::fill(next.begin(), next.end(), 0);
		bool any = false;
		for(size_t i = 0; i < tokens.size(); i++) {
			if(!states[i]) {
				continue;
			}
			switch(tokens[i].Kind) {
				case GlobTokenKind::Literal:
					if(c == tokens[i].Literal) {
						next[i + 1] = 1;
						any = true;
					}
					break;
				case GlobTokenKind::Question:
					if(c != '/') {
						next[i + 1] = 1;
						any = true;
					}
					break;
				case GlobTokenKind::Star:
					if(c != '/') {
						next[i] = 1;
						any = true;
					}
					break;
				case GlobTokenKind::StarStar:
					next[i] = 1;
					any = true;
					break;
				case GlobTokenKind::StarStarSlash:
					//A boundary state (1) must win over a mid-segment one (2)
					if(c == '/') {
						next[i] = 1;
					} else if(next[i] != 1) {
						next[i] = 2;
					}
					any = true;
					break;
			}
		}
		if(!any) {
			return false;
		}
		CloseGlobStates(tokens, next);
		std::swap(states, next);
	}
	return states[tokens.size()] != 0;
}

namespace
{
	bool ParseHiresLine(const string& stripped, string& tag, string& params)
	{
		string rest = stripped;
		if(!rest.empty() && rest[0] == '[') {
			size_t end = rest.find(']');
			if(end == string::npos) {
				return false;
			}
			rest = rest.substr(end + 1);
		}
		if(rest.empty() || rest[0] != '<') {
			return false;
		}
		size_t end = rest.find('>');
		if(end == string::npos) {
			return false;
		}
		tag = rest.substr(1, end - 1);
		params = rest.substr(end + 1);
		return true;
	}

	//Applies `prefix` to `value` once (idempotent: a value already under
	//the prefix is returned unchanged).
	string ApplyPrefixOnce(const string& value, const string& prefix)
	{
		if(value == prefix) {
			return value;
		}
		if(StringUtilities::StartsWith(value, prefix.c_str())) {
			return value;
		}
		return prefix + value;
	}

	string RewriteHiresParams(const string& tag, const string& rawParams, const string& prefix)
	{
		string params = rawParams;
		std::replace(params.begin(), params.end(), '\\', '/');
		if(tag == "img") {
			return ApplyPrefixOnce(params, prefix);
		}
		vector<string> tokens = StringUtilities::Split(params, ',');
		size_t idx = 0;
		if(tag == "bgm" || tag == "sfx") {
			idx = 2;
		}
		if(tokens.size() <= idx) {
			return params;
		}
		string token = StringUtilities::Trim(tokens[idx]);
		std::replace(token.begin(), token.end(), '\\', '/');
		tokens[idx] = ApplyPrefixOnce(token, prefix);
		string result;
		for(size_t i = 0; i < tokens.size(); i++) {
			result += (i ? "," : "") + tokens[i];
		}
		return result;
	}

	string RewriteHiresLine(const string& raw, const vector<string>& tags, const string& prefix)
	{
		string newline;
		string line = raw;
		if(!line.empty() && line.back() == '\n') {
			line.pop_back();
			newline = "\n";
			if(!line.empty() && line.back() == '\r') {
				line.pop_back();
				newline = "\r\n";
			}
		}
		string stripped = StringUtilities::Trim(line);
		string tag, params;
		bool isComment = !stripped.empty() && stripped[0] == '#';
		if(stripped.empty() || isComment || !ParseHiresLine(stripped, tag, params)
			|| std::find(tags.begin(), tags.end(), tag) == tags.end()) {
			return raw;
		}
		size_t tagEnd = stripped.find('>') + 1;
		return stripped.substr(0, tagEnd) + RewriteHiresParams(tag, params, prefix) + newline;
	}

	//MEP-recipe-v1 §4.4: rewrites the bgm/sfx/img/background/patch file-path
	//token of every matching tagged line of `text`; `tags` is the op's own
	//tags list (only those tags are rewritten). Returns the rewritten text.
	string RewriteHiresText(const string& text, const vector<string>& tags, const string& prefixIn)
	{
		string prefix = prefixIn;
		if(prefix.empty() || prefix.back() != '/') {
			prefix += '/';
		}
		string result;
		size_t pos = 0;
		while(pos < text.size()) {
			size_t next = text.find('\n', pos);
			size_t len = next == string::npos ? text.size() - pos : next - pos + 1;
			result += RewriteHiresLine(text.substr(pos, len), tags, prefix);
			pos += len;
		}
		return result;
	}

	//Every string entry of `parent`'s array member `key` (non-string entries
	//skipped); "" when the member is absent or not an array. Shared by every
	//op field that is a JSON array of strings (currently only rewrite-paths's
	//"tags").
	vector<string> CollectStringArray(const JsonValue& parent, const char* key)
	{
		vector<string> result;
		const JsonValue* arr = parent.Get(key);
		if(arr && arr->IsArray()) {
			for(const JsonValue& item : arr->GetArray()) {
				if(item.IsString()) {
					result.push_back(item.GetString());
				}
			}
		}
		return result;
	}
}

//--- the four op runners (§4) -----------------------------------------------

namespace
{
	bool SplitFrom(const string& value, string& sourceId, string& rest)
	{
		size_t pos = value.find(':');
		if(pos == string::npos) {
			return false;
		}
		sourceId = value.substr(0, pos);
		rest = value.substr(pos + 1);
		return !sourceId.empty() && !rest.empty();
	}
	bool WriteOutputFile(const string& outFolder, const string& rel, const vector<uint8_t>& data, string& error)
	{
		string dest = FolderUtilities::CombinePath(outFolder, rel);
		std::error_code ec;
		if(fs::exists(fs::u8path(dest), ec)) {
			error = "refusing to overwrite existing output path: " + rel;
			return false;
		}
		fs::create_directories(fs::u8path(dest).parent_path(), ec);
		ofstream out(dest, std::ios::out | std::ios::binary);
		if(!out) {
			error = "cannot write '" + rel + "'";
			return false;
		}
		out.write((const char*)data.data(), (std::streamsize)data.size());
		return true;
	}
	//Dedupes RunGlobOp's matches by basename and writes the surviving ones.
	bool WriteGlobMatches(const vector<string>& matches, MepRecipeSource& src,
		const string& destDir, MepRecipeOpContext& ctx, string& error)
	{
		unordered_map<string, string> seenBasenames;
		for(const string& match : matches) {
			size_t slash = match.find_last_of('/');
			string base = slash == string::npos ? match : match.substr(slash + 1);
			if(seenBasenames.count(base)) {
				error = "glob: basename collision '" + base + "' (" + seenBasenames[base] + " vs " + match + ")";
				return false;
			}
			seenBasenames[base] = match;
			string dest;
			if(!RequireSafeRel(destDir + "/" + base, dest)) {
				error = "glob: unsafe destination for '" + match + "'";
				return false;
			}
			if(!ctx.IncludePatches && IsPatchDest(dest)) {
				continue;
			}
			vector<uint8_t> data;
			if(!src.Read(match, data)) {
				error = "glob: cannot read matched file: " + match;
				return false;
			}
			if(!WriteOutputFile(ctx.OutFolder, dest, data, error)) {
				return false;
			}
		}
		return true;
	}
	//The actual filesystem rename for RunRenameOp, once every policy/withheld check passed.
	bool PerformRename(const string& outFolder, const string& srcRel, const string& destRel, string& error)
	{
		string srcPath = FolderUtilities::CombinePath(outFolder, srcRel);
		string destPath = FolderUtilities::CombinePath(outFolder, destRel);
		std::error_code ec;
		if(!fs::exists(fs::u8path(srcPath), ec)) {
			error = "rename: source does not exist: " + srcRel;
			return false;
		}
		if(fs::exists(fs::u8path(destPath), ec)) {
			error = "rename: dest already exists: " + destRel;
			return false;
		}
		fs::create_directories(fs::u8path(destPath).parent_path(), ec);
		fs::rename(fs::u8path(srcPath), fs::u8path(destPath), ec);
		if(ec) {
			error = "rename: " + ec.message();
			return false;
		}
		return true;
	}
}

bool RunCopyOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error)
{
	string sourceId, rest, dest;
	bool fromOk = SplitFrom(op.GetString("from"), sourceId, rest);
	bool toOk = RequireSafeRel(op.GetString("to"), dest);
	if(!fromOk || !toOk) {
		error = "copy: invalid 'from'/'to'";
		return false;
	}
	if(ctx.Missing.count(sourceId)) {
		ctx.Withheld.insert(dest);
		return true;
	}
	auto it = ctx.Sources.find(sourceId);
	string relPath;
	if(it == ctx.Sources.end() || !RequireSafeRel(rest, relPath) || !it->second->Exists(relPath)) {
		error = "copy: source file not found: " + rest;
		return false;
	}
	if(!ctx.IncludePatches && IsPatchDest(dest)) {
		return true;
	}
	vector<uint8_t> data;
	if(!it->second->Read(relPath, data)) {
		error = "copy: cannot read source file: " + rest;
		return false;
	}
	return WriteOutputFile(ctx.OutFolder, dest, data, error);
}

bool RunGlobOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error)
{
	string sourceId, pattern, destDir;
	bool fromOk = SplitFrom(op.GetString("from"), sourceId, pattern);
	//NormalizeRelativePath already drops the trailing '/' of "audio/"
	bool toOk = RequireSafeRel(op.GetString("to"), destDir);
	if(!fromOk || !toOk) {
		error = "glob: invalid 'from'/'to'";
		return false;
	}
	if(ctx.Missing.count(sourceId)) {
		ctx.Withheld.insert(destDir + "/");
		return true;
	}
	auto it = ctx.Sources.find(sourceId);
	if(it == ctx.Sources.end()) {
		error = "glob: unknown source-id '" + sourceId + "'";
		return false;
	}
	vector<string> matches;
	for(const string& name : it->second->ListRelative()) {
		if(GlobMatch(pattern, name)) {
			matches.push_back(name);
		}
	}
	if(matches.empty()) {
		error = "glob: matched no files: " + pattern;
		return false;
	}
	return WriteGlobMatches(matches, *it->second, destDir, ctx, error);
}

bool RunRenameOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error)
{
	string srcRel, destRel;
	bool fromOk = RequireSafeRel(op.GetString("from"), srcRel);
	bool toOk = RequireSafeRel(op.GetString("to"), destRel);
	if(!fromOk || !toOk) {
		error = "rename: invalid 'from'/'to'";
		return false;
	}
	if(!ctx.IncludePatches && (IsPatchDest(srcRel) || IsPatchDest(destRel))) {
		return true;
	}
	if(ctx.IsWithheld(srcRel)) {
		ctx.Withheld.insert(destRel);
		return true;
	}
	return PerformRename(ctx.OutFolder, srcRel, destRel, error);
}

bool RunRewritePathsOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error)
{
	string rel;
	if(!RequireSafeRel(op.GetString("file"), rel)) {
		error = "rewrite-paths: invalid 'file'";
		return false;
	}
	//MEP-recipe-v1 §4.4/§5: the prefix is a safe relative directory prefix -
	//an absolute or '..' prefix is a validation error (mep_recipe.py applies
	//the same _safe() check to prefix.rstrip("/"))
	string prefix;
	if(!RequireSafeRel(op.GetString("prefix"), prefix)) {
		error = "rewrite-paths: invalid 'prefix'";
		return false;
	}
	if(ctx.IsWithheld(rel)) {
		return true;
	}
	string path = FolderUtilities::CombinePath(ctx.OutFolder, rel);
	std::error_code ec;
	if(!fs::exists(fs::u8path(path), ec)) {
		error = "rewrite-paths: file does not exist: " + rel;
		return false;
	}
	vector<string> tags = CollectStringArray(op, "tags");
	string text;
	if(!MepFileIo::ReadWholeFile(path, text)) {
		error = "rewrite-paths: cannot read: " + rel;
		return false;
	}
	string rewritten = RewriteHiresText(text, tags, prefix);
	ofstream out(path, std::ios::out | std::ios::binary);
	out.write(rewritten.data(), (std::streamsize)rewritten.size());
	return true;
}
