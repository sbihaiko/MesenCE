#pragma once
#include "pch.h"

//One parsed + validated MEP v1 pack (docs/specs/MEP-v1.md). Pure data: the
//manager decides where the pack lives and whether it applies to the ROM.
//MepPack never opens the referenced content itself (envelope only - ADR-0005).

struct MepTarget
{
	string System; //nes, gb, gbc, sms, gg, sg1000, coleco, snes
	string Sha1; //40 uppercase hex digits (normalised on parse)
	string Crc32; //8 uppercase hex digits or empty
	string Name;
};

enum class MepSectionType : uint8_t
{
	Textures = 0,
	Audio = 1,
	Synth = 2
};

struct MepSection
{
	bool Present = false;
	//Relative to the container root, '/' separators, no leading "./", no
	//trailing '/'; "" means the root itself
	string Path;
	//F5 (ADR-0049): machine-generated layer of the same section, below the
	//human layer at Path. Empty when the pack has no auto/ folder for it.
	//"HasHuman" tells whether Path itself exists (a pack may be auto-only).
	bool HasHuman = false;
	string AutoPath;
};

//pack.json "patches": [{ "sha1": "...", "file": "rel/path.ips" }] (ADR-0044).
//Applied only to the ROM whose No-Intro sha1 matches; other targets load
//everything else and skip the patch.
struct MepPatch
{
	string Sha1;
	string File;
};

//Where the pack was found (ADR-0040 containers, ADR-0049 sibling folder)
enum class MepPackOrigin : uint8_t
{
	Folder = 0,
	Zip = 1,
	Sibling = 2
};

class MepPack
{
public:
	//pack.json fields
	string SpecVersion;
	string Name;
	string Version;
	string Author;
	string License;
	vector<MepTarget> Targets;
	vector<MepPatch> Patches;
	MepSection Sections[3];

	//Filled by the manager
	string ContainerName; //folder name or zip base name (precedence key, ADR-0040)
	string RootFolder; //absolute folder holding pack.json (extracted cache for zips)
	bool FromZip = false;
	MepPackOrigin Origin = MepPackOrigin::Folder;
	//True for a pack described by the folder convention alone (no pack.json)
	bool Synthetic = false;

	//Parses/validates pack.json text. Returns false with a human-readable
	//reason when any MUST rule of MEP-v1 §2.3/§3.1/§4 is violated or the
	//JSON is malformed. Unknown fields/sections are ignored (§3.2).
	static bool Parse(const string& json, MepPack& out, string& error);

	//True when any target's sha1 equals the given hash (case-insensitive)
	bool MatchesSha1(const string& sha1) const;

	//The matching target for this hash (nullptr when none)
	const MepTarget* FindTarget(const string& sha1) const;

	const MepSection& GetSection(MepSectionType type) const { return Sections[(int)type]; }
	bool HasSection(MepSectionType type) const { return Sections[(int)type].Present; }

	//Absolute path of a section's human layer (folder for textures/audio, file
	//for synth); empty when the section has no human layer
	string GetSectionPath(MepSectionType type) const;
	//Absolute path of the section's auto/ layer; empty when none (ADR-0049)
	string GetSectionAutoPath(MepSectionType type) const;

	//The patch that applies to this ROM hash, nullptr when none
	const MepPatch* FindPatch(const string& sha1) const;

	//Fills the sections from the fixed folder layout (ADR-0049):
	//textures/hires.txt, audio/hires.txt, synth/preset.cfg and the same
	//three under auto/. Returns true when at least one layer exists.
	bool DetectConventionLayout();

	//Section/layer relative paths of the convention
	static const char* GetConventionPath(MepSectionType type);
	static constexpr const char* AutoFolderName = "auto";

	static const char* GetSectionName(MepSectionType type);

	//Normalises a container-relative path and rejects anything that could
	//escape the pack root (spec §2.3/§6 - also used for zip entries).
	//Returns false when unsafe; "normalized" receives the cleaned path.
	static bool NormalizeRelativePath(const string& path, string& normalized);

	//ADR-0120: last-priority, additive fallback consulted by
	//MepPackManager::PrepareZip only after the pack.json-root and
	//zip-name-equals-ROM conventions (ADR-0040/ADR-0049) both fail. Pure and
	//I/O-free: operates only on the normalized entry-path list PrepareZip
	//already builds while validating zip-slip (no ZipReader/filesystem
	//access here, so it stays link-safe for core-unit-tests). Searches for a
	//subfolder literally named after the ROM (case-insensitive) that
	//directly holds a convention probe file (hires.txt, preset.cfg or
	//fingerprints.json - the leaf names of MepPack's own kConventionProbe
	//table), e.g. entries wrapped one extra release-zip folder deep:
	//"Contra80s-v1.1/Contra (U) [!]/hires.txt". Returns the discovered
	//prefix up to and including the ROM-named segment (no trailing '/');
	//"" when no candidate matches or more than one distinct candidate
	//matches (ambiguous - fails closed rather than guessing).
	//
	//"Depth" is the number of '/'-separated path segments in the normalized
	//entry itself (not just the discovered prefix), e.g.
	//"Contra80s-v1.1/Contra (U) [!]/hires.txt" is depth 3. Only entries at
	//depth <= kMepFallbackMaxDepth are considered; the whole list is refused
	//(fail-closed, "" returned) once it holds more than
	//kMepFallbackMaxEntries entries, so a pathological zip can't force an
	//unbounded scan.
	static constexpr int kMepFallbackMaxDepth = 4;
	static constexpr int kMepFallbackMaxEntries = 2000;
	static string FindFallbackSubfolder(const vector<string>& normalizedEntries, const string& romName);

	static bool IsValidSemver(const string& text);
	static bool IsKnownSystem(const string& system);
};
