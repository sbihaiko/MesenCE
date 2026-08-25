#pragma once
#include "pch.h"
#include "Shared/EnhancementPacks/MepPack.h"

class VirtualFile;
class Emulator;

//Discovers MEP packs in <home>/EnhancementPacks/ (directories and zips),
//matches them against the loaded ROM's No-Intro SHA-1 and exposes, per
//section, the winning pack's content path to the console loaders
//(ADR-0039 hash, ADR-0040 storage/precedence, ADR-0041 audio scope,
//ADR-0042 synth layering). Owned by Emulator; LoadForRom runs inside
//Emulator::InternalLoadRom before the console's own LoadRom.
class MepPackManager
{
private:
	Emulator* _emu;
	string _romSha1;
	//Containers disabled by the user (UI/config), lower-cased; independent of
	//the current scan so it can be pushed at any time
	unordered_set<string> _disabledContainers;
	string _romExtension;
	string _romName; //file name without extension (convention key, ADR-0049)
	string _romFolder; //folder holding the ROM (or its archive)
	vector<MepPack> _packs; //matching packs, precedence order (first wins)
	vector<string> _rejected; //"<container>: <reason>" for the UI/log

	void ScanAndMatch();
	void ScanSiblingFolder();
	bool LoadContainer(const string& rootFolder, const string& containerName, bool fromZip, MepPack& outPack, string& error);
	//Folder-convention pack (no pack.json): sections detected from the fixed
	//layout, target = the current ROM. False when the folder has no layer.
	bool LoadConventionPack(const string& rootFolder, const string& containerName, MepPackOrigin origin, MepPack& outPack);
	static string SystemFromExtension(const string& lowerExt);
	bool PrepareZip(const string& zipPath, const string& cacheRoot, string& outFolder, string& error);
	static bool ReadTextFile(const string& path, string& out);

public:
	MepPackManager(Emulator* emu);

	static constexpr const char* FolderName = "EnhancementPacks";
	static constexpr const char* CacheFolderName = ".cache";

	//<home>/EnhancementPacks (created on demand)
	static string GetPacksFolder();

	//No-Intro SHA-1 of the ROM payload (ADR-0039): 40 uppercase hex digits
	static string ComputeNoIntroSha1(VirtualFile& romFile);

	//Rescans the packs folder and keeps only the packs matching this ROM
	void LoadForRom(VirtualFile& romFile);
	void Clear();

	//Applies the winning pack's patches[] entry for this ROM (ADR-0044),
	//in place, before the console reads the ROM. Honours the
	//ApplyPatchOnHashMismatch override. Returns true when a patch was applied.
	bool ApplyPatches(VirtualFile& romFile);

	//Sibling folder of a ROM: <dir>/<name>/ (ADR-0049)
	static string GetSiblingFolder(VirtualFile& romFile);
	const string& GetRomName() const { return _romName; }
	const string& GetRomFolder() const { return _romFolder; }

	const string& GetRomSha1() const { return _romSha1; }
	const vector<MepPack>& GetPacks() const { return _packs; }
	const vector<string>& GetRejected() const { return _rejected; }
	bool HasPacks() const { return !_packs.empty(); }

	//Per-pack toggle (persisted by the UI); takes effect on the next load
	void SetPackEnabled(const string& containerName, bool enabled);
	bool IsPackEnabled(const string& containerName) const;

	//Winning pack for a section: first *enabled* pack in precedence order
	//that has it, honouring EnhancementPackConfig section toggles; nullptr
	//when nothing applies
	const MepPack* GetPackForSection(MepSectionType type) const;

	//One line per matching pack, tab-separated:
	//container\tname\tversion\tauthor\tlicense\tsections(comma)\tenabled(0/1)\tfromZip(0/1)
	//followed by "!<container>: <reason>" lines for rejected containers
	string GetPackListText() const;

	//Absolute content path of the winning section's human layer, or "" when
	//none: folder for textures/audio, file for synth
	string GetSectionPath(MepSectionType type) const;
	//Absolute path of the winning section's auto/ layer, or "" (ADR-0049)
	string GetSectionAutoPath(MepSectionType type) const;
	//ESP files of the winning synth section in apply order: auto/ layer first,
	//human layer last (each may be absent)
	vector<string> GetSynthPresetPaths() const;
	//True when the winning pack for the section is the ROM's sibling folder -
	//it then also overrides the legacy loose HdPacks/<rom>/ pack
	bool IsSectionFromSibling(MepSectionType type) const;
};
