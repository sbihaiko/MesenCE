#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeInstaller.h"
#include "Shared/EnhancementPacks/MepRecipeOps.h"
#include "Shared/MessageManager.h"
#include "Utilities/JsonReader.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/sha256.h"
#include <filesystem>
#include <ctime>
#include <algorithm>

namespace fs = std::filesystem;

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

	//--- sha256 verification (MEP-recipe-v1 §8) + §6 policy decision --------

	bool GetBoolField(const JsonValue* obj, const char* key, bool def)
	{
		const JsonValue* v = obj ? obj->Get(key) : nullptr;
		return (v && v->IsBool()) ? v->GetBool() : def;
	}

	//Verifies `path`'s sha256 against `expectedHex` (case-insensitive on
	//read, MEP-recipe-v1 §3.2/§3.3); fills `actualHexOut` (lowercase) on
	//success.
	bool VerifyArtifactHash(const string& path, const string& expectedHex, string& actualHexOut, string& error)
	{
		std::error_code ec;
		if(!fs::exists(fs::u8path(path), ec)) {
			error = "artifact does not exist: " + path;
			return false;
		}
		string expectedLower = StringUtilities::ToLower(expectedHex);
		actualHexOut = StringUtilities::ToLower(SHA256::GetHash(path));
		if(actualHexOut.empty()) {
			error = "artifact could not be read: " + path;
			return false;
		}
		if(actualHexOut != expectedLower) {
			error = "sha256 mismatch for '" + path + "': expected " + expectedLower + ", got " + actualHexOut;
			return false;
		}
		return true;
	}

	//Verifies every dep the caller supplied a path for and opens it as a
	//MepRecipeSource; a dep with no entry in `depPaths` is recorded in
	//`missingIds` instead (§6 - resolved by ApplyPolicy below, not by
	//itself a hard failure).
	bool VerifyDeps(const JsonValue& sources, const unordered_map<string, string>& depPaths,
		unordered_map<string, MepRecipeSource>& depSources, unordered_map<string, string>& depHashes,
		unordered_set<string>& missingIds, unordered_map<string, bool>& userSupplied, string& error)
	{
		const JsonValue* deps = sources.Get("deps");
		if(!deps || !deps->IsArray()) {
			return true;
		}
		for(const JsonValue& dep : deps->GetArray()) {
			string id = dep.GetString("id");
			userSupplied[id] = GetBoolField(&dep, "user_supplied", true);
			auto pathIt = depPaths.find(id);
			if(pathIt == depPaths.end()) {
				missingIds.insert(id);
				continue;
			}
			string actual;
			if(!VerifyArtifactHash(pathIt->second, dep.GetString("sha256"), actual, error)) {
				return false;
			}
			depHashes[id] = actual;
			if(!depSources[id].LoadFile(pathIt->second, error)) {
				return false;
			}
		}
		return true;
	}

	//§6: a missing dep is tolerated (its ops withheld) only under
	//apply_patch_only_if_complete and only when it is itself `user_supplied`
	//(never forcibly downloaded); anything else is a hard failure.
	bool ApplyPolicy(const JsonValue& root, const unordered_set<string>& missingIds,
		const unordered_map<string, bool>& userSupplied, string& error)
	{
		if(missingIds.empty()) {
			return true;
		}
		if(!GetBoolField(root.Get("policy"), "apply_patch_only_if_complete", true)) {
			error = "missing dep(s), policy forbids a partial install";
			return false;
		}
		for(const string& id : missingIds) {
			auto it = userSupplied.find(id);
			if(it != userSupplied.end() && !it->second) {
				error = "missing required dep '" + id + "'";
				return false;
			}
		}
		return true;
	}

	bool PrepareOutputFolder(const string& outFolder, string& error)
	{
		std::error_code ec;
		if(fs::exists(fs::u8path(outFolder), ec) && !fs::is_empty(fs::u8path(outFolder), ec)) {
			error = "output folder is not empty: " + outFolder;
			return false;
		}
		fs::create_directories(fs::u8path(outFolder), ec);
		return true;
	}

	//--- pack.json (§8, byte-for-byte matching mep_recipe.py's json.dumps) --

	void WriteJsonString(std::ostringstream& out, const string& value)
	{
		out << '"';
		for(unsigned char c : value) {
			switch(c) {
				case '"': out << "\\\""; break;
				case '\\': out << "\\\\"; break;
				case '\n': out << "\\n"; break;
				case '\r': out << "\\r"; break;
				case '\t': out << "\\t"; break;
				default:
					if(c < 0x20) {
						char buf[8];
						snprintf(buf, sizeof(buf), "\\u%04x", c);
						out << buf;
					} else {
						out << (char)c;
					}
			}
		}
		out << '"';
	}

	//Re-serializes an already-parsed JsonValue with the exact json.dumps(x,
	//indent=2) layout mep_recipe.py produces (`indent` = the column the
	//enclosing key's value starts at); passes "targets"/"patches" through
	//pack.json byte-for-byte, preserving their original field order. Array
	//and object bodies are split into their own helpers below
	//(max_lines_per_function guardrail) - all three are mutually recursive,
	//hence the forward declaration.
	void WriteJsonValue(const JsonValue& v, int indent, std::ostringstream& out);

	void WriteJsonArray(const vector<JsonValue>& arr, int indent, std::ostringstream& out)
	{
		if(arr.empty()) {
			out << "[]";
			return;
		}
		string pad(indent, ' '), childPad(indent + 2, ' ');
		out << "[\n";
		for(size_t i = 0; i < arr.size(); i++) {
			out << childPad;
			WriteJsonValue(arr[i], indent + 2, out);
			out << (i + 1 < arr.size() ? ",\n" : "\n");
		}
		out << pad << "]";
	}

	void WriteJsonObject(const vector<std::pair<string, JsonValue>>& obj, int indent, std::ostringstream& out)
	{
		if(obj.empty()) {
			out << "{}";
			return;
		}
		string pad(indent, ' '), childPad(indent + 2, ' ');
		out << "{\n";
		for(size_t i = 0; i < obj.size(); i++) {
			out << childPad;
			WriteJsonString(out, obj[i].first);
			out << ": ";
			WriteJsonValue(obj[i].second, indent + 2, out);
			out << (i + 1 < obj.size() ? ",\n" : "\n");
		}
		out << pad << "}";
	}

	void WriteJsonValue(const JsonValue& v, int indent, std::ostringstream& out)
	{
		if(v.IsString()) {
			WriteJsonString(out, v.GetString());
		} else if(v.IsBool()) {
			out << (v.GetBool() ? "true" : "false");
		} else if(v.IsNumber()) {
			double n = v.GetNumber();
			(n == (long long)n) ? (out << (long long)n) : (out << n);
		} else if(v.IsNull()) {
			out << "null";
		} else if(v.IsArray()) {
			WriteJsonArray(v.GetArray(), indent, out);
		} else {
			WriteJsonObject(v.GetObject(), indent, out);
		}
	}

	//§3.4 fallback derivation (mirrors _derive_sections): root hires.txt ->
	//textures at path ""; otherwise the folder-form probes.
	vector<std::pair<string, string>> DeriveSections(const string& outFolder)
	{
		std::error_code ec;
		auto exists = [&](const char* rel) {
			return fs::exists(fs::u8path(FolderUtilities::CombinePath(outFolder, rel)), ec);
		};
		vector<std::pair<string, string>> result;
		bool rootHires = exists("hires.txt");
		if(rootHires) {
			result.push_back({ "textures", "" });
		}
		struct { const char* name; const char* probe; const char* altProbe; const char* path; } rows[] = {
			{ "textures", "textures/hires.txt", nullptr, "textures/" },
			{ "audio", "audio/hires.txt", "audio/fingerprints.json", "audio/" },
			{ "synth", "synth/preset.cfg", nullptr, "synth/preset.cfg" },
		};
		for(const auto& row : rows) {
			bool hit = exists(row.probe) || (row.altProbe && exists(row.altProbe));
			bool already = std::any_of(result.begin(), result.end(), [&](auto& p) { return p.first == row.name; });
			if(hit && !already) {
				result.push_back({ row.name, row.name == string("textures") && rootHires ? "" : row.path });
			}
		}
		return result;
	}

	void WriteSections(const JsonValue* declared, const string& outFolder, std::ostringstream& out)
	{
		if(declared && declared->IsObject() && !declared->GetObject().empty()) {
			WriteJsonValue(*declared, 2, out);
			return;
		}
		vector<std::pair<string, string>> derived = DeriveSections(outFolder);
		if(derived.empty()) {
			out << "{}";
			return;
		}
		out << "{\n";
		for(size_t i = 0; i < derived.size(); i++) {
			out << "    \"" << derived[i].first << "\": {\n      \"path\": ";
			WriteJsonString(out, derived[i].second);
			out << "\n    }" << (i + 1 < derived.size() ? ",\n" : "\n");
		}
		out << "  }";
	}

	//mep/name/version/license: always present, "license" defaulting to
	//NOASSERTION same as _write_pack_json's `pack.get("license") or ...`.
	void WriteMepHeader(const JsonValue& pack, std::ostringstream& out)
	{
		out << "{\n  \"mep\": ";
		WriteJsonString(out, pack.GetString("mep", "1.1.0"));
		out << ",\n  \"name\": ";
		WriteJsonString(out, pack.GetString("name"));
		out << ",\n  \"version\": ";
		WriteJsonString(out, pack.GetString("version"));
		out << ",\n  \"license\": ";
		WriteJsonString(out, pack.GetString("license", "NOASSERTION"));
	}

	//"targets" (always), then the two conditional keys that sit between it
	//and "sections" - "author" (only when declared) and "patches" (only
	//when includePatches and the recipe actually declares a non-empty one,
	//MEP-recipe-v1 §6).
	void WriteTargetsAuthorPatches(const JsonValue& pack, bool includePatches, std::ostringstream& out)
	{
		out << ",\n  \"targets\": ";
		const JsonValue* targets = pack.Get("targets");
		if(targets) {
			WriteJsonValue(*targets, 2, out);
		} else {
			out << "[]";
		}
		string author = pack.GetString("author");
		if(!author.empty()) {
			out << ",\n  \"author\": ";
			WriteJsonString(out, author);
		}
		const JsonValue* patches = pack.Get("patches");
		if(includePatches && patches && patches->IsArray() && !patches->GetArray().empty()) {
			out << ",\n  \"patches\": ";
			WriteJsonValue(*patches, 2, out);
		}
	}

	bool WritePackJson(const JsonValue& pack, bool includePatches, const string& outFolder, string& error)
	{
		std::ostringstream out;
		WriteMepHeader(pack, out);
		WriteTargetsAuthorPatches(pack, includePatches, out);
		out << ",\n  \"sections\": ";
		WriteSections(pack.Get("sections"), outFolder, out);
		out << "\n}\n";

		ofstream file(FolderUtilities::CombinePath(outFolder, "pack.json"), std::ios::out | std::ios::binary);
		if(!file) {
			error = "cannot write pack.json";
			return false;
		}
		file << out.str();
		return true;
	}

	//--- .mep-install.json (F6.4-only, not part of the recipe vocabulary) ---

	string CurrentIsoTimestamp()
	{
		std::time_t now = std::time(nullptr);
		std::tm utc{};
#ifdef _WIN32
		gmtime_s(&utc, &now);
#else
		gmtime_r(&now, &utc);
#endif
		char buf[32];
		std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &utc);
		return string(buf);
	}

	//Writes `outFolder`/.mep-install.json: recipe_hash is the sha256 of the
	//recipe document text itself; depSha256 is dep-id -> the sha256 actually
	//verified for it (only the deps that were supplied and verified, not
	//the missing ones).
	bool WriteInstallStamp(const string& recipeHash, const string& primarySha256,
		const unordered_map<string, string>& depSha256, const string& outFolder, string& error)
	{
		std::ostringstream out;
		out << "{\n  \"recipe_hash\": \"" << recipeHash << "\",\n";
		out << "  \"source\": { \"sha256\": \"" << primarySha256 << "\" },\n";
		out << "  \"deps\": {";
		size_t i = 0;
		for(const auto& dep : depSha256) {
			out << (i ? "," : "") << "\n    \"" << dep.first << "\": \"" << dep.second << "\"";
			i++;
		}
		out << (depSha256.empty() ? "" : "\n  ") << "},\n";
		out << "  \"installed_at\": \"" << CurrentIsoTimestamp() << "\"\n}\n";

		ofstream file(FolderUtilities::CombinePath(outFolder, ".mep-install.json"), std::ios::out | std::ios::binary);
		if(!file) {
			error = "cannot write .mep-install.json";
			return false;
		}
		file << out.str();
		return true;
	}

	//--- Install() phases -----------------------------------------------------

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
		if(!primary || !VerifyArtifactHash(primaryPath, primary->GetString("sha256"), state.PrimaryHash, error)) {
			return false;
		}
		return VerifyDeps(*sources, depPaths, state.DepSources, state.DepHashes, state.MissingIds, state.UserSupplied, error)
			&& ApplyPolicy(state.Root, state.MissingIds, state.UserSupplied, error);
	}

	//Phase 2: every hash checked out - create the output folder, open the
	//primary source (discovering its pack root) and run the recipe's ops.
	bool BuildContextAndRun(InstallState& state, const string& primaryPath, const string& romName,
		const string& outFolder, string& error)
	{
		if(!PrepareOutputFolder(outFolder, error) || !state.PrimarySrc.LoadFile(primaryPath, error)) {
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
		if(!pack || !WritePackJson(*pack, state.Ctx.IncludePatches, outFolder, error)) {
			return false;
		}
		string recipeHash = SHA256::GetHash((uint8_t*)recipeJson.data(), recipeJson.size());
		return WriteInstallStamp(recipeHash, state.PrimaryHash, state.DepHashes, outFolder, error);
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
