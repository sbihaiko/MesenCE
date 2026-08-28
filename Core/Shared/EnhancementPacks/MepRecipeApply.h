#pragma once
#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeSource.h"

//Second half of the MepRecipeOps split (200-line-per-file guardrail,
//memory L-ff73acd33912-000, ADR-0138 Clarification §35): the four
//MEP-recipe-v1 op implementations (§4) and the execution context they
//share, built on top of MepRecipeSource (source reading) and MepRecipeOps
//(glob/rewrite/path-safety). Not a standalone public API -
//MepRecipeInstaller.cpp is the only caller.
class JsonValue;

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
