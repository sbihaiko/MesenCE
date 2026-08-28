#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeInstaller.h"
#include "Shared/EnhancementPacks/MepRecipeSource.h"
#include "Shared/EnhancementPacks/MepRecipeApply.h"
#include "Shared/EnhancementPacks/MepRecipeVerify.h"
#include "Shared/EnhancementPacks/MepRecipeWriter.h"
#include "Shared/EnhancementPacks/MepRecipeStamp.h"
#include "Shared/MessageManager.h"
#include "Utilities/JsonReader.h"
#include "Utilities/sha256.h"

namespace
{
	void Log(const string& message)
	{
		MessageManager::Log("[MEP] " + message);
	}

	//MEP-recipe-v1's own "Versioning" rule: clients MUST skip an unknown
	//`recipe` integer rather than guess (also used, at op granularity, for
	//an unrecognized `op` value - see RunOps below).
	bool CheckRecipeVersion(const JsonValue& root, string& error)
	{
		const JsonValue* version = root.Get("recipe");
		if(version && version->IsNumber() && version->GetNumber() == 1.0) {
			return true;
		}
		string got = version && version->IsNumber() ? std::to_string((long long)version->GetNumber()) : "<missing>";
		Log("recipe unsupported: recipe version " + got);
		error = "unsupported recipe version";
		return false;
	}

	//Runs every op in list order; an unknown `op` value is skipped (with a
	//log, mirroring the unknown-`recipe`-version rule above) rather than
	//aborting the whole install - a real hard failure (bad path, missing
	//rename source, ...) still aborts and returns false.
	bool RunOps(const JsonValue& root, MepRecipeOpContext& ctx, string& error)
	{
		const JsonValue* ops = root.Get("ops");
		if(!ops || !ops->IsArray()) {
			error = "'ops' must be an array";
			return false;
		}
		for(const JsonValue& op : ops->GetArray()) {
			string kind = op.GetString("op");
			bool ok = kind == "copy" ? RunCopyOp(op, ctx, error)
				: kind == "glob" ? RunGlobOp(op, ctx, error)
				: kind == "rename" ? RunRenameOp(op, ctx, error)
				: kind == "rewrite-paths" ? RunRewritePathsOp(op, ctx, error)
				: (Log("recipe unsupported: op '" + kind + "'"), true);
			if(!ok) {
				return false;
			}
		}
		return true;
	}

	//Everything Install() accumulates across its phases, so each phase stays
	//a short, single-purpose function (max_lines_per_function guardrail)
	//instead of one long procedure.
	struct InstallState
	{
		JsonValue Root;
		string PrimaryHash;
		MepRecipeSource PrimarySrc;
		unordered_map<string, MepRecipeSource> DepSources;
		unordered_map<string, string> DepHashes;
		unordered_set<string> MissingIds;
		unordered_map<string, bool> UserSupplied;
		MepRecipeOpContext Ctx;
	};

	//Phase 1: parse the document, reject an unsupported version, and
	//verify every provided artifact's sha256 (MEP-recipe-v1 §8) - nothing
	//on disk is touched yet, so a failure here writes nothing.
	bool ParseAndVerify(const string& recipeJson, const string& primaryPath,
		const unordered_map<string, string>& depPaths, InstallState& state, string& error)
	{
		JsonReader reader;
		if(!reader.Parse(recipeJson, state.Root) || !state.Root.IsObject() || !CheckRecipeVersion(state.Root, error)) {
			error = error.empty() ? "recipe is not valid JSON" : error;
			return false;
		}
		const JsonValue* sources = state.Root.Get("sources");
		const JsonValue* primary = sources ? sources->Get("primary") : nullptr;
		if(!primary || !MepRecipeVerify::VerifyArtifactHash(primaryPath, primary->GetString("sha256"), state.PrimaryHash, error)) {
			return false;
		}
		return MepRecipeVerify::VerifyDeps(*sources, depPaths, state.DepSources, state.DepHashes, state.MissingIds, state.UserSupplied, error)
			&& MepRecipeVerify::ApplyPolicy(state.Root, state.MissingIds, state.UserSupplied, error);
	}

	//Phase 2: every hash checked out - create the output folder, open the
	//primary source (discovering its pack root) and run the recipe's ops.
	bool BuildContextAndRun(InstallState& state, const string& primaryPath, const string& romName,
		const string& outFolder, string& error)
	{
		if(!MepRecipeVerify::PrepareOutputFolder(outFolder, error) || !state.PrimarySrc.LoadFile(primaryPath, error)) {
			return false;
		}
		DiscoverPrimaryRoot(state.PrimarySrc, romName);
		state.Ctx.OutFolder = outFolder;
		state.Ctx.IncludePatches = state.MissingIds.empty();
		state.Ctx.Missing = state.MissingIds;
		state.Ctx.Sources["primary"] = &state.PrimarySrc;
		for(auto& entry : state.DepSources) {
			state.Ctx.Sources[entry.first] = &entry.second;
		}
		return RunOps(state.Root, state.Ctx, error);
	}

	//Phase 3: pack.json (MEP-recipe-v1 §8) + the F6.4-only .mep-install.json.
	bool WriteOutputs(const InstallState& state, const string& recipeJson, const string& outFolder, string& error)
	{
		const JsonValue* pack = state.Root.Get("pack");
		if(!pack || !MepRecipeWriter::WritePackJson(*pack, state.Ctx.IncludePatches, outFolder, error)) {
			return false;
		}
		string recipeHash = SHA256::GetHash((uint8_t*)recipeJson.data(), recipeJson.size());
		return MepRecipeStamp::WriteInstallStamp(recipeHash, state.PrimaryHash, state.DepHashes, outFolder, error);
	}
}

bool MepRecipeInstaller::Install(const string& recipeJson, const string& primaryPath,
	const unordered_map<string, string>& depPaths, const string& romName,
	const string& outFolder, MepRecipeInstallResult& result)
{
	result = MepRecipeInstallResult();
	InstallState state;
	if(!ParseAndVerify(recipeJson, primaryPath, depPaths, state, result.Error)
		|| !BuildContextAndRun(state, primaryPath, romName, outFolder, result.Error)
		|| !WriteOutputs(state, recipeJson, outFolder, result.Error)) {
		return false;
	}
	result.Success = true;
	result.Withheld.assign(state.Ctx.Withheld.begin(), state.Ctx.Withheld.end());
	return true;
}
