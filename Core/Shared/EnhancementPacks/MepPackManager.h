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
	bool _bootstrapping = false;
	string _bootstrapSaveFolder; //owns the char* handed to HdPackBuilderOptions

	void ScanAndMatch();
	void ScanSiblingFolder();
	bool LoadContainer(const string& rootFolder, const string& containerName, bool fromZip, MepPack& outPack, string& error);
	//Folder-convention pack (no pack.json): sections detected from the fixed
	//layout, target = the current ROM. False when the folder has no layer.
	bool LoadConventionPack(const string& rootFolder, const string& containerName, MepPackOrigin origin, MepPack& outPack);
	static string SystemFromExtension(const string& lowerExt);
	//Extracts a zip to the cache; rejects zips with neither a root pack.json
	//nor a name matching the ROM, unless MepPack::FindFallbackSubfolder
	//(ADR-0120, last-priority) locates an unambiguous ROM-named subfolder
	//first - "outFolder"/"error" stay this method's only outputs.
	bool PrepareZip(const string& zipPath, const string& cacheRoot, string& outFolder, string& error);
	//True when the cache at outFolder already matches the zip's stamp and
	//still has a root pack.json (PrepareZip's early-exit check)
	static bool IsCacheCurrent(const string& outFolder, const string& stampPath, const string& stamp);
	//Loads+validates the zip's entries, resolves the ADR-0120 fallback when
	//needed, extracts and (re)writes the cache stamp; split out of
	//PrepareZip so each step stays focused
	bool ExtractZip(const string& zipPath, const string& name, string& outFolder, const string& stampPath, const string& stamp, string& error);
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
	//Sibling folder of the loaded ROM ("" when no ROM)
	string GetSiblingFolder() const;

	//F5.2: when BootstrapEnhancementFolder is on and no textures layer applies
	//to this ROM (no sibling/MEP textures, no loose HdPacks/<rom>/), export
	//the ROM tiles and start recording played tiles (xBRZ 4x) into
	//<sibling>/auto/textures/ (fallback: EnhancementPacks/<Game>/ when the
	//ROM's folder is not writable). Call once the console is initialised.
	void StartBootstrapIfNeeded();
	bool IsBootstrapping() const { return _bootstrapping; }
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
