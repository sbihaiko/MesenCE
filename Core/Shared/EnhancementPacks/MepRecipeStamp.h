#pragma once
#include "pch.h"

//Split out of MepRecipeWriter (200-line-per-file guardrail, memory
//L-ff73acd33912-000, ADR-0138 Clarification §35): the F6.4-only
//`.mep-install.json` stamp - not part of the MEP-recipe-v1 vocabulary
//(spec §8), so it carries no json.dumps byte-for-byte parity requirement
//unlike MepRecipeWriter::WritePackJson. Not a standalone public API -
//MepRecipeInstaller.cpp is the only caller.
namespace MepRecipeStamp
{
	//Writes `outFolder`/.mep-install.json: recipe_hash is the sha256 of the
	//recipe document text itself; depSha256 is dep-id -> the sha256 actually
	//verified for it (only the deps that were supplied and verified, not
	//the missing ones).
	bool WriteInstallStamp(const string& recipeHash, const string& primarySha256,
		const unordered_map<string, string>& depSha256, const string& outFolder, string& error);
}
