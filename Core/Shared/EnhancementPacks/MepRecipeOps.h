#pragma once
#include "pch.h"
#include "Utilities/miniz.h"

class JsonValue;

//Everything MepRecipeInstaller.cpp needs to actually apply a parsed
//MEP-recipe-v1 recipe (ADR-0138 §4, Clarification §37) once every hash has
//verified: the read-only zip-backed source abstraction + §7 primary-root
//discovery, the shared op-execution context, and the four op runners
//themselves (§4). The pure path-safety / rewrite-paths (§4.4) helpers are
//internal to MepRecipeOps.cpp; the glob matcher (§4.2) stays public so the
//unit tests can pin its semantics directly. Not a standalone public API -
//MepRecipeInstaller.cpp is the only caller of everything declared here.

//A read-only view over one recipe artifact (always a zip - MEP-recipe-v1
//§3.2/§3.3, both "primary" and every dep are downloaded/user-supplied zip
//files). Calls into Utilities/miniz.h directly instead of the
//Utilities/ZipReader + ArchiveReader wrapper: ArchiveReader::GetReader also
//references SZReader (7z), which would drag the whole SevenZip/ sources
//into the lightweight core-unit-tests link for a format this interpreter
//never reads. Same underlying miniz calls ZipReader.cpp already uses, just
//without the ArchiveReader/SZReader indirection.
class MepRecipeSource
{
public:
	~MepRecipeSource();
	bool LoadFile(const string& path, string& error);
	bool LoadBytes(vector<uint8_t> bytes, string& error);
	bool Exists(const string& rel) const;
	//False when the entry is missing, cannot be inflated, or exceeds the
	//MepFileIo decompression caps (declared size checked before inflating)
	bool Read(const string& rel, vector<uint8_t>& out) const;
	//Safe-normalized file paths under RootPrefix (directories excluded)
	vector<string> ListRelative() const;
	//Raw normalized entry names of the whole archive (RootPrefix NOT
	//applied) - what root-discovery's probes scan; cached at load time
	const vector<string>& RawEntries() const { return _rawEntries; }
	bool HasRawEntry(const string& normalized) const { return _normalizedToOriginal.count(normalized) > 0; }

private:
	//Only §7 discovery may move the root
	friend string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName);

	void Close();
	void SetRootPrefix(const string& prefix) { _rootPrefix = prefix; }

	mz_zip_archive _zip{};
	bool _loaded = false;
	vector<uint8_t> _bytes;
	unordered_map<string, string> _normalizedToOriginal; //normalized -> raw zip entry name
	vector<string> _rawEntries; //the keys of _normalizedToOriginal, in archive order
	string _rootPrefix;
};

//MEP-recipe-v1 §7: opens `src`'s pack root the same way mep_lint.py's
//open_primary does (root hits, then MepPack::FindFallbackSubfolder, then a
//single top-level nested zip, reloading `src` in place when that last
//resort wins) and returns the discovered prefix ("" at the container
//root). Never fails - an unmatched container defaults to the root prefix,
//same as the Python reference.
string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName);

//MEP-recipe-v1 §4.2: '*' matches one path segment, '**' matches zero or
//more segments, '?' matches one character other than '/'. Iterative NFA
//simulation - O(pattern x name), no recursion, so a hostile pattern cannot
//blow the stack or go exponential.
bool GlobMatch(const string& pattern, const string& name);

//Execution context shared by the four op runners below, built once by
//MepRecipeInstaller per Install() call.
struct MepRecipeOpContext
{
	unordered_map<string, MepRecipeSource*> Sources; //source-id ("primary" + dep ids) -> source
	unordered_set<string> Missing; //dep ids withheld by policy (§6)
	//Output paths (or "dir/" prefixes) a skipped op would have produced -
	//the §6/§22 transitive-skip set consulted by rename/rewrite-paths
	unordered_set<string> Withheld;
	string OutFolder;
	bool IncludePatches = true;

	//True when `rel` is itself withheld, or sits under a withheld "dir/"
	//prefix (§6/§22 transitive closure)
	bool IsWithheld(const string& rel) const
	{
		if(Withheld.count(rel)) {
			return true;
		}
		for(const string& w : Withheld) {
			if(!w.empty() && w.back() == '/' && rel.compare(0, w.size(), w) == 0) {
				return true;
			}
		}
		return false;
	}
};

//Each returns false only on a structural/hard failure (source missing,
//rename dest collision, ...); `error` is set only in that case. A
//policy-driven skip (missing dep, patch suppression) returns true having
//updated `ctx` instead.
bool RunCopyOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error);
bool RunGlobOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error);
bool RunRenameOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error);
bool RunRewritePathsOp(const JsonValue& op, MepRecipeOpContext& ctx, string& error);
