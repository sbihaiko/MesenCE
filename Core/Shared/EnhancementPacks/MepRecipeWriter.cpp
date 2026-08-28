#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeWriter.h"
#include "Utilities/JsonReader.h"
#include "Utilities/FolderUtilities.h"
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

namespace
{
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
}

bool MepRecipeWriter::WritePackJson(const JsonValue& pack, bool includePatches, const string& outFolder, string& error)
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
