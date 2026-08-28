#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeOps.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Utilities/JsonReader.h"
#include "Utilities/StringUtilities.h"
#include <algorithm>

bool IsPatchDest(const string& rel)
{
	string lower = StringUtilities::ToLower(rel);
	return StringUtilities::StartsWith(lower, "patches/") || StringUtilities::EndsWith(lower, ".ips") || StringUtilities::EndsWith(lower, ".bps");
}

bool RequireSafeRel(const string& raw, string& out)
{
	string normalized;
	if(!MepPack::NormalizeRelativePath(raw, normalized) || normalized.empty()) {
		return false;
	}
	out = normalized;
	return true;
}

namespace
{
	//--- glob (MEP-recipe-v1 §4.2) ---------------------------------------

	bool GlobMatchImpl(const char* pat, const char* name);

	//"**/" -> zero-or-more path segments (only stops right after a '/');
	//bare "**" -> zero-or-more of anything (stops at any position). Both
	//forms also allow the zero-length match (mirrors Python's optional
	//"(?:.*/)?" group vs. its unconstrained ".*" translation).
	bool MatchStarStar(const char* rest, const char* name, bool requireSlash)
	{
		if(GlobMatchImpl(rest, name)) {
			return true;
		}
		for(const char* p = name; *p; p++) {
			if((!requireSlash || *p == '/') && GlobMatchImpl(rest, p + 1)) {
				return true;
			}
		}
		return false;
	}

	bool GlobMatchImpl(const char* pat, const char* name)
	{
		if(pat[0] == '*' && pat[1] == '*' && pat[2] == '/') {
			return MatchStarStar(pat + 3, name, true);
		}
		if(pat[0] == '*' && pat[1] == '*') {
			return MatchStarStar(pat + 2, name, false);
		}
		if(pat[0] == '*') {
			if(GlobMatchImpl(pat + 1, name)) {
				return true;
			}
			return *name && *name != '/' && GlobMatchImpl(pat, name + 1);
		}
		if(pat[0] == '?') {
			return *name && *name != '/' && GlobMatchImpl(pat + 1, name + 1);
		}
		if(pat[0] == '\0') {
			return *name == '\0';
		}
		return *name == pat[0] && GlobMatchImpl(pat + 1, name + 1);
	}
}

bool GlobMatch(const string& pattern, const string& name)
{
	return GlobMatchImpl(pattern.c_str(), name.c_str());
}

namespace
{
	//--- rewrite-paths (MEP-recipe-v1 §4.4) ------------------------------

	bool ParseHiresLine(const string& stripped, string& tag, string& params)
	{
		string rest = stripped;
		if(!rest.empty() && rest[0] == '[') {
			size_t end = rest.find(']');
			if(end == string::npos) {
				return false;
			}
			rest = rest.substr(end + 1);
		}
		if(rest.empty() || rest[0] != '<') {
			return false;
		}
		size_t end = rest.find('>');
		if(end == string::npos) {
			return false;
		}
		tag = rest.substr(1, end - 1);
		params = rest.substr(end + 1);
		return true;
	}

	string RewriteHiresParams(const string& tag, const string& rawParams, const string& prefix)
	{
		string params = rawParams;
		std::replace(params.begin(), params.end(), '\\', '/');
		if(tag == "img") {
			return (params == prefix || StringUtilities::StartsWith(params, prefix.c_str())) ? params : prefix + params;
		}
		vector<string> tokens = StringUtilities::Split(params, ',');
		size_t idx = (tag == "bgm" || tag == "sfx") ? 2 : 0;
		if(tokens.size() <= idx) {
			return params;
		}
		string token = StringUtilities::Trim(tokens[idx]);
		std::replace(token.begin(), token.end(), '\\', '/');
		tokens[idx] = (token == prefix || StringUtilities::StartsWith(token, prefix.c_str())) ? token : prefix + token;
		string result;
		for(size_t i = 0; i < tokens.size(); i++) {
			result += (i ? "," : "") + tokens[i];
		}
		return result;
	}

	string RewriteHiresLine(const string& raw, const vector<string>& tags, const string& prefix)
	{
		string newline;
		string line = raw;
		if(!line.empty() && line.back() == '\n') {
			line.pop_back();
			newline = "\n";
			if(!line.empty() && line.back() == '\r') {
				line.pop_back();
				newline = "\r\n";
			}
		}
		string stripped = StringUtilities::Trim(line);
		string tag, params;
		bool isComment = !stripped.empty() && stripped[0] == '#';
		if(stripped.empty() || isComment || !ParseHiresLine(stripped, tag, params)
			|| std::find(tags.begin(), tags.end(), tag) == tags.end()) {
			return raw;
		}
		size_t tagEnd = stripped.find('>') + 1;
		return stripped.substr(0, tagEnd) + RewriteHiresParams(tag, params, prefix) + newline;
	}
}

string RewriteHiresText(const string& text, const vector<string>& tags, const string& prefixIn)
{
	string prefix = prefixIn;
	if(prefix.empty() || prefix.back() != '/') {
		prefix += '/';
	}
	string result;
	size_t pos = 0;
	while(pos < text.size()) {
		size_t next = text.find('\n', pos);
		size_t len = next == string::npos ? text.size() - pos : next - pos + 1;
		result += RewriteHiresLine(text.substr(pos, len), tags, prefix);
		pos += len;
	}
	return result;
}

vector<string> CollectStringArray(const JsonValue& parent, const char* key)
{
	vector<string> result;
	const JsonValue* arr = parent.Get(key);
	if(arr && arr->IsArray()) {
		for(const JsonValue& item : arr->GetArray()) {
			if(item.IsString()) {
				result.push_back(item.GetString());
			}
		}
	}
	return result;
}
