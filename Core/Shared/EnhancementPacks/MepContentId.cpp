#include "Shared/EnhancementPacks/MepContentId.h"
#include "Utilities/JsonReader.h"
#include "Utilities/sha256.h"
#include <cstdint>
#include <cstdio>

//ADR-0139 path segments / basenames excluded from the tree hash - the
//artefacts it names as "outside the discovered root" (mirror of
//mep_content_id.py's _EXCLUDED_SEGMENTS/_EXCLUDED_BASENAMES).
namespace
{
	const char* kExcludedSegments[] = { "__MACOSX", "screenshots" };
	const char* kExcludedBasenames[] = { ".DS_Store" };

	string Basename(const string& path)
	{
		size_t slash = path.find_last_of('/');
		return slash == string::npos ? path : path.substr(slash + 1);
	}

	bool IsExcluded(const string& path)
	{
		size_t start = 0;
		while(true) {
			size_t end = path.find('/', start);
			string segment = path.substr(start, end == string::npos ? string::npos : end - start);
			for(const char* seg : kExcludedSegments) {
				if(segment == seg) {
					return true;
				}
			}
			if(end == string::npos) {
				break;
			}
			start = end + 1;
		}
		string base = Basename(path);
		for(const char* name : kExcludedBasenames) {
			if(base == name) {
				return true;
			}
		}
		return base.compare(0, 6, "README") == 0;
	}

	void AppendHexByte(string& out, uint8_t byte)
	{
		static const char* kHex = "0123456789abcdef";
		out.push_back(kHex[byte >> 4]);
		out.push_back(kHex[byte & 0xf]);
	}

	string HexDecode(const string& hex)
	{
		string raw;
		raw.reserve(hex.size() / 2);
		for(size_t i = 0; i + 1 < hex.size(); i += 2) {
			auto nibble = [](char c) -> uint8_t {
				if(c >= '0' && c <= '9') return (uint8_t)(c - '0');
				if(c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
				return (uint8_t)(c - 'A' + 10);
			};
			raw.push_back((char)((nibble(hex[i]) << 4) | nibble(hex[i + 1])));
		}
		return raw;
	}

	//Canonical JSON serialization that must be byte-identical to Python's
	//json.dumps(obj, sort_keys=True, separators=(",", ":")) with the default
	//ensure_ascii=True: compact separators, object keys sorted (byte-wise
	//UTF-8 order == code-point order for valid UTF-8), `"`/`\`/control chars
	//escaped with Python's short escapes where it has them, everything >= 0x80
	//as lowercase-hex \uXXXX (a surrogate pair for astral code points). The
	//`omitKey` parameter drops one object member (the pack.json 'version' key,
	//so a label-only bump is not a new revision). Numbers serialize as
	//integers when integral, else with %.17g - MEP-v1 pack.json carries no
	//numeric fields (version is a string), so real manifests stay in the
	//exact-match region.
	class CanonicalJsonWriter
	{
	public:
		string Write(const JsonValue& value, const char* omitKey = nullptr)
		{
			_buf.clear();
			_omitKey = omitKey;
			WriteValue(value);
			return _buf;
		}

	private:
		string _buf;
		const char* _omitKey = nullptr;

		void WriteValue(const JsonValue& value)
		{
			switch(value.GetType()) {
				case JsonValue::Type::Null:
					_buf += "null";
					break;
				case JsonValue::Type::Bool:
					_buf += value.GetBool() ? "true" : "false";
					break;
				case JsonValue::Type::Number: {
					double n = value.GetNumber();
					if(n == std::floor(n) && n >= -9007199254740992.0 && n <= 9007199254740992.0) {
						char buf[32];
						snprintf(buf, sizeof(buf), "%.0f", n);
						_buf += buf;
					} else {
						char buf[64];
						snprintf(buf, sizeof(buf), "%.17g", n);
						_buf += buf;
					}
					break;
				}
				case JsonValue::Type::String:
					WriteString(value.GetString());
					break;
				case JsonValue::Type::Array:
					_buf += '[';
					for(size_t i = 0; i < value.GetArray().size(); i++) {
						if(i) {
							_buf += ',';
						}
						WriteValue(value.GetArray()[i]);
					}
					_buf += ']';
					break;
				case JsonValue::Type::Object: {
					//Sort the members by key (Python sort_keys) - byte-wise
					//UTF-8 comparison matches code-point ordering
					vector<std::pair<string, const JsonValue*>> members;
					for(const auto& member : value.GetObject()) {
						if(_omitKey && member.first == _omitKey) {
							continue;
						}
						members.emplace_back(member.first, &member.second);
					}
					std::sort(members.begin(), members.end(),
						[](const auto& a, const auto& b) { return a.first < b.first; });
					_buf += '{';
					for(size_t i = 0; i < members.size(); i++) {
						if(i) {
							_buf += ',';
						}
						WriteString(members[i].first);
						_buf += ':';
						WriteValue(*members[i].second);
					}
					_buf += '}';
					break;
				}
			}
		}

		static void AppendUtf16Escape(string& out, uint32_t codeUnit)
		{
			out += "\\u";
			AppendHexByte(out, (uint8_t)(codeUnit >> 8));
			AppendHexByte(out, (uint8_t)(codeUnit & 0xff));
		}

		void WriteString(const string& s)
		{
			_buf += '"';
			size_t i = 0;
			while(i < s.size()) {
				uint8_t c = (uint8_t)s[i];
				if(c < 0x80) {
					switch(c) {
						case '"': _buf += "\\\""; break;
						case '\\': _buf += "\\\\"; break;
						case '\n': _buf += "\\n"; break;
						case '\r': _buf += "\\r"; break;
						case '\t': _buf += "\\t"; break;
						case '\b': _buf += "\\b"; break;
						case '\f': _buf += "\\f"; break;
						default:
							if(c < 0x20) {
								_buf += "\\u00";
								AppendHexByte(_buf, c);
							} else {
								_buf.push_back((char)c);
							}
							break;
					}
					i++;
				} else {
					//Decode one UTF-8 code point and emit it as \uXXXX
					//(ensure_ascii), a surrogate pair for astral code points
					uint32_t cp = 0;
					size_t extra = 0;
					if((c & 0xe0) == 0xc0) { cp = c & 0x1f; extra = 1; }
					else if((c & 0xf0) == 0xe0) { cp = c & 0x0f; extra = 2; }
					else if((c & 0xf8) == 0xf0) { cp = c & 0x07; extra = 3; }
					else { i++; continue; } //invalid byte: cannot round-trip, skip
					bool valid = (i + extra < s.size());
					if(valid) {
						for(size_t k = 1; k <= extra; k++) {
							uint8_t cont = (uint8_t)s[i + k];
							if((cont & 0xc0) != 0x80) {
								valid = false;
								break;
							}
							cp = (cp << 6) | (cont & 0x3f);
						}
					}
					if(!valid) {
						i++;
						continue;
					}
					if(cp <= 0xffff) {
						AppendUtf16Escape(_buf, cp);
					} else {
						uint32_t v = cp - 0x10000;
						AppendUtf16Escape(_buf, 0xd800 + (v >> 10));
						AppendUtf16Escape(_buf, 0xdc00 + (v & 0x3ff));
					}
					i += 1 + extra;
				}
			}
			_buf += '"';
		}
	};

	//pack.json payload for the tree hash: canonical JSON without 'version'. An
	//unparseable pack.json hashes as its raw bytes rather than failing the
	//whole content_id (mep_lint reports the JSON error separately) - a
	//malformed manifest is still a stable input, byte-faithful either way.
	string CanonicalPackJson(const vector<uint8_t>& data)
	{
		JsonValue root;
		JsonReader reader;
		string text(data.begin(), data.end());
		if(!reader.Parse(text, root) || !root.IsObject()) {
			return text;
		}
		CanonicalJsonWriter writer;
		return writer.Write(root, "version");
	}
}

string MepContentId::ComputeTree(const vector<Entry>& entries)
{
	vector<Entry> sorted = entries;
	std::sort(sorted.begin(), sorted.end(),
		[](const Entry& a, const Entry& b) { return a.Path < b.Path; });
	string manifest;
	for(const Entry& entry : sorted) {
		if(IsExcluded(entry.Path)) {
			continue;
		}
		if(entry.Path.size() >= 256) {
			return ""; //ADR-0139 path-length bound: hash undefined for this tree
		}
		string payload;
		if(entry.Path == "pack.json" || (entry.Path.size() > 9 && entry.Path.compare(entry.Path.size() - 9, 9, "/pack.json") == 0)) {
			payload = CanonicalPackJson(entry.Data);
		} else {
			payload.assign(entry.Data.begin(), entry.Data.end());
		}
		string digestHex = SHA256::GetHash((uint8_t*)payload.data(), payload.size());
		manifest += entry.Path;
		manifest.push_back((char)entry.Path.size());
		manifest += HexDecode(digestHex);
	}
	return SHA256::GetHash((uint8_t*)manifest.data(), manifest.size());
}

string MepContentId::ComputeRecipe(const string& primaryTreeHash, const string& recipeHash,
	const unordered_map<string, string>& depHashes)
{
	string lines = primaryTreeHash + "\n" + recipeHash;
	vector<std::pair<string, string>> deps(depHashes.begin(), depHashes.end());
	std::sort(deps.begin(), deps.end(),
		[](const auto& a, const auto& b) { return a.first < b.first; });
	for(const auto& dep : deps) {
		lines += "\n" + dep.second;
	}
	return SHA256::GetHash((uint8_t*)lines.data(), lines.size());
}
