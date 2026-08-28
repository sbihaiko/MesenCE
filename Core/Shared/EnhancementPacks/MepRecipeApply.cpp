#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeApply.h"
#include "Shared/EnhancementPacks/MepRecipeOps.h"
#include "Utilities/JsonReader.h"
#include "Utilities/FolderUtilities.h"
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

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
