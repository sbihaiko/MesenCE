#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeVerify.h"
#include "Shared/EnhancementPacks/MepRecipeSource.h"
#include "Utilities/JsonReader.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/sha256.h"
#include <filesystem>

namespace fs = std::filesystem;

namespace
{
	bool GetBoolField(const JsonValue* obj, const char* key, bool def)
	{
		const JsonValue* v = obj ? obj->Get(key) : nullptr;
		return (v && v->IsBool()) ? v->GetBool() : def;
	}
}

bool MepRecipeVerify::VerifyArtifactHash(const string& path, const string& expectedHex, string& actualHexOut, string& error)
{
	std::error_code ec;
	if(!fs::exists(fs::u8path(path), ec)) {
		error = "artifact does not exist: " + path;
		return false;
	}
	string expectedLower = StringUtilities::ToLower(expectedHex);
	actualHexOut = StringUtilities::ToLower(SHA256::GetHash(path));
	if(actualHexOut != expectedLower) {
		error = "sha256 mismatch for '" + path + "': expected " + expectedLower + ", got " + actualHexOut;
		return false;
	}
	return true;
}

bool MepRecipeVerify::VerifyDeps(const JsonValue& sources, const unordered_map<string, string>& depPaths,
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

bool MepRecipeVerify::ApplyPolicy(const JsonValue& root, const unordered_set<string>& missingIds,
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

bool MepRecipeVerify::PrepareOutputFolder(const string& outFolder, string& error)
{
	std::error_code ec;
	if(fs::exists(fs::u8path(outFolder), ec) && !fs::is_empty(fs::u8path(outFolder), ec)) {
		error = "output folder is not empty: " + outFolder;
		return false;
	}
	fs::create_directories(fs::u8path(outFolder), ec);
	return true;
}
