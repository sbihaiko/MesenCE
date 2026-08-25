#pragma once
#include "pch.h"
#include "Shared/EnhancementPacks/MepPack.h"

class VirtualFile;

//Discovers MEP packs in <home>/EnhancementPacks/ (directories and zips),
//matches them against the loaded ROM's No-Intro SHA-1 and exposes, per
//section, the winning pack's content path to the console loaders
//(ADR-0039 hash, ADR-0040 storage/precedence, ADR-0041 audio scope,
//ADR-0042 synth layering). Owned by Emulator; LoadForRom runs inside
//Emulator::InternalLoadRom before the console's own LoadRom.
class MepPackManager
{
private:
	string _romSha1;
	string _romExtension;
	vector<MepPack> _packs; //matching packs, precedence order (first wins)
	vector<string> _rejected; //"<container>: <reason>" for the UI/log

	void ScanAndMatch();
	bool LoadContainer(const string& rootFolder, const string& containerName, bool fromZip, MepPack& outPack, string& error);
	bool PrepareZip(const string& zipPath, const string& cacheRoot, string& outFolder, string& error);
	static bool ReadTextFile(const string& path, string& out);

public:
	static constexpr const char* FolderName = "EnhancementPacks";
	static constexpr const char* CacheFolderName = ".cache";

	//<home>/EnhancementPacks (created on demand)
	static string GetPacksFolder();

	//No-Intro SHA-1 of the ROM payload (ADR-0039): 40 uppercase hex digits
	static string ComputeNoIntroSha1(VirtualFile& romFile);

	//Rescans the packs folder and keeps only the packs matching this ROM
	void LoadForRom(VirtualFile& romFile);
	void Clear();

	const string& GetRomSha1() const { return _romSha1; }
	const vector<MepPack>& GetPacks() const { return _packs; }
	const vector<string>& GetRejected() const { return _rejected; }
	bool HasPacks() const { return !_packs.empty(); }

	//Winning pack for a section (first in precedence order that has it),
	//nullptr when no matching pack provides the section
	const MepPack* GetPackForSection(MepSectionType type) const;

	//Absolute content path of the winning section, or "" when none:
	//folder for textures/audio, file for synth
	string GetSectionPath(MepSectionType type) const;
};
