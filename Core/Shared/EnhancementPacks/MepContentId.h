#pragma once
#include "pch.h"

//ADR-0139 `content_id` (P.1): canonical hash of the resolved pack tree, and
//the recipe composite when a recipe exists. Two implementations must agree on
//every value: scripts/mep_content_id.py (normative, drives CI mep-meta) and
//this Core module (MepPackManager for local containers, MepRecipeInstaller at
//install time), both checked against the shared parity fixture under
//docs/specs/golden/mep-content-id.json.
//
//Tree form: content_id = hex SHA-256 over a canonical manifest of the
//resolved pack root's files: entries sorted by byte-wise UTF-8 path relative
//to the root ('/' separators); per entry the path bytes, one byte = the path
//length (paths must be < 256 bytes), then the 32-byte SHA-256 of the file
//bytes. Entries whose path contains a `__MACOSX` or `screenshots` segment, or
//whose basename is `.DS_Store` or starts with `README`, are excluded.
//`pack.json` is hashed as canonical JSON (sorted keys, compact separators,
//Python json.dumps escaping) with its `version` key removed, so a label-only
//bump is not a new revision; every other file is hashed byte-for-byte.
//
//Recipe form: content_id = hex SHA-256 of `primaryTreeHash + "\n" +
//recipeHash` plus one "\n"-joined line per dep digest sorted by dep id
//(declared digests - CI needs no user_supplied bytes; the client computes the
//same function at install time from the primary bytes and stores it in
//.mep-install.json, never re-derived from the installed output tree).
class MepContentId
{
public:
	struct Entry
	{
		string Path; // '/' separators, relative to the discovered root
		vector<uint8_t> Data;
	};

	//Hex tree content_id over `entries`; "" when a path is >= 256 bytes (the
	//ADR-0139 path-length bound - the hash is undefined then, and callers
	//treat "" as "not computed").
	static string ComputeTree(const vector<Entry>& entries);

	//Hex recipe composite from the primary tree hash + recipe doc hash +
	//declared dep digests (dep-id -> hex sha256).
	static string ComputeRecipe(const string& primaryTreeHash, const string& recipeHash,
		const unordered_map<string, string>& depHashes);

	//Hex tree content_id over a real directory tree: enumerates folder
	//recursively (relative '/' paths, byte-wise UTF-8), dropping the host's own
	//install/host metadata (.mep-install.json / .bootstrap) so the baseline is
	//stable against reinstalls, and returns ComputeTree(entries). "" when the
	//folder cannot be read or computes to "". Used (ADR-0147) to detect local
	//edits to an installed mep/ pack by comparing against the baseline recorded
	//at install time.
	static string ComputeFolder(const string& folder);
};
