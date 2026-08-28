#pragma once
#include "pch.h"

class JsonValue;

//MEP-recipe-v1 §8's pack.json output: byte-for-byte matching
//`scripts/mep_recipe.py apply`'s own json.dumps(indent=2) formatting - the
//golden-fixture parity test's bar. The F6.4-only `.mep-install.json` stamp
//(also §8, not part of the recipe vocabulary) is MepRecipeStamp.h/.cpp - a
//further split of the same 200-line-per-file guardrail (memory
//L-ff73acd33912-000, ADR-0138 Clarification §35). Not a standalone public
//API - MepRecipeInstaller.cpp is the only caller of both.
namespace MepRecipeWriter
{
	//Writes `outFolder`/pack.json. `pack` is the recipe's own "pack" JsonValue
	//(targets/patches are re-serialized verbatim, preserving their original
	//field order); pack.sections is used as-is when present and non-empty,
	//otherwise derived from the output tree (§3.4).
	bool WritePackJson(const JsonValue& pack, bool includePatches, const string& outFolder, string& error);
}
