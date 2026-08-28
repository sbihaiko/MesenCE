#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeStamp.h"
#include "Utilities/FolderUtilities.h"
#include <ctime>

namespace
{
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
}

bool MepRecipeStamp::WriteInstallStamp(const string& recipeHash, const string& primarySha256,
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
