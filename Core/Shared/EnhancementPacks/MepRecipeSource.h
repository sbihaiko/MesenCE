#pragma once
#include "pch.h"
#include "Utilities/miniz.h"

//Split out of MepRecipeOps (200-line-per-file guardrail, memory
//L-ff73acd33912-000, ADR-0138 Clarification §35): the zip-backed source
//abstraction and MEP-recipe-v1 §7 primary-root discovery. MepRecipeOps.cpp
//is the only caller (not a standalone public API).

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
	bool Exists(const string& rel) const;
	bool Read(const string& rel, vector<uint8_t>& out) const;
	//Safe-normalized file paths under RootPrefix (directories excluded)
	vector<string> ListRelative() const;
	//Raw normalized entry names of the whole archive (RootPrefix NOT
	//applied) - what root-discovery's probes scan
	vector<string> RawEntries() const;
	void SetRootPrefix(const string& prefix) { _rootPrefix = prefix; }
	const string& GetRootPrefix() const { return _rootPrefix; }

private:
	bool LoadBytes(vector<uint8_t> bytes, string& error);
	void Close();

	mz_zip_archive _zip{};
	bool _loaded = false;
	vector<uint8_t> _bytes;
	unordered_map<string, string> _normalizedToOriginal; //normalized -> raw zip entry name
	string _rootPrefix;

	friend string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName);
};

//MEP-recipe-v1 §7: opens `src`'s pack root the same way mep_lint.py's
//open_primary does (root hits, then MepPack::FindFallbackSubfolder, then a
//single top-level nested zip, reloading `src` in place when that last
//resort wins) and returns the discovered prefix ("" at the container
//root). Never fails - an unmatched container defaults to the root prefix,
//same as the Python reference.
string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName);
