#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeOps.h"
#include "Shared/EnhancementPacks/MepPack.h"
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
}

bool MepRecipeSource::LoadFile(const string& path, string& error)
{
	ifstream in(path, std::ios::in | std::ios::binary);
	if(!in) {
		error = "cannot open: " + path;
		return false;
	}
	std::ostringstream ss;
	ss << in.rdbuf();
	string content = ss.str();
	return LoadBytes(vector<uint8_t>(content.begin(), content.end()), error);
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
		string original = stat.m_filename;
		string normalized = original;
		std::replace(normalized.begin(), normalized.end(), '\\', '/');
		_normalizedToOriginal[normalized] = original;
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
	size_t size = 0;
	void* data = mz_zip_reader_extract_file_to_heap(const_cast<mz_zip_archive*>(&_zip), it->second.c_str(), &size, 0);
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
	for(const auto& entry : _normalizedToOriginal) {
		const string& name = entry.first;
		if(name.compare(0, _rootPrefix.size(), _rootPrefix) != 0) {
			continue;
		}
		string rel = name.substr(_rootPrefix.size());
		if(!rel.empty()) {
			result.push_back(rel);
		}
	}
	return result;
}

vector<string> MepRecipeSource::RawEntries() const
{
	vector<string> result;
	for(const auto& entry : _normalizedToOriginal) {
		result.push_back(entry.first);
	}
	return result;
}

namespace
{
	bool HasEntry(const vector<string>& entries, const char* name)
	{
		return std::find(entries.begin(), entries.end(), string(name)) != entries.end();
	}

	//MEP-recipe-v1 §7 root-hit probes (mep_lint.py's PROBES/AUDIO_ALT_PROBE, plus pack.json)
	bool HasRootHit(const vector<string>& entries)
	{
		static const char* kProbes[] = { "pack.json", "hires.txt", "textures/hires.txt",
			"audio/hires.txt", "synth/preset.cfg", "audio/fingerprints.json" };
		for(const char* probe : kProbes) {
			if(HasEntry(entries, probe)) {
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
	bool TryDiscover(const vector<string>& entries, const string& romName, string& prefix)
	{
		if(HasRootHit(entries)) {
			prefix = "";
			return true;
		}
		string fallback = MepPack::FindFallbackSubfolder(entries, romName);
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
	if(TryDiscover(src.RawEntries(), romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	string nested = FindTopLevelNestedZip(src.RawEntries());
	vector<uint8_t> bytes;
	string loadError;
	if(!nested.empty() && src.Read(nested, bytes) && src.LoadBytes(bytes, loadError)
		&& TryDiscover(src.RawEntries(), romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	src.SetRootPrefix("");
	return "";
}

//--- path-safety + glob (§4.2) + rewrite-paths (§4.4) ----------------------

bool IsPatchDest(const string& rel)
{
	string lower = StringUtilities::ToLower(rel);
	return StringUtilities::StartsWith(lower, "patches/") || StringUtilities::EndsWith(lower, ".ips") || StringUtilities::EndsWith(lower, ".bps");
}

bool RequireSafeRel(const string& raw, string& out)
{
	string normalized;
	if(!MepPack::NormalizeRelativePath(raw, normalized) || normalized.empty()) {
		return false;
	}
	out = normalized;
	return true;
}

namespace
{
	bool GlobMatchImpl(const char* pat, const char* name);

	//"**/" -> zero-or-more path segments (only stops right after a '/');
	//bare "**" -> zero-or-more of anything (stops at any position). Both
	//forms also allow the zero-length match (mirrors Python's optional
	//"(?:.*/)?" group vs. its unconstrained ".*" translation).
	bool MatchStarStar(const char* rest, const char* name, bool requireSlash)
	{
		if(GlobMatchImpl(rest, name)) {
			return true;
		}
		for(const char* p = name; *p; p++) {
			if((!requireSlash || *p == '/') && GlobMatchImpl(rest, p + 1)) {
				return true;
			}
		}
		return false;
	}

	bool GlobMatchImpl(const char* pat, const char* name)
	{
		if(pat[0] == '*' && pat[1] == '*' && pat[2] == '/') {
			return MatchStarStar(pat + 3, name, true);
		}
		if(pat[0] == '*' && pat[1] == '*') {
			return MatchStarStar(pat + 2, name, false);
		}
		if(pat[0] == '*') {
			if(GlobMatchImpl(pat + 1, name)) {
				return true;
			}
			return *name && *name != '/' && GlobMatchImpl(pat, name + 1);
		}
		if(pat[0] == '?') {
			return *name && *name != '/' && GlobMatchImpl(pat + 1, name + 1);
		}
		if(pat[0] == '\0') {
			return *name == '\0';
		}
		return *name == pat[0] && GlobMatchImpl(pat + 1, name + 1);
	}
}

bool GlobMatch(const string& pattern, const string& name)
{
	return GlobMatchImpl(pattern.c_str(), name.c_str());
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

	string RewriteHiresParams(const string& tag, const string& rawParams, const string& prefix)
	{
		string params = rawParams;
		std::replace(params.begin(), params.end(), '\\', '/');
		if(tag == "img") {
			return (params == prefix || StringUtilities::StartsWith(params, prefix.c_str())) ? params : prefix + params;
		}
		vector<string> tokens = StringUtilities::Split(params, ',');
		size_t idx = (tag == "bgm" || tag == "sfx") ? 2 : 0;
		if(tokens.size() <= idx) {
			return params;
		}
		string token = StringUtilities::Trim(tokens[idx]);
		std::replace(token.begin(), token.end(), '\\', '/');
		tokens[idx] = (token == prefix || StringUtilities::StartsWith(token, prefix.c_str())) ? token : prefix + token;
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
}

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
	string RstripSlash(const string& value)
	{
		string result = value;
		while(result.size() > 1 && result.back() == '/') {
			result.pop_back();
		}
		return result;
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
			string dest = destDir + "/" + base;
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
	if(!SplitFrom(op.GetString("from"), sourceId, rest) || !RequireSafeRel(op.GetString("to"), dest)) {
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
	if(!SplitFrom(op.GetString("from"), sourceId, pattern) || !RequireSafeRel(RstripSlash(op.GetString("to")), destDir)) {
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
	if(!RequireSafeRel(op.GetString("from"), srcRel) || !RequireSafeRel(op.GetString("to"), destRel)) {
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
	string prefix = op.GetString("prefix");
	std::replace(prefix.begin(), prefix.end(), '\\', '/');
	ifstream in(path, std::ios::in | std::ios::binary);
	std::ostringstream ss;
	ss << in.rdbuf();
	string rewritten = RewriteHiresText(ss.str(), tags, prefix);
	ofstream out(path, std::ios::out | std::ios::binary);
	out.write(rewritten.data(), (std::streamsize)rewritten.size());
	return true;
}
