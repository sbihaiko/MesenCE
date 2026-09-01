#include "Common.h"
#include "Core/Shared/EnhancementPacks/MepContentId.h"
#include "Core/Shared/EnhancementPacks/MepRecipeInstaller.h"
#include "Utilities/StringUtilities.h"

//F6.4b - client-side MEP-recipe-v1 auto-install (ADR-0138 clarifications
//4/37/38). Sibling file to EmuApiWrapper.cpp (already at its 200-line
//per-file guardrail - see project AGENTS.md) rather than a new addition
//there; this is the only export in the file, so it stays well under the
//guardrail on its own.
//
//This export is a thin marshaling wrapper around the already-shipped F6.4a
//offline installer (MepRecipeInstaller::Install, Core/Shared/EnhancementPacks/
//MepRecipeInstaller.h) - no install/patch/rewrite logic is duplicated here.
//The catalog fetch, host-allowlist download and dep resolution that produce
//the paths passed in below are the UI-side network-facing slice (F6.4b's
//other tasks); this DLL boundary never touches the network itself.

//depPathsBlob: dep-id -> local-path map, encoded as newline-separated
//"depId\tlocalPath" rows (the same tab-separated-row-per-line convention
//MepPackManager::GetPackListText/GetMepPackList already use elsewhere in
//this DLL) rather than a char** array, for which this DLL has no existing
//marshaling precedent. A null/empty blob means no deps supplied.
static unordered_map<string, string> ParseMepRecipeDepPaths(const char* depPathsBlob)
{
	unordered_map<string, string> depPaths;
	if(!depPathsBlob || depPathsBlob[0] == 0) {
		return depPaths;
	}

	for(string& row : StringUtilities::Split(depPathsBlob, '\n')) {
		size_t tabPos = row.find('\t');
		if(tabPos == string::npos || tabPos == 0) {
			continue;
		}
		depPaths[row.substr(0, tabPos)] = row.substr(tabPos + 1);
	}
	return depPaths;
}

extern "C"
{
	//outResult: encoded as newline-separated rows - row 0 is "1"/"0" for
	//success/failure (redundant with the bool return value, kept for
	//callers that only read the buffer), row 1 is the error message (empty
	//on success), and any remaining rows are MepRecipeInstallResult::
	//Withheld entries (only present on a successful install where
	//policy.apply_patch_only_if_complete withheld part of the recipe,
	//MEP-recipe-v1 section 6).
	DllExport bool __stdcall InstallMepRecipe(const char* recipeJson, const char* primaryPath, const char* depPathsBlob, const char* romName, const char* outFolder, char* outResult, uint32_t maxResultLength)
	{
		unordered_map<string, string> depPaths = ParseMepRecipeDepPaths(depPathsBlob);

		MepRecipeInstallResult result;
		bool success = MepRecipeInstaller::Install(
			recipeJson ? recipeJson : "",
			primaryPath ? primaryPath : "",
			depPaths,
			romName ? romName : "",
			outFolder ? outFolder : "",
			result
		);

		string resultText = (success ? "1" : "0") + string("\n") + result.Error;
		for(string& withheld : result.Withheld) {
			resultText += "\n" + withheld;
		}
		StringUtilities::CopyToBuffer(resultText, outResult, maxResultLength);

		return success;
	}

	//ADR-0147: hex content_id of a real directory tree (MepContentId::
	//ComputeFolder), used by the UI to detect local edits to an installed mep/
	//pack by comparing against the baseline recorded at install time. Throws
	//no exception; an unreadable folder (or one that computes to "") returns
	//an empty buffer.
	DllExport void __stdcall GetMepContentId(const char* folder, char* outBuffer, uint32_t maxLength)
	{
		string result = MepContentId::ComputeFolder(folder ? folder : "");
		StringUtilities::CopyToBuffer(result, outBuffer, maxLength);
	}
}
