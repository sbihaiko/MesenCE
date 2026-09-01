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

//P.3: identity a container's .mep-install.json stamp carries (ADR-0140
//pack_id, ADR-0139 content_id); both empty for a stamp-less container (the
//UI derives `local:<container>` and never content-merges it, PRD §5).
struct MepPackIdentity
{
	string PackId;
	string ContentId;
};

class MepPackManager
{
private:
	Emulator* _emu;
	string _romSha1;
	//Containers disabled by the user (UI/config), lower-cased; independent of
	//the current scan so it can be pushed at any time
	unordered_set<string> _disabledContainers;
	//ADR-0145: containers whose pack.json targets did not match the loaded
	//ROM's No-Intro SHA1 (lower-cased). They stay in _packs as *optimistic*
	//candidates: textures apply (HdNesPack falls through per-tile, no
	//corruption) and BPS patches may attempt (self-validating); IPS patches
	//and audio/synth still require an exact match. Kept here, not on MepPack,
	//because the Makefile does not track header dependencies (ABI-safe).
	unordered_set<string> _optimisticContainers;
	//P.3 (PRD Part B §5): per-ROM-sha1 preferred pack_id pushed by the
	//UI from EnhancementPackConfig. Keyed by the No-Intro sha1 of the ROM as
	//loaded, so the right choice applies per ROM; "" or a missing key means no
	//preference (lexicographic default, ADR-0040).
	unordered_map<string, string> _preferredPackIdByRomSha1;
	//P.3: pack_id/content_id read from each container's .mep-install.json
	//stamp, keyed by the lower-cased container name. Kept OUT of MepPack on
	//purpose: this Makefile does not track header dependencies, so changing
	//MepPack's layout would leave stale objects ABI-mismatched (a silent
	//memory-corruption crash). The manager owns identity; MepPack stays pure.
	unordered_map<string, MepPackIdentity> _packIdentityByContainer;
	string _romExtension;
	string _romName; //file name without extension (convention key, ADR-0049)
	string _romFolder; //folder holding the ROM (or its archive)
	vector<MepPack> _packs; //matching packs, precedence order (first wins)
	vector<string> _rejected; //"<container>: <reason>" for the UI/log
	//ADR-0145: snapshot of the winning textures pack, taken on the emulation
	//thread at load time. The HD renderer's health signal runs on the decode
	//thread, so it must NOT read _packs/_optimisticContainers directly - it
	//reads this snapshot instead (written once per load, before the render
	//thread can fire) and asks to auto-disable when match rate stays low.
	string _texturesContainer;
	bool _texturesIsOptimistic = false;
	bool _bootstrapping = false;
	string _bootstrapSaveFolder; //owns the char* handed to HdPackBuilderOptions

	void ScanAndMatch();
	void ScanSiblingFolder();
	bool LoadContainer(const string& rootFolder, const string& containerName, bool fromZip, MepPack& outPack, string& error);
	//Folder-convention pack (no pack.json): sections detected from the fixed
	//layout, target = the current ROM. False when the folder has no layer.
	bool LoadConventionPack(const string& rootFolder, const string& containerName, MepPackOrigin origin, MepPack& outPack);
	//ADR-0147: true when the sibling holds mep/ as the human pack layer
	//(a section probe under mep/, or a mep/pack.json exists)
	bool HasSiblingMepPack(const string& sibling) const;
	//ADR-0147: the sibling pack whose human layer is rooted at mep/ and whose
	//machine layer is the sibling auto/ folder (siblings, not children)
	bool LoadMepSiblingPack(const string& sibling, MepPack& outPack);
	static string SystemFromExtension(const string& lowerExt);
	//Reads .mep-install.json at the pack root into _packIdentityByContainer
	//(P.3; a missing/malformed stamp leaves the entry with empty fields)
	void ReadInstallIdentity(MepPack& pack);
	//A pack's effective pack_id for preference matching (P.3): its
	//.mep-install.json pack_id when present, else the ADR-0140 rule-4
	//`local:<container>` fallback (lower-cased)
	string EffectivePackId(const MepPack& pack) const;
	//The enabled, section-having pack whose effective pack_id equals the
	//preferred one for the loaded ROM, or nullptr when there is no preference
	//or no matching pack
	const MepPack* FindPreferredPack(MepSectionType type) const;
	//ADR-0145: true when the pack was kept as an optimistic candidate (no
	//target matched the loaded ROM's No-Intro SHA1)
	bool IsOptimistic(const MepPack& pack) const;
	//ADR-0145: the first patch in "pack" whose file is a self-validating BPS
	//patch (magic "BPS1"), nullptr when none - the only patch format safe to
	//apply optimistically on a SHA1 mismatch
	const MepPatch* FindFirstBpsPatch(const MepPack& pack) const;
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

	//P.3: records the per-ROM preferred pack_id (ADR-0140 id or `local:<
	//container>`); "" or an empty container removes it. Pushed at config-apply
	//time; consulted per ROM in GetPackForSection (see _preferredPackIdByRomSha1).
	void SetPreferredMepPack(const string& romSha1, const string& packId);
	//P.3: drops every per-ROM preference, so a config-apply is authoritative
	//(the UI resets then re-pushes the full current map - a removed choice is
	//never left stale in the core).
	void ClearPreferredMepPacks();

	//Winning pack for a section: first *enabled* pack in precedence order
	//that has it, honouring EnhancementPackConfig section toggles; nullptr
	//when nothing applies. P.3: a pack whose effective pack_id equals the
	//preferred one for the loaded ROM's sha1 wins even when lexicographically
	//later (PRD §5 - the preference overrides the ADR-0040 default order).
	//ADR-0145: Textures may come from an optimistic (SHA1-mismatched) pack -
	//the renderer falls through per-tile and a low match-rate health signal
	//auto-disables it; Audio/Synth still require an exact match (out of scope).
	const MepPack* GetPackForSection(MepSectionType type) const;

	//ADR-0145: runtime health signal from the HD renderer. When the bg-tile
	//match rate stays low on an *optimistic* textures pack (applied without an
	//exact SHA1 match), warns the user and auto-disables that container so the
	//next load stops trying it. No-op when the active textures pack is an exact
	//match (low coverage there is legitimate, not a wrong-game signal).
	void HandleLowTextureMatchRate();

	//One line per matching pack, tab-separated:
	//container\tname\tversion\tauthor\tlicense\tsections(comma)\tenabled(0/1)\tfromZip(0/1)\tpackId\tcontentId
	//(packId/contentId from .mep-install.json, empty for a stamp-less container;
	//P.3 feeds the UI resolver's pack_id/`local:` derivation and content_id merge)
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
