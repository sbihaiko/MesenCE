#pragma once
#include "pch.h"

class JsonValue;
class MepRecipeSource;

//Split out of MepRecipeInstaller (200-line-per-file guardrail, memory
//L-ff73acd33912-000, ADR-0138 Clarification §35): sha256 verification
//(MEP-recipe-v1 §8) and the §6 apply_patch_only_if_complete policy
//decision - both purely about whether an install may proceed, before any
//op runs or any byte is written. Not a standalone public API -
//MepRecipeInstaller.cpp is the only caller.
namespace MepRecipeVerify
{
	//Verifies `path`'s sha256 against `expectedHex` (case-insensitive on
	//read, MEP-recipe-v1 §3.2/§3.3); fills `actualHexOut` (lowercase) on
	//success.
	bool VerifyArtifactHash(const string& path, const string& expectedHex, string& actualHexOut, string& error);

	//Verifies every dep the caller supplied a path for and opens it as a
	//MepRecipeSource; a dep with no entry in `depPaths` is recorded in
	//`missingIds` instead (§6 - resolved by ApplyPolicy below, not by
	//itself a hard failure).
	bool VerifyDeps(const JsonValue& sources, const unordered_map<string, string>& depPaths,
		unordered_map<string, MepRecipeSource>& depSources, unordered_map<string, string>& depHashes,
		unordered_set<string>& missingIds, unordered_map<string, bool>& userSupplied, string& error);

	//§6: a missing dep is tolerated (its ops withheld) only under
	//apply_patch_only_if_complete and only when it is itself `user_supplied`
	//(never forcibly downloaded); anything else is a hard failure.
	bool ApplyPolicy(const JsonValue& root, const unordered_set<string>& missingIds,
		const unordered_map<string, bool>& userSupplied, string& error);

	bool PrepareOutputFolder(const string& outFolder, string& error);
}
