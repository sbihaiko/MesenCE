#pragma once
#include "pch.h"

//Offline, local-files-only MEP-recipe-v1 interpreter (ADR-0138 §4 +
//Clarification §37) - offline meaning no HTTP, no network, no libcurl:
//every source this class touches is a path to a file the caller already has on disk (a
//previously downloaded primary/dep artifact, or a path the user supplied
//by hand). Fetching those files, the catalog/MEI lookup and the
//"which dep is missing, please supply it" UI prompt are a separate,
//network-facing slice (F6.4b) - out of scope here by design, per the
//ADR-0138 §37 network-boundary split.
//
//Parses the recipe document (Utilities/JsonReader), verifies every
//provided artifact's sha256 before any op runs (MEP-recipe-v1 §8),
//applies policy.apply_patch_only_if_complete's transitive-skip semantics
//(§6) when a dependency is missing, delegates the four op implementations
//to MepRecipeOps/MepRecipeApply, and writes pack.json + the F6.4-only
//.mep-install.json (MepRecipeWriter/MepRecipeStamp) into the caller's
//output folder - normally MepPackManager::GetPacksFolder() + the ROM's
//convention name (ADR-0040), which this class does not own or compute
//itself (it takes the destination folder as a parameter, mirroring
//MepPack's "pure data, manager decides placement" split, ADR-0005).
class MepRecipeInstallResult
{
public:
	bool Success = false;
	//Set only on a hard failure (bad JSON, unsupported recipe version, a
	//sha256 mismatch, a structural op error); empty on success.
	string Error;
	//Output paths (or "dir/" prefixes) withheld by
	//policy.apply_patch_only_if_complete because a dependency was missing
	//(MEP-recipe-v1 §6) - empty when every dep was supplied.
	vector<string> Withheld;
};

class MepRecipeInstaller
{
public:
	//recipeJson: the recipe document text, already fetched by the caller.
	//primaryPath: local path to the primary artifact (sha256-verified here).
	//depPaths: dep-id -> local path, only for the deps the caller actually
	//  has; a dep declared in the recipe but absent from this map is
	//  treated as a missing `user_supplied` dependency (§6).
	//romName: optional ROM name for the primary's ADR-0120 name-anchored
	//  fallback discovery (MEP-recipe-v1 §7); may be empty.
	//outFolder: destination folder, must not already contain files.
	static bool Install(const string& recipeJson, const string& primaryPath,
		const unordered_map<string, string>& depPaths, const string& romName,
		const string& outFolder, MepRecipeInstallResult& result);
};
