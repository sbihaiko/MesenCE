#include "pch.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Utilities/JsonReader.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/FolderUtilities.h"

namespace
{
	constexpr const char* kSectionNames[kMepSectionCount] = { "textures", "audio", "synth", "border" };
	//Fixed layout of the folder convention (ADR-0049, ADR-0149); textures/audio/border are
	//folders holding content (hires.txt, border.png), synth is the preset file itself
	constexpr const char* kConventionPaths[kMepSectionCount] = { "textures", "audio", "synth/preset.cfg", "border" };
	constexpr const char* kConventionProbe[kMepSectionCount] = { "textures/hires.txt", "audio/hires.txt", "synth/preset.cfg", "border/border.png" };
	//Leaf names of kConventionProbe (+ ADR-0047's audio/fingerprints.json
	//alt) - what MepPack::FindFallbackSubfolder looks for directly under a
	//ROM-named subfolder (ADR-0120)
	constexpr const char* kFallbackProbeBasenames[3] = { "hires.txt", "preset.cfg", "fingerprints.json" };
	constexpr const char* kKnownSystems[] = { "nes", "gb", "gbc", "sms", "gg", "sg1000", "coleco", "snes" };
	constexpr int kSupportedMajor = 1;

	bool IsHexUpperOrLower(const string& text, size_t expectedLength)
	{
		if(text.size() != expectedLength) {
			return false;
		}
		for(char c : text) {
			bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
			if(!ok) {
				return false;
			}
		}
		return true;
	}

	bool RequireString(const JsonValue& root, const char* key, string& out, string& error)
	{
		const JsonValue* value = root.Get(key);
		if(!value || !value->IsString() || value->GetString().empty()) {
			error = string("missing or invalid required field '") + key + "'";
			return false;
		}
		out = value->GetString();
		return true;
	}

	//Section paths may legitimately be empty (= the pack root, MEP-v1 §3.2;
	//the MEP recipe installer writes `"path": ""` for a section at the root),
	//so the generic RequireString - which rejects empty strings - is the wrong
	//validator here. Presence and type are still required.
	bool RequireSectionPath(const JsonValue& root, string& out, string& error)
	{
		const JsonValue* value = root.Get("path");
		if(!value || !value->IsString()) {
			error = string("missing or invalid required field 'path'");
			return false;
		}
		out = value->GetString();
		return true;
	}

	bool IsFallbackProbeBasename(const string& basename)
	{
		string lower = StringUtilities::ToLower(basename);
		for(const char* probe : kFallbackProbeBasenames) {
			if(lower == probe) {
				return true;
			}
		}
		return false;
	}

	//Rightmost segment (excluding the basename itself) equal to romName,
	//case-insensitive; -1 when no segment matches (ADR-0120)
	int FindRomNameAnchor(const vector<string>& segments, const string& lowerRomName)
	{
		for(int i = (int)segments.size() - 2; i >= 0; i--) {
			if(StringUtilities::ToLower(segments[i]) == lowerRomName) {
				return i;
			}
		}
		return -1;
	}

	string JoinSegments(const vector<string>& segments, int lastIndex)
	{
		string joined;
		for(int i = 0; i <= lastIndex; i++) {
			if(i > 0) {
				joined += '/';
			}
			joined += segments[i];
		}
		return joined;
	}
}

const char* MepPack::GetSectionName(MepSectionType type)
{
	return kSectionNames[(int)type];
}

const char* MepPack::GetConventionPath(MepSectionType type)
{
	return kConventionPaths[(int)type];
}

bool MepPack::DetectConventionLayout(const string& humanPrefix)
{
	bool any = false;
	//ADR-0147: MesenCE may root the sibling's human layer at mep/ (a sibling
	//of auto/, not a child of it). A non-empty humanPrefix shifts the human
	//probe and the section Path; the machine (auto/) layer is unchanged.
	string layerRoot = humanPrefix.empty() ? "" : (humanPrefix + "/");
	for(int i = 0; i < kMepSectionCount; i++) {
		MepSection& section = Sections[i];
		string humanProbe = FolderUtilities::CombinePath(RootFolder, layerRoot + kConventionProbe[i]);
		string autoProbe = FolderUtilities::CombinePath(FolderUtilities::CombinePath(RootFolder, AutoFolderName), kConventionProbe[i]);
		bool human = (bool)ifstream(humanProbe);
		bool automatic = (bool)ifstream(autoProbe);
		if(i == (int)MepSectionType::Audio) {
			//audio/ may hold fingerprints.json (ADR-0047) instead of a hires.txt
			human = human || (bool)ifstream(FolderUtilities::CombinePath(FolderUtilities::CombinePath(RootFolder, layerRoot + kConventionPaths[i]), "fingerprints.json"));
			automatic = automatic || (bool)ifstream(FolderUtilities::CombinePath(FolderUtilities::CombinePath(FolderUtilities::CombinePath(RootFolder, AutoFolderName), kConventionPaths[i]), "fingerprints.json"));
		}
		if(human) {
			section.HasHuman = true;
			section.Path = humanPrefix.empty() ? kConventionPaths[i] : (layerRoot + kConventionPaths[i]);
		}
		if(automatic) {
			section.AutoPath = string(AutoFolderName) + "/" + kConventionPaths[i];
		}
		if(human || automatic) {
			section.Present = true;
			any = true;
		}
	}

	//ADR-0121: a bare hires.txt directly at RootFolder (no textures/ wrapper
	//at all) is the pre-MEP, pre-ADR-0049 "classic Mesen HD pack" layout -
	//still loadable today by the emulator's separate, older HdPacks/<rom>/
	//loader at that exact shape (see MepPackManager::StartBootstrapIfNeeded's
	//own check of that legacy path), but until now never recognized as a
	//textures section by MEP's *own* convention detection. That silently
	//broke two paths that otherwise already work: a sibling folder
	//(ADR-0049) or a zip/folder container named exactly like the ROM
	//(ADR-0040) holding nothing but a loose hires.txt. Mirrors
	//scripts/mep_lint.py's discover_sections() root-level branch
	//(`sections.setdefault("textures", "")`) - "setdefault" here too: never
	//overrides a textures/ layer the loop above already found.
	MepSection& textures = Sections[(int)MepSectionType::Textures];
	if(!textures.Present) {
		string rootHires = FolderUtilities::CombinePath(RootFolder, layerRoot + "hires.txt");
		if((bool)ifstream(rootHires)) {
			textures.Present = true;
			textures.HasHuman = true;
			textures.Path = humanPrefix.empty() ? "" : humanPrefix;
			any = true;
		}
	}

	//Border section fallback: bare border.png directly at RootFolder
	MepSection& border = Sections[(int)MepSectionType::Border];
	if(!border.Present) {
		string rootBorder = FolderUtilities::CombinePath(RootFolder, layerRoot + "border.png");
		if((bool)ifstream(rootBorder)) {
			border.Present = true;
			border.HasHuman = true;
			border.Path = humanPrefix.empty() ? "" : humanPrefix;
			any = true;
		}
	}

	return any;
}

bool MepPack::IsValidSemver(const string& text)
{
	//MAJOR.MINOR.PATCH, digits only (pre-release/build suffixes are not
	//needed by the spec's own examples and would complicate major detection)
	int part = 0;
	int digits = 0;
	for(char c : text) {
		if(c >= '0' && c <= '9') {
			digits++;
		} else if(c == '.') {
			if(digits == 0) {
				return false;
			}
			part++;
			digits = 0;
			if(part > 2) {
				return false;
			}
		} else {
			return false;
		}
	}
	return part == 2 && digits > 0;
}

bool MepPack::IsKnownSystem(const string& system)
{
	for(const char* known : kKnownSystems) {
		if(system == known) {
			return true;
		}
	}
	return false;
}

bool MepPack::NormalizeRelativePath(const string& path, string& normalized)
{
	normalized.clear();

	string work = path;
	std::replace(work.begin(), work.end(), '\\', '/');

	//Absolute paths, drive letters and UNC-ish prefixes escape the root
	if(!work.empty() && work[0] == '/') {
		return false;
	}
	if(work.find(':') != string::npos) {
		return false;
	}
	for(char c : work) {
		if((uint8_t)c < 0x20) {
			return false;
		}
	}

	vector<string> parts;
	for(string& part : StringUtilities::Split(work, '/')) {
		if(part.empty() || part == ".") {
			continue;
		}
		if(part == "..") {
			//Even "a/../b" is refused: keep the rule simple and auditable
			return false;
		}
		parts.push_back(part);
	}

	for(size_t i = 0; i < parts.size(); i++) {
		if(i > 0) {
			normalized += '/';
		}
		normalized += parts[i];
	}
	return true;
}

string MepPack::FindFallbackSubfolder(const vector<string>& normalizedEntries, const string& romName)
{
	if(romName.empty() || normalizedEntries.size() > (size_t)kMepFallbackMaxEntries) {
		//Fail-closed: an empty ROM name or an oversized entry list is
		//refused outright rather than partially scanned (ADR-0120)
		return "";
	}

	string lowerRomName = StringUtilities::ToLower(romName);
	string candidate; //first accepted prefix; prefixes are never empty once found
	bool ambiguous = false;
	for(const string& normalized : normalizedEntries) {
		vector<string> segments = StringUtilities::Split(normalized, '/');
		if((int)segments.size() < 2 || (int)segments.size() > kMepFallbackMaxDepth || !IsFallbackProbeBasename(segments.back())) {
			continue;
		}
		int anchor = FindRomNameAnchor(segments, lowerRomName);
		if(anchor < 0) {
			continue;
		}
		string prefix = JoinSegments(segments, anchor);
		if(candidate.empty()) {
			candidate = prefix;
		} else if(candidate != prefix) {
			ambiguous = true;
		}
	}
	return ambiguous ? "" : candidate;
}

bool MepPack::Parse(const string& json, MepPack& out, string& error)
{
	out = MepPack();

	JsonReader reader;
	JsonValue root;
	if(!reader.Parse(json, root)) {
		error = "pack.json is not valid JSON: " + reader.GetError();
		return false;
	}
	if(!root.IsObject()) {
		error = "pack.json root must be an object";
		return false;
	}

	if(!RequireString(root, "mep", out.SpecVersion, error)) {
		return false;
	}
	if(!IsValidSemver(out.SpecVersion)) {
		error = "'mep' is not a semver version: " + out.SpecVersion;
		return false;
	}
	int major = std::stoi(out.SpecVersion.substr(0, out.SpecVersion.find('.')));
	if(major != kSupportedMajor) {
		error = "unsupported MEP major version " + std::to_string(major) + " (host supports " + std::to_string(kSupportedMajor) + ".x)";
		return false;
	}

	if(!RequireString(root, "name", out.Name, error) || !RequireString(root, "version", out.Version, error)) {
		return false;
	}
	//MEP-v1 §3.1: `license` is SHOULD (optional since v1.1) — absent reads as "not declared",
	//the same placeholder MepPackManager uses for convention-only sibling folders.
	out.License = root.GetString("license", "unspecified");
	if(out.License.empty()) {
		out.License = "unspecified";
	}
	if(!IsValidSemver(out.Version)) {
		error = "'version' is not a semver version: " + out.Version;
		return false;
	}
	out.Author = root.GetString("author");

	//targets (MUST, >= 1)
	const JsonValue* targets = root.Get("targets");
	if(!targets || !targets->IsArray() || targets->GetArray().empty()) {
		error = "'targets' must be a non-empty array";
		return false;
	}
	for(const JsonValue& entry : targets->GetArray()) {
		if(!entry.IsObject()) {
			error = "'targets' entries must be objects";
			return false;
		}
		MepTarget target;
		if(!RequireString(entry, "system", target.System, error) || !RequireString(entry, "sha1", target.Sha1, error)) {
			error = "targets[]: " + error;
			return false;
		}
		if(!IsKnownSystem(target.System)) {
			error = "targets[]: unknown system '" + target.System + "'";
			return false;
		}
		if(!IsHexUpperOrLower(target.Sha1, 40)) {
			error = "targets[]: 'sha1' must be 40 hex digits";
			return false;
		}
		target.Sha1 = StringUtilities::ToUpper(target.Sha1);
		target.Crc32 = entry.GetString("crc32");
		if(!target.Crc32.empty()) {
			if(!IsHexUpperOrLower(target.Crc32, 8)) {
				error = "targets[]: 'crc32' must be 8 hex digits";
				return false;
			}
			target.Crc32 = StringUtilities::ToUpper(target.Crc32);
		}
		target.Name = entry.GetString("name");
		out.Targets.push_back(target);
	}

	//patches (optional, ADR-0044): [{sha1, file}]
	const JsonValue* patches = root.Get("patches");
	if(patches) {
		if(!patches->IsArray()) {
			error = "'patches' must be an array";
			return false;
		}
		for(const JsonValue& entry : patches->GetArray()) {
			MepPatch patch;
			if(!entry.IsObject() || !RequireString(entry, "sha1", patch.Sha1, error) || !RequireString(entry, "file", patch.File, error)) {
				error = "patches[]: entries need 'sha1' and 'file'";
				return false;
			}
			if(!IsHexUpperOrLower(patch.Sha1, 40)) {
				error = "patches[]: 'sha1' must be 40 hex digits";
				return false;
			}
			string normalized;
			if(!NormalizeRelativePath(patch.File, normalized) || normalized.empty()) {
				error = "patches[]: unsafe path '" + patch.File + "'";
				return false;
			}
			patch.Sha1 = StringUtilities::ToUpper(patch.Sha1);
			patch.File = normalized;
			out.Patches.push_back(patch);
		}
	}

	//sections (MUST, >= 1 known section)
	const JsonValue* sections = root.Get("sections");
	if(!sections || !sections->IsObject()) {
		error = "'sections' must be an object";
		return false;
	}
	int knownSections = 0;
	for(const auto& member : sections->GetObject()) {
		int index = -1;
		for(int i = 0; i < kMepSectionCount; i++) {
			if(member.first == kSectionNames[i]) {
				index = i;
			}
		}
		if(index < 0) {
			//Unknown section: ignored for forward compatibility (§3.2)
			continue;
		}
		if(!member.second.IsObject()) {
			error = "section '" + member.first + "' must be an object";
			return false;
		}
		string path;
		if(!RequireSectionPath(member.second, path, error)) {
			error = "section '" + member.first + "': " + error;
			return false;
		}
		string normalized;
		if(!NormalizeRelativePath(path, normalized)) {
			error = "section '" + member.first + "': unsafe path '" + path + "'";
			return false;
		}
		if(index == (int)MepSectionType::Synth && normalized.empty()) {
			error = "section 'synth': path must point to a file";
			return false;
		}
		out.Sections[index].Present = true;
		out.Sections[index].HasHuman = true;
		out.Sections[index].Path = normalized;
		knownSections++;
	}
	if(knownSections == 0) {
		error = "'sections' must contain at least one of textures/audio/synth/border";
		return false;
	}

	return true;
}

const MepTarget* MepPack::FindTarget(const string& sha1) const
{
	string upper = StringUtilities::ToUpper(sha1);
	for(const MepTarget& target : Targets) {
		if(target.Sha1 == upper) {
			return &target;
		}
	}
	return nullptr;
}

bool MepPack::MatchesSha1(const string& sha1) const
{
	return FindTarget(sha1) != nullptr;
}

string MepPack::GetSectionPath(MepSectionType type) const
{
	const MepSection& section = Sections[(int)type];
	if(!section.Present || !section.HasHuman) {
		return "";
	}
	if(section.Path.empty()) {
		return RootFolder;
	}
	return FolderUtilities::CombinePath(RootFolder, section.Path);
}

string MepPack::GetSectionAutoPath(MepSectionType type) const
{
	const MepSection& section = Sections[(int)type];
	if(!section.Present || section.AutoPath.empty()) {
		return "";
	}
	return FolderUtilities::CombinePath(RootFolder, section.AutoPath);
}

const MepPatch* MepPack::FindPatch(const string& sha1) const
{
	string upper = StringUtilities::ToUpper(sha1);
	for(const MepPatch& patch : Patches) {
		if(patch.Sha1 == upper) {
			return &patch;
		}
	}
	return nullptr;
}
