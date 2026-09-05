//Fase 4 (docs/roadmap/plano-testes-unitarios.md): framework-free C++ unit
//test harness - no MesenCore/emulator/ROM. Bloco A exercises
//ChannelRoleClassifier; Bloco B exercises MepPack::NormalizeRelativePath
//(driven by docs/specs/golden/mep/path-cases.txt) and MepPack::Parse; Bloco C
//(ADR-0120) exercises MepPack::FindFallbackSubfolder, the pure last-priority
//zip-fallback search PrepareZip consults, with literal fixtures; Bloco D
//(ADR-0121) exercises MepPack::DetectConventionLayout's bare-root hires.txt
//recognition against a real throwaway temp-dir tree (the one block here that
//touches the filesystem, since DetectConventionLayout itself does); Bloco E
//(ADR-0138 §4/§37, F6.4a) exercises MepRecipeInstaller/MepRecipeOps/SHA256
//against the real-bytes golden fixture under
//docs/specs/golden/mep-recipe/fixture/ - including shelling out to the
//read-only Python reference interpreter (scripts/mep_recipe.py apply) for a
//byte-for-byte parity check, so both interpreters MUST agree on this fixture
//forever after. No framework: cases print PASS/FAIL, exit is non-zero on any
//failure (see roles_probe.cpp). Bloco I (ADR-0142) exercises OggMixer's BGM
//crossfade through IOggSource stubs - no stb_vorbis, no Emulator. Bloco J
//(ADR-0134) exercises OggLoopStream's track loop point through a stub
//IOggDecoder; Bloco K (ADR-0133) exercises the replacement mute mask shared
//by NesAudioReplacer (policy) and NesSoundMixer (application); Bloco L
//(F5.4g Bloco B) diffs EnhancedSynthEngine's rendered PCM against
//docs/specs/golden/synth/enhanced-synth-pcm.txt. Bloco M (ADR-0120 §4) is the
//E2E zip harness that section deferred: it builds real archives with
//Utilities/miniz.cpp and runs MepZipExtract - the pipeline
//MepPackManager::PrepareZip delegates to - over them; Bloco N (P.7) covers
//AspectRatioMath's per-setting geometry (16:9/4:3/auto/PAR), not the pixels on
//screen; Bloco O (P.4) covers ShortcutKeyRules' keyboard-block exemption that
//keeps ToggleOverlay reachable inside a keyboard game; Bloco P (ADR-0153,
//Phase 9) covers the artist-legible sheet pipeline end to end on synthetic
//grids - status-bar detection, grid phase advantage, vocabulary counts and the
//`misc` isolation rule, mutual-predictability grouping over background
//adjacency and (F9.5) over OAM offsets, scroll matching, and
//SheetRender's geometry and sidecar JSON. Run from the repo root so the golden paths
//and the `python3 scripts/mep_recipe.py` shell-out resolve.
#include "Shared/Audio/ChannelRoleClassifier.h"
#include "Shared/Audio/EnhancedSynthEngine.h"
#include "Shared/EnhancementPacks/AudioFingerprint.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Shared/EnhancementPacks/MepRecipeInstaller.h"
#include "Shared/EnhancementPacks/MepContentId.h"
#include "Shared/EnhancementPacks/MepZipExtract.h"
#include "Shared/MessageManager.h"
#include "Shared/Video/BorderLayout.h"
#include "Shared/Video/AspectRatioMath.h"
#include "Shared/ShortcutKeyRules.h"
#include "NES/HdPacks/MetatileVocabulary.h"
#include "NES/HdPacks/ScreenStitcher.h"
#include "NES/HdPacks/SheetGrouping.h"
#include "NES/HdPacks/SheetRender.h"
#include "NES/HdPacks/SpriteGrouping.h"
#include "NES/HdPacks/OggFadeRamp.h"
#include "NES/HdPacks/OggLoopStream.h"
#include "NES/HdPacks/OggMixer.h"
#include "Shared/Audio/ReplacementMuteMask.h"
#include "Utilities/Base64.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/JsonReader.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/miniz.h"
#include "Utilities/sha256.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace
{
	int gCases = 0;
	int gFailures = 0;

	void Check(bool condition, const std::string& name, const std::string& detail = "")
	{
		gCases++;
		if(condition) {
			printf("PASS  %s\n", name.c_str());
		} else {
			gFailures++;
			printf("FAIL  %s%s%s\n", name.c_str(), detail.empty() ? "" : ": ", detail.c_str());
		}
	}

	double NoteToFreq(double note)
	{
		return 440.0 * std::pow(2.0, (note - 69.0) / 12.0);
	}

	//--- Bloco A: ChannelRoleClassifier -------------------------------------

	ChannelRoleClassifier MakeLeadOnlyClassifier()
	{
		static constexpr ChannelRoleClassifier::ChannelRole defaults[1] = { ChannelRoleClassifier::ChannelRole::Lead };
		ChannelRoleClassifier roles;
		roles.Init(1, defaults);
		return roles;
	}
	void TestSilentChannelNotSfx()
	{
		ChannelRoleClassifier roles = MakeLeadOnlyClassifier();
		ChannelRoleClassifier::Channel ch; //Freq/Vol default to 0: never sounding
		for(int i = 0; i < 60; i++) {
			roles.Update(&ch, 0.01);
		}
		Check(!roles.IsSfx(0), "BlocoA: silent channel is never flagged SFX");
	}

	//Holds channel 0 at Vol=0.8, HwSweep on, stepping stepSemitones every dt
	//seconds for 8 steps; returns the OR of every SfxCue seen along the way.
	uint8_t RunHwSweepGlide(ChannelRoleClassifier& roles, double stepSemitones, double dt)
	{
		ChannelRoleClassifier::Channel ch { NoteToFreq(60.0), 0.8, true };
		roles.Update(&ch, dt); //onset: establishes the baseline pitch
		uint8_t cues = 0;
		double note = 60.0;
		for(int i = 0; i < 8; i++) {
			note += stepSemitones;
			ch.Freq = NoteToFreq(note);
			roles.Update(&ch, dt);
			cues |= roles.SfxCues(0);
		}
		return cues;
	}
	void TestFastSweepIsSfx()
	{
		ChannelRoleClassifier roles = MakeLeadOnlyClassifier();
		uint8_t cues = RunHwSweepGlide(roles, 1.0, 0.01); //100 st/s: over kGlideMinRate
		Check((cues & ChannelRoleClassifier::CueSweep) != 0, "BlocoA: fast hardware sweep raises CueSweep");
		Check(roles.IsSfx(0), "BlocoA: fast hardware sweep + amplitude flags SFX");
	}
	void TestSlowGlideStaysMusic()
	{
		ChannelRoleClassifier roles = MakeLeadOnlyClassifier();
		RunHwSweepGlide(roles, 0.25, 0.1); //total 2.0 st @ 2.5 st/s: under kSweepMinTotal(4)/kGlideMinRate
		Check(!roles.IsSfx(0), "BlocoA: slow >=2-semitone glide stays music (not SFX)");
	}

	void TestLeadVsBassByMeanPitch()
	{
		//Deliberately swapped defaults: a correct outcome proves the roles came from mean pitch, not the defaults.
		static constexpr ChannelRoleClassifier::ChannelRole defaults[2] = { ChannelRoleClassifier::ChannelRole::Bass, ChannelRoleClassifier::ChannelRole::Lead };
		ChannelRoleClassifier roles;
		roles.Init(2, defaults);
		ChannelRoleClassifier::Channel ch[2] = {
			{ NoteToFreq(72.0), 0.8, false }, //high, steady: should end up Lead
			{ NoteToFreq(36.0), 0.8, false }, //low, steady: should end up Bass
		};
		for(int i = 0; i < 400; i++) { //4s covers the audible ramp + kDecisionsToSwitch + kSwapGraceS
			roles.Update(ch, 0.01);
		}
		Check(roles.Role(0) == ChannelRoleClassifier::ChannelRole::Lead, "BlocoA: high mean-pitch channel becomes lead");
		Check(roles.Role(1) == ChannelRoleClassifier::ChannelRole::Bass, "BlocoA: low mean-pitch channel becomes bass");
	}

	//--- Bloco B: MepPack ----------------------------------------------------

	void CheckPathCase(const std::string& path, const std::string& label, int lineNo, int& caseCount)
	{
		bool expectOk = label == "ok";
		if(!expectOk && label != "bad") {
			Check(false, "BlocoB: path-cases.txt line " + std::to_string(lineNo), "unknown label '" + label + "'");
			return;
		}
		std::string normalized;
		bool actualOk = MepPack::NormalizeRelativePath(path, normalized);
		caseCount++;
		Check(actualOk == expectOk, "BlocoB: NormalizeRelativePath('" + path + "') == " + label, actualOk ? "got ok" : "got bad");
	}
	void TestNormalizeRelativePathGolden()
	{
		const std::string fixturePath = "docs/specs/golden/mep/path-cases.txt";
		std::ifstream file(fixturePath);
		if(!file.is_open()) {
			Check(false, "BlocoB: path-cases.txt fixture opens", "could not open " + fixturePath + " (run from repo root)");
			return;
		}
		std::string line;
		int lineNo = 0, caseCount = 0;
		while(std::getline(file, line)) {
			lineNo++;
			if(!line.empty() && line.back() == '\r') {
				line.pop_back();
			}
			if(line.empty() || line[0] == '#') {
				continue;
			}
			size_t tab = line.find('\t');
			if(tab == std::string::npos) {
				Check(false, "BlocoB: path-cases.txt line " + std::to_string(lineNo), "missing TAB separator: '" + line + "'");
				continue;
			}
			CheckPathCase(line.substr(0, tab), line.substr(tab + 1), lineNo, caseCount);
		}
		Check(caseCount > 0, "BlocoB: path-cases.txt fixture has at least one case", "found " + std::to_string(caseCount));
	}

	void TestNormalizeRelativePathRejectsControlChars()
	{
		//Control characters (bytes < 0x20) are deliberately excluded from
		//path-cases.txt (the TAB column format can't carry them literally -
		//ADR-0124), so this C++ side owns its own literal coverage, mirroring
		//the C# IsSafePath_RejectsControlCharacters theory in
		//UI.Tests/Mep/MepZipValidatorTests.cs.
		static const std::pair<char, const char*> cases[] = {
			{ '\0', "NUL" },
			{ '\x01', "0x01" },
			{ '\t', "a literal TAB" },
		};
		for(const auto& c : cases) {
			std::string path = "textures/bad";
			path += c.first;
			path += "name.txt";
			std::string normalized;
			bool actualOk = MepPack::NormalizeRelativePath(path, normalized);
			Check(!actualOk, std::string("BlocoB: NormalizeRelativePath rejects a path containing ") + c.second, actualOk ? "unexpectedly succeeded" : "correctly rejected");
		}
	}

	void TestParseValidPackJson()
	{
		const std::string fixturePath = "docs/specs/golden/mep/pack.json";
		std::ifstream file(fixturePath, std::ios::binary);
		if(!file.is_open()) {
			Check(false, "BlocoB: pack.json fixture opens", "could not open " + fixturePath + " (run from repo root)");
			return;
		}
		std::ostringstream buffer;
		buffer << file.rdbuf();
		MepPack pack;
		std::string error;
		bool ok = MepPack::Parse(buffer.str(), pack, error);
		Check(ok, "BlocoB: Parse(pack.json golden) succeeds", error);
		if(!ok) {
			return;
		}
		Check(pack.Name.rfind("F1 Test Tone", 0) == 0, "BlocoB: Parse fills 'name'", pack.Name);
		Check(pack.Targets.size() == 1, "BlocoB: Parse fills one target");
		Check(pack.HasSection(MepSectionType::Textures) && pack.HasSection(MepSectionType::Audio) && pack.HasSection(MepSectionType::Synth), "BlocoB: Parse fills all three sections");
	}

	void TestParseFailureCases()
	{
		//{json, label}; the non-object case is re-run below to also check its
		//error message names the reason.
		static const std::pair<const char*, const char*> cases[] = {
			{ "{ this is not json", "malformed JSON" },
			{ "[1, 2, 3]", "a non-object root" },
			{ "{}", "an object missing required fields" },
		};
		for(const auto& c : cases) {
			MepPack pack;
			std::string error;
			bool ok = MepPack::Parse(c.first, pack, error);
			Check(!ok, std::string("BlocoB: Parse rejects ") + c.second, ok ? "unexpectedly succeeded" : error);
		}
		MepPack pack;
		std::string error;
		MepPack::Parse("[1, 2, 3]", pack, error);
		Check(error.find("object") != std::string::npos, "BlocoB: Parse's non-object error names the reason", error);
	}

	//F6.6 (ADR-0138 §3.2 / round-trip fix): the MEP recipe installer writes
	//`"path": ""` for a section at the pack root (WriteSections/DeriveSections),
	//so Parse must accept an empty path for textures/audio and resolve it to the
	//root, while synth - whose path names a preset file, never a folder - must
	//still be rejected.
	void TestParseEmptySectionPath()
	{
		MepPack pack;
		std::string error;
		const char* json = R"({
			"mep": "1.1.0",
			"name": "Root Sections",
			"version": "1.0.0",
			"license": "CC0-1.0",
			"targets": [{"system": "nes", "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B"}],
			"sections": {
				"textures": {"path": ""},
				"audio": {"path": ""}
			}
		})";
		bool ok = MepPack::Parse(json, pack, error);
		Check(ok, "BlocoB: Parse accepts an empty textures/audio section path (= the pack root)", error);
		if(!ok) {
			return;
		}
		Check(pack.HasSection(MepSectionType::Textures) && pack.HasSection(MepSectionType::Audio), "BlocoB: empty-path sections are still detected as present");
		Check(pack.Sections[(int)MepSectionType::Textures].Path.empty(), "BlocoB: empty textures path parses to Path=\"\"", pack.Sections[(int)MepSectionType::Textures].Path);
		Check(pack.GetSectionPath(MepSectionType::Textures) == pack.RootFolder, "BlocoB: empty textures path resolves to RootFolder");

		MepPack synthPack;
		std::string synthError;
		const char* synthJson = R"({
			"mep": "1.1.0",
			"name": "Empty Synth",
			"version": "1.0.0",
			"license": "CC0-1.0",
			"targets": [{"system": "nes", "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B"}],
			"sections": {"synth": {"path": ""}}
		})";
		bool synthOk = MepPack::Parse(synthJson, synthPack, synthError);
		Check(!synthOk, "BlocoB: Parse still rejects an empty synth path", synthOk ? "unexpectedly succeeded" : synthError);
		Check(synthError.find("path must point to a file") != std::string::npos, "BlocoB: empty synth rejection names the reason", synthError);
	}

	//--- Bloco C: MepPack::FindFallbackSubfolder (ADR-0120) -------------------

	void TestFallbackSubfolderContra80sResolves()
	{
		//Release-zip wrapper one level deep, exactly the TasticHacks/Contra80s
		//shape described in the ADR: <wrapper>/<ROM name>/hires.txt (depth 3)
		std::vector<std::string> entries = {
			"Contra80s-v1.1/readme.txt",
			"Contra80s-v1.1/Contra (U) [!]/hires.txt",
		};
		std::string prefix = MepPack::FindFallbackSubfolder(entries, "Contra (U) [!]");
		Check(prefix == "Contra80s-v1.1/Contra (U) [!]", "BlocoC: FindFallbackSubfolder resolves the Contra80s-shaped wrapper", "got '" + prefix + "'");

		//Literal "<ROM name>/hires.txt" shape (no extra wrapper level, depth 2)
		std::vector<std::string> flatEntries = { "Contra (U) [!]/hires.txt" };
		std::string flatPrefix = MepPack::FindFallbackSubfolder(flatEntries, "Contra (U) [!]");
		Check(flatPrefix == "Contra (U) [!]", "BlocoC: FindFallbackSubfolder resolves a bare '<ROM name>/hires.txt' entry", "got '" + flatPrefix + "'");
	}

	void TestFallbackSubfolderAmbiguousIsEmpty()
	{
		//Two distinct subfolders both named after the ROM: fails closed
		//rather than guessing which one is the real pack root
		std::vector<std::string> entries = {
			"WrapperA/Contra (U) [!]/hires.txt",
			"WrapperB/Contra (U) [!]/hires.txt",
		};
		std::string prefix = MepPack::FindFallbackSubfolder(entries, "Contra (U) [!]");
		Check(prefix.empty(), "BlocoC: FindFallbackSubfolder is ambiguous/empty for two ROM-named subfolders", "got '" + prefix + "'");
	}

	void TestFallbackSubfolderDepthAndEntryCaps()
	{
		//Depth cap (kMepFallbackMaxDepth=4): a 5-segment entry is refused
		//even though its shape would otherwise resolve
		std::vector<std::string> tooDeep = { "a/b/c/Contra (U) [!]/hires.txt" };
		Check(MepPack::FindFallbackSubfolder(tooDeep, "Contra (U) [!]").empty(), "BlocoC: FindFallbackSubfolder rejects entries past the depth cap");

		//Entry-count cap (kMepFallbackMaxEntries=2000): an oversized list is
		//refused outright, fail-closed
		std::vector<std::string> tooMany(MepPack::kMepFallbackMaxEntries + 1, "Contra (U) [!]/hires.txt");
		Check(MepPack::FindFallbackSubfolder(tooMany, "Contra (U) [!]").empty(), "BlocoC: FindFallbackSubfolder rejects an oversized entry list");

		//No candidate at all: unrelated entries, no match
		std::vector<std::string> noMatch = { "SomeOtherGame/hires.txt", "pack.json" };
		Check(MepPack::FindFallbackSubfolder(noMatch, "Contra (U) [!]").empty(), "BlocoC: FindFallbackSubfolder is empty when no candidate matches");
	}

	//--- Bloco D: MepPack::DetectConventionLayout bare-root hires.txt (ADR-0121) ---
	//Real filesystem I/O (unlike Blocos B/C's pure-function fixtures):
	//DetectConventionLayout() itself opens files via ifstream, so these tests
	//write a throwaway folder tree under the OS temp dir and remove it
	//afterward, rather than adding a filesystem seam to a class kept pure by
	//design elsewhere in this same file (ADR-0120 §2).

	std::filesystem::path MakeTempPackDir(const std::string& label)
	{
		std::filesystem::path dir = std::filesystem::temp_directory_path() / ("mep_core_unit_tests_" + label);
		std::error_code ec;
		std::filesystem::remove_all(dir, ec);
		std::filesystem::create_directories(dir, ec);
		return dir;
	}

	void WriteTestFile(const std::filesystem::path& path, const std::string& content)
	{
		std::ofstream out(path, std::ios::out | std::ios::binary);
		out << content;
	}

	void TestDetectConventionLayoutBareRootHiresTxt()
	{
		//The pre-MEP "classic Mesen HD pack" shape: hires.txt loose at
		//RootFolder, no textures/ wrapper - e.g. a sibling folder (ADR-0049)
		//or a zip/folder container named exactly like the ROM (ADR-0040)
		//holding nothing else. Mirrors scripts/mep_lint.py's
		//discover_sections() root-level branch.
		std::filesystem::path dir = MakeTempPackDir("bare_root_hires");
		WriteTestFile(dir / "hires.txt", "<ver>106\n");

		MepPack pack;
		pack.RootFolder = dir.string();
		bool any = pack.DetectConventionLayout();

		Check(any, "BlocoD: DetectConventionLayout finds a bare root hires.txt");
		Check(pack.HasSection(MepSectionType::Textures), "BlocoD: bare root hires.txt is recognized as the textures section");
		Check(pack.GetSectionPath(MepSectionType::Textures) == dir.string(), "BlocoD: textures section path resolves to RootFolder itself (empty Path)", pack.GetSectionPath(MepSectionType::Textures));
		Check(!pack.HasSection(MepSectionType::Audio) && !pack.HasSection(MepSectionType::Synth), "BlocoD: bare root hires.txt does not fabricate audio/synth sections");

		std::error_code ec;
		std::filesystem::remove_all(dir, ec);
	}

	void TestDetectConventionLayoutConventionWinsOverBareRoot()
	{
		//A pack with BOTH textures/hires.txt (the real convention) and a
		//loose root hires.txt must resolve to the convention path - never
		//overridden by the ADR-0121 addition (mirrors mep_lint.py's
		//sections.setdefault: existing entries win).
		std::filesystem::path dir = MakeTempPackDir("convention_wins");
		std::error_code ec;
		std::filesystem::create_directories(dir / "textures", ec);
		WriteTestFile(dir / "textures" / "hires.txt", "<ver>106\n");
		WriteTestFile(dir / "hires.txt", "<ver>106\n<img>unrelated.png\n");

		MepPack pack;
		pack.RootFolder = dir.string();
		pack.DetectConventionLayout();

		std::string texturesPath = pack.GetSectionPath(MepSectionType::Textures);
		Check(texturesPath != dir.string() && texturesPath.find("textures") != std::string::npos, "BlocoD: an existing textures/hires.txt convention is never overridden by the bare-root fallback", texturesPath);

		std::filesystem::remove_all(dir, ec);
	}

	void TestDetectConventionLayoutNoHiresTxtAtAll()
	{
		//No hires.txt anywhere: DetectConventionLayout must return false, not
		//be fooled by an unrelated file at RootFolder.
		std::filesystem::path dir = MakeTempPackDir("no_hires_at_all");
		WriteTestFile(dir / "readme.txt", "not a pack");

		MepPack pack;
		pack.RootFolder = dir.string();
		bool any = pack.DetectConventionLayout();

		Check(!any, "BlocoD: DetectConventionLayout finds nothing when there is no hires.txt anywhere");

		std::error_code ec;
		std::filesystem::remove_all(dir, ec);
	}

	void TestDetectConventionLayoutMepHumanLayer()
{
	//ADR-0147: the sibling may root the human layer at mep/ (a sibling of
	//auto/, not a child). The human probe lives under mep/; the machine layer
	//stays under auto/ - both resolved as siblings, so the human section
	//path is mep/<convention> and the machine layer is auto/<convention>.
	std::filesystem::path dir = MakeTempPackDir("mep_human_layer");
	std::error_code ec;
	std::filesystem::create_directories(dir / "mep" / "textures", ec);
	std::filesystem::create_directories(dir / "auto" / "textures", ec);
	WriteTestFile(dir / "mep" / "textures" / "hires.txt", "<ver>106\n");
	WriteTestFile(dir / "auto" / "textures" / "hires.txt", "<ver>106\n");

	MepPack pack;
	pack.RootFolder = dir.string();
	bool any = pack.DetectConventionLayout("mep");

	Check(any, "BlocoD: DetectConventionLayout finds a mep/ human layer");
	Check(pack.HasSection(MepSectionType::Textures), "BlocoD: mep/textures/hires.txt is recognized as the textures section");
	Check(pack.GetSectionPath(MepSectionType::Textures) == (dir / "mep" / "textures").string(), "BlocoD: textures human path resolves to mep/textures", pack.GetSectionPath(MepSectionType::Textures));
	Check(pack.GetSectionAutoPath(MepSectionType::Textures) == (dir / "auto" / "textures").string(), "BlocoD: textures machine layer resolves to auto/textures, a sibling of mep/", pack.GetSectionAutoPath(MepSectionType::Textures));

	std::filesystem::remove_all(dir, ec);
}

void TestDetectConventionLayoutBorderSection()
{
	//ADR-0149 (Phase 8): border convention layout 'border/border.png' and root fallback 'border.png'
	std::filesystem::path dir = MakeTempPackDir("border_convention");
	std::error_code ec;
	std::filesystem::create_directories(dir / "border", ec);
	WriteTestFile(dir / "border" / "border.png", "fake_png");

	MepPack pack;
	pack.RootFolder = dir.string();
	bool any = pack.DetectConventionLayout();

	Check(any, "BlocoD: DetectConventionLayout finds border section");
	Check(pack.HasSection(MepSectionType::Border), "BlocoD: border/border.png is recognized as Border section");
	Check(pack.GetSectionPath(MepSectionType::Border) == (dir / "border").string(), "BlocoD: border section resolves to border/ folder");

	std::filesystem::remove_all(dir, ec);

	//Fallback: bare root border.png
	std::filesystem::path dirBare = MakeTempPackDir("border_bare_root");
	WriteTestFile(dirBare / "border.png", "fake_png");

	MepPack packBare;
	packBare.RootFolder = dirBare.string();
	bool anyBare = packBare.DetectConventionLayout();

	Check(anyBare, "BlocoD: DetectConventionLayout finds root border.png");
	Check(packBare.HasSection(MepSectionType::Border), "BlocoD: root border.png recognized as Border section");
	Check(packBare.GetSectionPath(MepSectionType::Border) == dirBare.string(), "BlocoD: bare root border resolves to root folder");

	std::filesystem::remove_all(dirBare, ec);
}

//--- Bloco E: MepRecipeInstaller/MepRecipeOps/SHA256 (ADR-0138 §4/§37) ---
	//Golden fixture: docs/specs/golden/mep-recipe/fixture/ (real bytes, real
	//sha256 hashes - unlike the format-only docs/specs/golden/mep-recipe/
	//recipe.json). scripts/gen_mep_recipe_fixture.py + its own
	//scripts/test_gen_mep_recipe_fixture.py own generating/validating it;
	//this Bloco only reads it.
	const std::string kFixtureDir = "docs/specs/golden/mep-recipe/fixture";

	std::string ReadFileBytes(const std::string& path)
	{
		std::ifstream in(path, std::ios::in | std::ios::binary);
		std::ostringstream ss;
		ss << in.rdbuf();
		return ss.str();
	}

	//Writes `content` to <temp>/<name> (unique per name) and returns its path;
	//used by the Bloco H fingerprint fixtures.
	std::string WriteTempFile(const std::string& name, const std::string& content)
	{
		std::filesystem::path path = std::filesystem::temp_directory_path() / name;
		std::ofstream out(path, std::ios::out | std::ios::binary | std::ios::trunc);
		out << content;
		out.close();
		return path.string();
	}

	//Every relative file path (POSIX separators, directories excluded) under
	//`root`, skipping any entry named `excludeName` - used to diff the C++
	//installer's output tree against mep_recipe.py apply's without the
	//F6.4-only .mep-install.json stamp (not part of the recipe vocabulary).
	std::vector<std::string> ListRelativeFiles(const std::filesystem::path& root, const std::string& excludeName)
	{
		std::vector<std::string> result;
		std::error_code ec;
		for(auto it = std::filesystem::recursive_directory_iterator(root, ec); it != std::filesystem::recursive_directory_iterator(); it.increment(ec)) {
			if(ec || it->is_directory(ec) || it->path().filename() == excludeName) {
				continue;
			}
			result.push_back(std::filesystem::relative(it->path(), root).generic_string());
		}
		std::sort(result.begin(), result.end());
		return result;
	}

	//Byte-for-byte parity check between two installed pack trees (relative
	//path sets, then file contents); `detail` explains the first mismatch.
	bool DirsMatchByteForByte(const std::filesystem::path& a, const std::filesystem::path& b, std::string& detail)
	{
		std::vector<std::string> filesA = ListRelativeFiles(a, ".mep-install.json");
		std::vector<std::string> filesB = ListRelativeFiles(b, ".mep-install.json");
		if(filesA != filesB) {
			detail = "relative path sets differ (" + std::to_string(filesA.size()) + " vs " + std::to_string(filesB.size()) + " files)";
			return false;
		}
		for(const std::string& rel : filesA) {
			if(ReadFileBytes((a / rel).string()) != ReadFileBytes((b / rel).string())) {
				detail = "file contents differ: " + rel;
				return false;
			}
		}
		return true;
	}

	//Replaces the single expected occurrence of `from` with `to`; Check()s
	//that it was actually found, so a fixture reformat fails loudly here
	//instead of silently turning this into a no-op test.
	std::string ReplaceOnce(const std::string& text, const std::string& from, const std::string& to, const std::string& label)
	{
		size_t pos = text.find(from);
		Check(pos != std::string::npos, "BlocoE: " + label + " finds its anchor text in the golden recipe", "looked for '" + from + "'");
		return pos == std::string::npos ? text : text.substr(0, pos) + to + text.substr(pos + from.size());
	}

	//Renders a byte list as lowercase hex. Used only to spell out the FIPS
	//180-4 known-answer digests below as a byte array instead of a single
	//64-char hex string literal, since a contiguous run that long reads
	//as an opaque token to a generic secret scanner even though it is a
	//public, standardized test vector.
	std::string BytesToHex(std::initializer_list<uint8_t> bytes)
	{
		static const char* digits = "0123456789abcdef";
		std::string hex;
		for(uint8_t b : bytes) {
			hex += digits[b >> 4];
			hex += digits[b & 0x0f];
		}
		return hex;
	}

	void TestSha256KnownAnswer()
	{
		//FIPS 180-4 known-answer vectors: sha256("") and sha256("abc").
		std::string empty;
		std::string emptyDigest = BytesToHex({
			0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14, 0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
			0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c, 0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55 });
		Check(SHA256::GetHash((uint8_t*)empty.data(), empty.size()) == emptyDigest,
			"BlocoE: SHA256::GetHash matches the empty-string known-answer vector");
		std::string abc = "abc";
		std::string abcDigest = BytesToHex({
			0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea, 0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
			0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c, 0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad });
		Check(SHA256::GetHash((uint8_t*)abc.data(), abc.size()) == abcDigest,
			"BlocoE: SHA256::GetHash matches the 'abc' known-answer vector");
	}

	void TestFullDepsInstallMatchesPythonReference()
	{
		std::filesystem::path cppOut = MakeTempPackDir("recipe_full_deps_cpp");
		std::filesystem::path pyOut = MakeTempPackDir("recipe_full_deps_py");
		std::string recipeJson = ReadFileBytes(kFixtureDir + "/recipe.json");

		std::unordered_map<std::string, std::string> deps = { { "audio", kFixtureDir + "/audio-dep.zip" } };
		MepRecipeInstallResult result;
		bool ok = MepRecipeInstaller::Install(recipeJson, kFixtureDir + "/primary.zip", deps, "", cppOut.string(), result);
		Check(ok && result.Success, "BlocoE: full-deps Install() succeeds", result.Error);

		std::string cmd = "python3 scripts/mep_recipe.py apply '" + kFixtureDir + "/recipe.json' --primary '"
			+ kFixtureDir + "/primary.zip' --dep audio='" + kFixtureDir + "/audio-dep.zip' --out '" + pyOut.string() + "' >/dev/null 2>&1";
		Check(std::system(cmd.c_str()) == 0, "BlocoE: python3 scripts/mep_recipe.py apply (full deps) exits 0");

		std::string detail;
		Check(DirsMatchByteForByte(cppOut, pyOut, detail), "BlocoE: full-deps C++ install matches mep_recipe.py apply byte-for-byte", detail);

		std::error_code ec;
		std::filesystem::remove_all(cppOut, ec);
		std::filesystem::remove_all(pyOut, ec);
	}

	void TestMissingDepWithholdsPatchKeepsTextures()
	{
		std::filesystem::path out = MakeTempPackDir("recipe_missing_dep");
		std::string recipeJson = ReadFileBytes(kFixtureDir + "/recipe-missing-dep.json");

		MepRecipeInstallResult result;
		bool ok = MepRecipeInstaller::Install(recipeJson, kFixtureDir + "/primary.zip", {}, "", out.string(), result);
		Check(ok && result.Success, "BlocoE: missing-dep Install() still succeeds (policy tolerates it)", result.Error);

		Check(std::filesystem::exists(out / "hires.txt") && std::filesystem::exists(out / "tiles.png"),
			"BlocoE: missing-dep install still writes the textures that don't depend on the missing dep");
		Check(!std::filesystem::exists(out / "patches" / "game.ips"), "BlocoE: missing-dep install withholds the patch file");
		Check(!std::filesystem::exists(out / "audio" / "track01.ogg"), "BlocoE: missing-dep install withholds the renamed audio file too (transitive skip)");
		Check(ReadFileBytes((out / "pack.json").string()).find("\"patches\"") == std::string::npos,
			"BlocoE: missing-dep pack.json omits the 'patches' key entirely");
		Check(!result.Withheld.empty(), "BlocoE: missing-dep Install() reports a non-empty withheld set");

		std::error_code ec;
		std::filesystem::remove_all(out, ec);
	}

	void TestHashMismatchAbortsWritesNothing()
	{
		JsonReader reader;
		JsonValue root;
		std::string recipeJson = ReadFileBytes(kFixtureDir + "/recipe.json");
		reader.Parse(recipeJson, root);
		std::string realHash = root.Get("sources")->Get("primary")->GetString("sha256");
		std::string corrupted = realHash;
		corrupted[0] = (corrupted[0] == '0') ? '1' : '0'; //still 64 hex chars, guaranteed to differ

		std::string badRecipe = ReplaceOnce(recipeJson, realHash, corrupted, "hash-mismatch test");
		std::filesystem::path out = std::filesystem::temp_directory_path() / "mep_core_unit_tests_hash_mismatch";
		std::error_code ec;
		std::filesystem::remove_all(out, ec);

		MepRecipeInstallResult result;
		bool ok = MepRecipeInstaller::Install(badRecipe, kFixtureDir + "/primary.zip", {}, "", out.string(), result);
		Check(!ok && !result.Success && !result.Error.empty(), "BlocoE: a primary sha256 mismatch aborts Install()", result.Error);
		Check(!std::filesystem::exists(out), "BlocoE: a sha256 mismatch writes nothing to the output folder");
	}

	void TestUnknownOpAndVersionLogsAndSkips()
	{
		std::filesystem::path home = std::filesystem::temp_directory_path() / "mep_core_unit_tests_home";
		FolderUtilities::SetHomeFolder(home.string()); //MessageManager::Log needs a home folder to be set at all

		std::string recipeJson = ReadFileBytes(kFixtureDir + "/recipe.json");
		std::unordered_map<std::string, std::string> deps = { { "audio", kFixtureDir + "/audio-dep.zip" } };

		std::string badVersion = ReplaceOnce(recipeJson, "\"recipe\": 1,", "\"recipe\": 42,", "unknown-version test");
		MepRecipeInstallResult versionResult;
		bool versionOk = MepRecipeInstaller::Install(badVersion, kFixtureDir + "/primary.zip", deps, "", (std::filesystem::temp_directory_path() / "mep_core_unit_tests_bad_version").string(), versionResult);
		Check(!versionOk, "BlocoE: an unsupported recipe version aborts Install()");
		Check(MessageManager::GetLog().find("[MEP] recipe unsupported") != std::string::npos, "BlocoE: an unsupported recipe version logs '[MEP] recipe unsupported'");

		std::string badOp = ReplaceOnce(recipeJson, "\"ops\": [", "\"ops\": [{ \"op\": \"frobnicate\", \"from\": \"primary:hires.txt\", \"to\": \"unused.bin\" },", "unknown-op test");
		std::filesystem::path opOut = MakeTempPackDir("recipe_unknown_op");
		MepRecipeInstallResult opResult;
		bool opOk = MepRecipeInstaller::Install(badOp, kFixtureDir + "/primary.zip", deps, "", opOut.string(), opResult);
		Check(opOk && opResult.Success, "BlocoE: an unknown op is skipped rather than aborting the whole install", opResult.Error);
		Check(std::filesystem::exists(opOut / "hires.txt"), "BlocoE: the ops after an unknown op still run");
		Check(MessageManager::GetLog().find("[MEP] recipe unsupported: op 'frobnicate'") != std::string::npos, "BlocoE: an unknown op logs '[MEP] recipe unsupported'");

		std::error_code ec;
		std::filesystem::remove_all(opOut, ec);
		std::filesystem::remove_all(home, ec); //mesen.log/.1 written into it by MessageManager::Log
	}

	//F6.4c (ADR-0138 §39): the three primary-discovery edge cases must
	//resolve to the same installed tree on both interpreters. The wrapped
	//subfolder (ADR-0120 name-anchored) and the bare legacy probe basename
	//(ADR-0121) both need the identical non-empty romName on each side --
	//the C++ FindFallbackSubfolder is ROM-name-anchored while the Python
	//side also resolves structurally; the nested top-level zip resolves
	//with romName == "" on both.
	void TestDiscoveryEdgeCaseParity()
	{
		struct EdgeCase {
			const char* zip;
			const char* recipe;
			const char* romName;
		};
		const EdgeCase cases[] = {
			{ "wrapped-subfolder.zip", "recipe-wrapped-subfolder.json", "mep-recipe-fixture-rom" },
			{ "nested-zip.zip",        "recipe-nested-zip.json",        "" },
			{ "bare-probe.zip",        "recipe-bare-probe.json",        "mep-recipe-fixture-rom" },
		};
		for(const EdgeCase& c : cases) {
			std::string label = std::string("BlocoE[") + c.zip + "]";
			std::filesystem::path cppOut = MakeTempPackDir(std::string("recipe_edge_cpp_") + c.zip);
			std::filesystem::path pyOut = MakeTempPackDir(std::string("recipe_edge_py_") + c.zip);
			std::string recipeJson = ReadFileBytes(kFixtureDir + "/" + c.recipe);
			std::unordered_map<std::string, std::string> deps = { { "audio", kFixtureDir + "/audio-dep.zip" } };

			MepRecipeInstallResult result;
			bool ok = MepRecipeInstaller::Install(recipeJson, kFixtureDir + "/" + c.zip, deps, c.romName, cppOut.string(), result);
			Check(ok && result.Success, label + " Install() succeeds", result.Error);

			std::string cmd = "python3 scripts/mep_recipe.py apply '" + kFixtureDir + "/" + c.recipe + "' --primary '"
				+ kFixtureDir + "/" + c.zip + "' --dep audio='" + kFixtureDir + "/audio-dep.zip' --out '" + pyOut.string() + "'";
			if(c.romName[0] != '\0') {
				cmd += " --rom-name '" + std::string(c.romName) + "'";
			}
			cmd += " >/dev/null 2>&1";
			Check(std::system(cmd.c_str()) == 0, label + " mep_recipe.py apply exits 0");

			std::string detail;
			Check(DirsMatchByteForByte(cppOut, pyOut, detail), label + " C++ install matches mep_recipe.py apply byte-for-byte", detail);

			std::error_code ec;
			std::filesystem::remove_all(cppOut, ec);
			std::filesystem::remove_all(pyOut, ec);
		}
	}

	//--- Bloco F: F5.4g Bloco B (ADR-0052 items 3/4/6 + channel steal) --------
	//Arpeggio→chord folding (item 3), expression family (item 4), per-channel
	//FixedRole override (item 6) and HandleChannelSteal (item 2's "stolen and
	//handed back"). Pure logic - no emulator, no SoundFont file.

	void TestFoldArpeggioToChord()
	{
		//A C-E-G arpeggio (MIDI 60, 64, 67) folds into a C-E-G sustained chord,
		//frequencies lowest first (C4 < E4 < G4)
		int cycle[3] = { 60, 64, 67 };
		double chord[EnhancedSynthEngine::MaxChordNotes];
		uint32_t count = EnhancedSynthEngine::FoldArpeggioToChord(cycle, 3, chord);
		Check(count == 3, "BlocoF: a 3-note arpeggio folds into a 3-note chord");
		bool notesMatch = count >= 3
			&& std::abs(chord[0] - NoteToFreq(60.0)) < 0.01
			&& std::abs(chord[1] - NoteToFreq(64.0)) < 0.01
			&& std::abs(chord[2] - NoteToFreq(67.0)) < 0.01;
		Check(notesMatch, "BlocoF: chord frequencies match the cycle's notes, sorted lowest-first");

		//Unsorted input is sorted ascending
		int shuffled[3] = { 67, 60, 64 };
		count = EnhancedSynthEngine::FoldArpeggioToChord(shuffled, 3, chord);
		Check(count >= 3 && chord[0] < chord[1] && chord[1] < chord[2], "BlocoF: fold sorts the chord lowest-first regardless of input order");

		//Empty cycle = single note, no chord
		count = EnhancedSynthEngine::FoldArpeggioToChord(cycle, 0, chord);
		Check(count == 0, "BlocoF: an empty cycle folds to no chord");
	}

	void TestEvaluateExpression()
	{
		//A note falling fast after its onset with little oscillation is a pluck
		EnhancedSynthEngine::ExpressionEnvelope pluck = EnhancedSynthEngine::EvaluateExpression(2.0, 0.3, 0.5);
		Check(pluck.Family == EnhancedSynthEngine::ExpressionEnvelope::FamilyPluck, "BlocoF: fast decay + little vibrato classifies as pluck");
		//Sustained tone, no oscillation, slow glide -> sustained
		EnhancedSynthEngine::ExpressionEnvelope sustained = EnhancedSynthEngine::EvaluateExpression(0.2, 0.2, 0.8);
		Check(sustained.Family == EnhancedSynthEngine::ExpressionEnvelope::FamilySustained, "BlocoF: slow decay + no oscillation classifies as sustained");
		//Vibrato-heavy held note -> strings
		EnhancedSynthEngine::ExpressionEnvelope strings = EnhancedSynthEngine::EvaluateExpression(0.1, 1.8, 0.3);
		Check(strings.Family == EnhancedSynthEngine::ExpressionEnvelope::FamilyStrings, "BlocoF: vibrato-heavy tone classifies as strings");
		//Fast portamento -> strings (a sliding line)
		EnhancedSynthEngine::ExpressionEnvelope slide = EnhancedSynthEngine::EvaluateExpression(0.1, 0.3, 6.0);
		Check(slide.Family == EnhancedSynthEngine::ExpressionEnvelope::FamilyStrings, "BlocoF: a fast portamento classifies as strings");
	}

	void TestFixedRoleOverride()
	{
		//With auto roles on, a FixedRole override pins channel 0 to Bass even
		//though its default is Lead and it plays high the whole time
		static constexpr ChannelRoleClassifier::ChannelRole defaults[2] = { ChannelRoleClassifier::ChannelRole::Lead, ChannelRoleClassifier::ChannelRole::Harmony };
		ChannelRoleClassifier roles;
		roles.Init(2, defaults);
		int32_t fixedRoles[4] = { 2, -1, -1, -1 }; //channel 0 forced to Bass
		roles.SetFixedRoles(fixedRoles);
		ChannelRoleClassifier::Channel ch[2] = {
			{ NoteToFreq(84.0), 0.8, false }, //high, steady - would normally be Lead
			{ NoteToFreq(48.0), 0.8, false }, //low
		};
		for(int i = 0; i < 400; i++) {
			roles.Update(ch, 0.01);
		}
		Check(roles.Role(0) == ChannelRoleClassifier::ChannelRole::Bass, "BlocoF: FixedRole pins channel 0 to Bass despite a high mean pitch");
		Check(roles.HasFixedRole(0) && !roles.HasFixedRole(1), "BlocoF: HasFixedRole reports the pinned channel only");
	}

	void TestChannelStealRestore()
	{
		//Composer swap-back (ADR-0052 item 2): channel 0 (default Lead) leads,
		//falls silent long enough for the classifier to hand Lead to channel 1;
		//the moment channel 0 resumes, Lead is restored instantly - no full
		//hysteresis re-classification cycle.
		static constexpr ChannelRoleClassifier::ChannelRole defaults[3] = { ChannelRoleClassifier::ChannelRole::Lead, ChannelRoleClassifier::ChannelRole::Harmony, ChannelRoleClassifier::ChannelRole::Bass };
		ChannelRoleClassifier roles;
		roles.Init(3, defaults);
		ChannelRoleClassifier::Channel ch[3] = {
			{ NoteToFreq(72.0), 0.8, false }, //lead melody
			{ NoteToFreq(55.0), 0.8, false }, //harmony
			{ NoteToFreq(36.0), 0.8, false }, //bass
		};
		for(int i = 0; i < 300; i++) {
			roles.Update(ch, 0.01);
		}
		Check(roles.Role(0) == ChannelRoleClassifier::ChannelRole::Lead, "BlocoF: channel 0 holds the lead before the steal");

		//Channel 0 falls silent while channel 1 carries a high line (3s - long
		//enough for the classifier to reassign Lead to channel 1)
		ch[0].Vol = 0;
		ch[1] = { NoteToFreq(79.0), 0.8, false };
		for(int i = 0; i < 300; i++) {
			roles.Update(ch, 0.01);
		}
		Check(roles.Role(1) == ChannelRoleClassifier::ChannelRole::Lead, "BlocoF: the classifier hands Lead to channel 1 while channel 0 is out");

		//Channel 0 resumes - the stolen role is handed back on this first flush
		ch[0] = { NoteToFreq(72.0), 0.8, false };
		ch[1] = { NoteToFreq(55.0), 0.8, false };
		roles.Update(ch, 0.01);
		Check(roles.Role(0) == ChannelRoleClassifier::ChannelRole::Lead, "BlocoF: HandleChannelSteal restores the lead instantly on resume");
	}

	void TestArpeggioKeysDetection()
	{
		//A 50 Hz C-E alternation (one pitch change per 2 flushes at dt=0.01) is
		//a fast arpeggio (item 3), not SFX - the classifier exposes its cycle
		//for the engine's chord folding
		ChannelRoleClassifier roles = MakeLeadOnlyClassifier();
		ChannelRoleClassifier::Channel ch { NoteToFreq(60.0), 0.8, false };
		bool high = false;
		for(int i = 0; i < 60; i++) { //0.6s of alternation
			if((i & 1) == 0) {
				high = !high; //pitch changes every 2 flushes -> 50 Hz cycle
			}
			ch.Freq = NoteToFreq(high ? 64.0 : 60.0);
			roles.Update(&ch, 0.01);
		}
		int keys[4] = { 0, 0, 0, 0 };
		uint32_t count = roles.ArpeggioKeys(0, keys);
		Check(count == 2, "BlocoF: a 50 Hz C-E alternation is detected as a 2-note arpeggio");
		bool hasC = count >= 2 && (std::abs(keys[0] - 60) <= 1 || std::abs(keys[1] - 60) <= 1);
		bool hasE = count >= 2 && (std::abs(keys[0] - 64) <= 1 || std::abs(keys[1] - 64) <= 1);
		Check(hasC && hasE, "BlocoF: the arpeggio cycle is the two alternating notes");
	}

	//--- Bloco G: MepContentId golden parity (ADR-0139/P.1) ----------------
	//The Core hasher and the normative Python hasher (scripts/mep_content_id.py)
	//must agree on the SAME goldens: docs/specs/golden/mep-content-id.json is
	//run by both sides (the Python side via scripts/test_mep_content_id_golden.py,
	//this block via MepContentId) so the two implementations can never drift.
	void TestContentIdGoldenParity()
	{
		JsonValue root;
		JsonReader reader;
		if(!reader.Parse(ReadFileBytes("docs/specs/golden/mep-content-id.json"), root) || !root.IsObject()) {
			Check(false, "BlocoG: the content_id golden parses as JSON", reader.GetError());
			return;
		}
		const JsonValue* fixtures = root.Get("fixtures");
		if(!fixtures || !fixtures->IsArray()) {
			Check(false, "BlocoG: the content_id golden has a fixtures array");
			return;
		}
		for(const JsonValue& fx : fixtures->GetArray()) {
			std::string name = fx.GetString("name");
			std::string kind = fx.GetString("kind");
			std::string expected = fx.GetString("expected_content_id");
			if(kind == "tree") {
				std::vector<MepContentId::Entry> entries;
				const JsonValue* list = fx.Get("entries");
				for(const JsonValue& e : list->GetArray()) {
					std::string data = e.GetString("data");
					if(e.GetString("encoding") == "base64") {
						entries.push_back({ e.GetString("path"), Base64::Decode(data) });
					} else {
						entries.push_back({ e.GetString("path"), std::vector<uint8_t>(data.begin(), data.end()) });
					}
				}
				std::string got = MepContentId::ComputeTree(entries);
				Check(got == expected, "BlocoG: tree fixture '" + name + "' matches golden", got + " != " + expected);
			} else if(kind == "recipe") {
				unordered_map<string, string> deps;
				const JsonValue* d = fx.Get("deps");
				for(const auto& member : d->GetObject()) {
					deps[member.first] = member.second.GetString();
				}
				std::string got = MepContentId::ComputeRecipe(fx.GetString("primary_tree_hash"), fx.GetString("recipe_hash"), deps);
				Check(got == expected, "BlocoG: recipe fixture '" + name + "' matches golden", got + " != " + expected);
			}
		}
	}

	void TestMepContentIdComputeFolder()
	{
		//ADR-0147: ComputeFolder must be stable against the host's own install
		//metadata (.mep-install.json / .bootstrap), so a reinstall does not look
		//like a user edit, while a real content change does.
		std::filesystem::path dir = std::filesystem::temp_directory_path() / "mep_contentid_folder_test";
		std::error_code ec;
		std::filesystem::remove_all(dir, ec);
		std::filesystem::create_directories(dir / "textures", ec);
		std::ofstream(dir / "textures" / "hires.txt", std::ios::out | std::ios::binary) << "<ver>106\n";
		std::ofstream(dir / ".mep-install.json", std::ios::out | std::ios::binary) << "{\"installed_at\":\"A\"}\n";

		std::string base = MepContentId::ComputeFolder(dir.string());
		Check(!base.empty(), "BlocoG: ComputeFolder hashes a real directory tree");

		//Reinstall rewrites .mep-install.json (installed_at changes) - must NOT change the baseline
		std::ofstream(dir / ".mep-install.json", std::ios::out | std::ios::binary) << "{\"installed_at\":\"B\"}\n";
		Check(MepContentId::ComputeFolder(dir.string()) == base, "BlocoG: .mep-install.json is excluded from the baseline (a reinstall is not an edit)");

		//A real content edit DOES change the baseline
		std::ofstream(dir / "textures" / "hires.txt", std::ios::out | std::ios::binary) << "<ver>106\n<img>different.png\n";
		Check(MepContentId::ComputeFolder(dir.string()) != base, "BlocoG: editing textures changes the baseline (an edit is detected)");

		std::filesystem::remove_all(dir, ec);
	}
}

//--- Bloco H: FingerprintStore loop field round-trip (ADR-0134 Option A) ------
//F5.4g Block C item 8: fingerprints.json's optional `loop` point (PCM
//samples at the OGG's own rate). Absence/zero means loop-the-whole-file;
//a malformed value falls back to 0 (the host tolerates it, MEP-v1 §5.2);
//Save emits the field only when non-zero.
namespace
{
	std::string FingerprintJson(const std::string& extra)
	{
		return "{\"version\":1,\"tracks\":[{\"id\":\"t1\",\"kind\":\"bgm\",\"frames\":1200"
			+ (extra.empty() ? "" : "," + extra)
			+ ",\"events\":[[0,0,0],[1,2,8],[2,-1,16],[3,4,24]]}]}";
	}
	void TestFingerprintLoopLoad()
	{
		std::string error;
		std::vector<AudioFingerprint> out;
		Check(FingerprintStore::Load(WriteTempFile("fp_loop.json", FingerprintJson("\"loop\":441000")), out, error),
			"BlocoH: fingerprints.json with loop loads");
		Check(out.size() == 1 && out[0].Loop == 441000, "BlocoH: loop parsed to AudioFingerprint::Loop", std::to_string(out.empty() ? -1 : (int)out[0].Loop));
	}
	void TestFingerprintLoopAbsent()
	{
		std::string error;
		std::vector<AudioFingerprint> out;
		Check(FingerprintStore::Load(WriteTempFile("fp_no_loop.json", FingerprintJson("")), out, error),
			"BlocoH: fingerprints.json without loop loads");
		Check(out.size() == 1 && out[0].Loop == 0, "BlocoH: absent loop defaults to 0");
	}
	void TestFingerprintLoopMalformed()
	{
		std::string error;
		std::vector<AudioFingerprint> out;
		//A non-numeric `loop` is ignored (fallback 0), matching MEP-v1 §5.2's
		//"ignore an unknown/malformed field rather than reject the pack".
		Check(FingerprintStore::Load(WriteTempFile("fp_bad_loop.json", FingerprintJson("\"loop\":\"oops\"")), out, error),
			"BlocoH: malformed loop does not reject the pack");
		Check(out.size() == 1 && out[0].Loop == 0, "BlocoH: malformed loop falls back to 0");
	}
	void TestFingerprintLoopSave()
	{
		std::vector<AudioFingerprint> tracks;
		AudioFingerprint fp;
		fp.Id = "t1"; fp.Kind = "bgm"; fp.Frames = 1200; fp.Loop = 441000;
		fp.Events.push_back({ 0, 0, 0 });
		tracks.push_back(fp);
		std::string path = WriteTempFile("fp_save.json", "");
		Check(FingerprintStore::Save(path, tracks), "BlocoH: Save writes the file");
		std::string text = ReadFileBytes(path);
		Check(text.find("\"loop\": 441000") != std::string::npos, "BlocoH: Save emits the loop point when non-zero", text);

		fp.Loop = 0;
		tracks[0] = fp;
		path = WriteTempFile("fp_save0.json", "");
		Check(FingerprintStore::Save(path, tracks), "BlocoH: Save writes the file (loop 0)");
		std::string text0 = ReadFileBytes(path);
		Check(text0.find("loop") == std::string::npos, "BlocoH: Save omits the loop field when zero", text0);
	}
	//--- Bloco H: BorderLayout (ADR-0149, Slice F8.3b) -------------------------
	//Host-free viewport/canvas math extracted from VideoRenderer so the border
	//layer's layout rules are pinned without linking the Emulator.

	std::string RectStr(const BorderRect& r)
	{
		return "(" + std::to_string(r.X) + "," + std::to_string(r.Y) + " " + std::to_string(r.Width) + "x" + std::to_string(r.Height) + ")";
	}

	void CheckRect(const BorderRect& got, int32_t x, int32_t y, uint32_t w, uint32_t h, const std::string& name)
	{
		BorderRect want;
		want.X = x;
		want.Y = y;
		want.Width = w;
		want.Height = h;
		Check(got == want, name, "got " + RectStr(got) + " want " + RectStr(want));
	}

	void TestBorderDefaultHeuristic()
	{
		//No border.json: 16:9 canvas gets a 4:3, full-height, centred viewport
		BorderLayout l = BorderLayout::ForCanvas(1920, 1080);
		Check(l.ViewportWidth == 1440 && l.ViewportHeight == 1080, "BlocoH: default viewport is 4:3 at full canvas height",
			std::to_string(l.ViewportWidth) + "x" + std::to_string(l.ViewportHeight));
		Check(l.ViewportX == 240 && l.ViewportY == 0, "BlocoH: default viewport is horizontally centred",
			std::to_string(l.ViewportX) + "," + std::to_string(l.ViewportY));
		Check(l.ScaleMode == BorderScaleMode::Fit && !l.Underlay, "BlocoH: defaults are scale_mode=fit, underlay=false");
		Check(l.IsViewportInsideCanvas(), "BlocoH: default viewport lies inside the canvas");

		//Canvas narrower than 4:3: viewport is clamped to X=0 (never negative)
		BorderLayout narrow = BorderLayout::ForCanvas(600, 600);
		Check(narrow.ViewportX == 0 && narrow.ViewportWidth == 800, "BlocoH: default viewport on narrow canvas starts at X=0 and overflows",
			std::to_string(narrow.ViewportX) + "/" + std::to_string(narrow.ViewportWidth));
		Check(!narrow.IsViewportInsideCanvas(), "BlocoH: overflowing default viewport is reported outside the canvas");
		CheckRect(narrow.ClampedViewport(), 0, 0, 600, 600, "BlocoH: overflowing default viewport clamps to the canvas");

		//Authored viewport wins over the heuristic
		BorderLayout authored;
		authored.CanvasWidth = 1920;
		authored.CanvasHeight = 1080;
		authored.ViewportX = 100;
		authored.ViewportY = 50;
		authored.ViewportWidth = 1000;
		authored.ViewportHeight = 900;
		authored.ApplyDefaultViewportIfMissing();
		CheckRect(authored.ClampedViewport(), 100, 50, 1000, 900, "BlocoH: authored viewport is kept as-is");

		//A viewport with one zero dimension counts as invalid -> heuristic
		BorderLayout half;
		half.CanvasWidth = 1920;
		half.CanvasHeight = 1080;
		half.ViewportWidth = 500;
		half.ViewportHeight = 0;
		half.ApplyDefaultViewportIfMissing();
		Check(half.ViewportWidth == 1440 && half.ViewportHeight == 1080 && half.ViewportX == 240, "BlocoH: zero-height viewport falls back to the heuristic");
	}

	void TestBorderParseScaleMode()
	{
		BorderScaleMode mode = BorderScaleMode::Fit;
		Check(BorderLayout::ParseScaleMode("stretch", mode) && mode == BorderScaleMode::Stretch, "BlocoH: scale_mode 'stretch' parses");
		Check(BorderLayout::ParseScaleMode("fit", mode) && mode == BorderScaleMode::Fit, "BlocoH: scale_mode 'fit' parses");
		mode = BorderScaleMode::Stretch;
		Check(!BorderLayout::ParseScaleMode("Fit", mode) && mode == BorderScaleMode::Stretch, "BlocoH: unknown scale_mode is rejected and leaves the value untouched");
		Check(!BorderLayout::ParseScaleMode("", mode), "BlocoH: empty scale_mode is rejected");
	}

	void TestBorderFitLetterboxing()
	{
		BorderLayout l = BorderLayout::ForCanvas(1920, 1080);

		//Same aspect: fills the output exactly
		CheckRect(l.CanvasRectOnOutput(1920, 1080), 0, 0, 1920, 1080, "BlocoH: fit on a same-aspect output fills it");
		CheckRect(l.CanvasRectOnOutput(960, 540), 0, 0, 960, 540, "BlocoH: fit on a half-size output scales down");

		//Wider output (21:9): full height, pillarboxed and centred
		CheckRect(l.CanvasRectOnOutput(2560, 1080), 320, 0, 1920, 1080, "BlocoH: fit on a wider output pillarboxes");
		//Taller output (4:3): full width, letterboxed and centred
		CheckRect(l.CanvasRectOnOutput(1920, 1440), 0, 180, 1920, 1080, "BlocoH: fit on a taller output letterboxes");

		//Game viewport follows the canvas rect
		CheckRect(l.ViewportRectOnOutput(1920, 1080), 240, 0, 1440, 1080, "BlocoH: viewport on same-aspect output equals the canvas viewport");
		CheckRect(l.ViewportRectOnOutput(960, 540), 120, 0, 720, 540, "BlocoH: viewport scales with the canvas on a half-size output");
		CheckRect(l.ViewportRectOnOutput(2560, 1080), 560, 0, 1440, 1080, "BlocoH: viewport is offset by the pillarbox");
		CheckRect(l.ViewportRectOnOutput(1920, 1440), 240, 180, 1440, 1080, "BlocoH: viewport is offset by the letterbox");

		//Aspect is preserved in fit mode: 4:3 viewport stays 4:3 on every output
		//(integer rounding: 1600 * 4/3 = 2133.33, so allow a 1px slack)
		BorderRect vp = l.ViewportRectOnOutput(3840, 1600);
		int64_t aspectErr = (int64_t)vp.Width * 3 - (int64_t)vp.Height * 4;
		Check(aspectErr >= -4 && aspectErr <= 4, "BlocoH: fit preserves the 4:3 game aspect on an odd output (within 1px)", RectStr(vp));

		//Degenerate inputs never produce a rect
		CheckRect(l.CanvasRectOnOutput(0, 1080), 0, 0, 0, 0, "BlocoH: zero-width output yields an empty rect");
		CheckRect(BorderLayout().CanvasRectOnOutput(1920, 1080), 0, 0, 0, 0, "BlocoH: zero-size canvas yields an empty rect");
	}

	void TestBorderStretch()
	{
		BorderLayout l = BorderLayout::ForCanvas(1920, 1080);
		l.ScaleMode = BorderScaleMode::Stretch;
		CheckRect(l.CanvasRectOnOutput(2560, 1080), 0, 0, 2560, 1080, "BlocoH: stretch fills a wider output");
		CheckRect(l.CanvasRectOnOutput(1920, 1440), 0, 0, 1920, 1440, "BlocoH: stretch fills a taller output");
		//Viewport is stretched along with the canvas (aspect is NOT preserved)
		CheckRect(l.ViewportRectOnOutput(2560, 1080), 320, 0, 1920, 1080, "BlocoH: stretch scales the viewport horizontally");
		CheckRect(l.ViewportRectOnOutput(1920, 1440), 240, 0, 1440, 1440, "BlocoH: stretch scales the viewport vertically");
	}

	void TestBorderViewportClamping()
	{
		BorderLayout l;
		l.CanvasWidth = 100;
		l.CanvasHeight = 50;

		//Negative origin: clipped to 0
		l.ViewportX = -10;
		l.ViewportY = -5;
		l.ViewportWidth = 30;
		l.ViewportHeight = 20;
		Check(!l.IsViewportInsideCanvas(), "BlocoH: negative viewport origin is outside the canvas");
		CheckRect(l.ClampedViewport(), 0, 0, 20, 15, "BlocoH: negative viewport origin clamps to the canvas origin");

		//Overflowing far edge: clipped to canvas size
		l.ViewportX = 90;
		l.ViewportY = 40;
		Check(!l.IsViewportInsideCanvas(), "BlocoH: viewport past the far edge is outside the canvas");
		CheckRect(l.ClampedViewport(), 90, 40, 10, 10, "BlocoH: viewport past the far edge clamps to the canvas size");

		//Fully outside: empty
		l.ViewportX = 200;
		l.ViewportY = 0;
		CheckRect(l.ClampedViewport(), 0, 0, 0, 0, "BlocoH: viewport fully outside the canvas is empty");
		CheckRect(l.ViewportRectOnOutput(200, 100), 0, 0, 0, 0, "BlocoH: viewport fully outside the canvas maps to nothing on the output");

		//Exactly on the edge is still inside
		l.ViewportX = 60;
		l.ViewportY = 30;
		l.ViewportWidth = 40;
		l.ViewportHeight = 20;
		Check(l.IsViewportInsideCanvas(), "BlocoH: viewport touching the far edge is inside the canvas");

		//Drawing never writes outside the canvas buffer: paint a 2x2 game
		//into a viewport that overhangs every edge and check only the
		//canvas cells changed (the guard cells around it stay intact)
		BorderLayout small;
		small.CanvasWidth = 4;
		small.CanvasHeight = 4;
		small.ViewportX = -2;
		small.ViewportY = -2;
		small.ViewportWidth = 8;
		small.ViewportHeight = 8;
		std::vector<uint32_t> buf(16 + 2, 0xCAFEBABE); //16 canvas cells + 2 guard cells
		uint32_t game[4] = { 0xFF000001, 0xFF000002, 0xFF000003, 0xFF000004 };
		BorderDrawGameIntoViewport(buf.data(), small, game, 2, 2);
		bool guardsIntact = buf[16] == 0xCAFEBABE && buf[17] == 0xCAFEBABE;
		Check(guardsIntact, "BlocoH: overhanging viewport never writes past the canvas buffer");
		bool allPainted = true;
		for(int i = 0; i < 16; i++) {
			if(buf[i] == 0xCAFEBABE) {
				allPainted = false;
			}
		}
		Check(allPainted, "BlocoH: overhanging viewport still paints every canvas cell it covers");
		//Viewport cell (2,2) (canvas 0,0) samples game pixel (2*2/8, 2*2/8) = (0,0)
		Check(buf[0] == 0xFF000001 && buf[15] == 0xFF000004, "BlocoH: overhanging viewport samples the game with nearest-neighbour",
			std::to_string(buf[0]) + "/" + std::to_string(buf[15]));
	}

	void TestBorderBlendOver()
	{
		Check(BorderBlendOver(0xFF112233, 0x00FFFFFF) == 0xFF112233, "BlocoH: alpha 0 border leaves the game pixel untouched");
		Check(BorderBlendOver(0xFF112233, 0xFFAABBCC) == 0xFFAABBCC, "BlocoH: alpha 255 border replaces the game pixel");
		//50% white over opaque black: (255*128 + 0*127)/255 = 128 per channel, alpha stays 255
		uint32_t mid = BorderBlendOver(0xFF000000, 0x80FFFFFF);
		Check(mid == 0xFF808080, "BlocoH: mid alpha blends channels with integer source-over", std::to_string(mid));
		//50% over a transparent destination: alpha accumulates, colour is scaled
		uint32_t onClear = BorderBlendOver(0x00000000, 0x80FFFFFF);
		Check(onClear == 0x80808080, "BlocoH: mid alpha over transparent keeps the border's alpha", std::to_string(onClear));
		//Alpha 1 barely changes the destination but never overflows a channel
		uint32_t tiny = BorderBlendOver(0xFFFFFFFF, 0x01000000);
		Check(tiny == 0xFFFEFEFE, "BlocoH: alpha 1 black over white darkens by one step", std::to_string(tiny));
	}

	void TestBorderCompositeOrdering()
	{
		//2x2 canvas; viewport = right column (x=1, w=1, h=2); 1x1 game frame
		BorderLayout l;
		l.CanvasWidth = 2;
		l.CanvasHeight = 2;
		l.ViewportX = 1;
		l.ViewportY = 0;
		l.ViewportWidth = 1;
		l.ViewportHeight = 2;
		//Border: opaque red on the left column, 50% white on the right column
		uint32_t border[4] = { 0xFFFF0000, 0x80FFFFFF, 0xFFFF0000, 0x80FFFFFF };
		uint32_t game[1] = { 0xFF000000 };
		uint32_t dst[4];

		//Overlay (default): border blends over the game inside the viewport
		l.Underlay = false;
		BorderCompositeFrame(dst, border, l, game, 1, 1);
		Check(dst[0] == 0xFFFF0000 && dst[2] == 0xFFFF0000, "BlocoH: overlay keeps the opaque border outside the viewport");
		Check(dst[1] == 0xFF808080 && dst[3] == 0xFF808080, "BlocoH: overlay blends the translucent border over the game", std::to_string(dst[1]));

		//Underlay: game is copied strictly over the viewport, border untouched elsewhere
		l.Underlay = true;
		BorderCompositeFrame(dst, border, l, game, 1, 1);
		Check(dst[0] == 0xFFFF0000 && dst[2] == 0xFFFF0000, "BlocoH: underlay keeps the border outside the viewport");
		Check(dst[1] == 0xFF000000 && dst[3] == 0xFF000000, "BlocoH: underlay draws the game verbatim over the viewport (no blend)", std::to_string(dst[1]));

		//Overlay outside the viewport starts from transparent black, so a
		//translucent border there is NOT lifted by any game pixel
		l.Underlay = false;
		uint32_t border2[4] = { 0x80FFFFFF, 0x80FFFFFF, 0x80FFFFFF, 0x80FFFFFF };
		BorderCompositeFrame(dst, border2, l, game, 1, 1);
		Check(dst[0] == 0x80808080, "BlocoH: overlay outside the viewport blends over transparent black", std::to_string(dst[0]));
		Check(dst[1] == 0xFF808080, "BlocoH: overlay inside the viewport blends over the game", std::to_string(dst[1]));
	}
}

//--- Bloco I: OggMixer BGM crossfade ramp (ADR-0142) -------------------------
//The shipped fade was block-stepped: MixAudio computed one uint8_t volume per
//call and applied it to the whole block, so at the real 735-sample block size
//the 1764-sample window was 2-3 steps of ~40% - a quieter click, not a
//crossfade (https://github.com/sbihaiko/MesenCE/issues/151). The volume is now
//interpolated per sample (OggFadeRamp::MixSamples, the same kernel OggReader
//uses). The mixer is driven here through IOggSource stubs of constant
//amplitude, so the case needs no stb_vorbis, no VirtualFile and no Emulator.
namespace
{
	constexpr uint32_t kFadeSamples = 1764; //OggMixer::kBgmFadeSamples
	constexpr uint32_t kBlockSamples = 735; //one NTSC frame at 44.1kHz - the real MixAudio block
	constexpr double kMixVolume = 128.0;    //OggMixer::Reset's default _bgmVolume
	constexpr double kAmpA = 6000.0;
	constexpr double kAmpB = 9000.0;

	//A source of constant amplitude that mixes through the production ramp
	//kernel and, like OggReader, produces nothing on run-ahead frames.
	class ConstantOggSource : public IOggSource
	{
	private:
		int16_t _amplitude;
		const bool* _runAhead;
		std::vector<int16_t> _scratch;

	public:
		uint32_t MixedFrames = 0;

		ConstantOggSource(int16_t amplitude, const bool* runAhead) : _amplitude(amplitude), _runAhead(runAhead) {}

		bool IsPlaybackOver() override { return false; }
		void SetSampleRate(int sampleRate) override {}
		void SetLoopFlag(bool loop) override {}
		uint32_t GetOffset() override { return MixedFrames; }

		void ApplySamples(int16_t* buffer, size_t sampleCount, uint8_t volumeStart, uint8_t volumeEnd) override
		{
			if(*_runAhead) {
				return;
			}
			_scratch.assign(sampleCount * 2, _amplitude);
			OggFadeRamp::MixSamples(buffer, _scratch.data(), (uint32_t)sampleCount, (uint32_t)sampleCount, volumeStart, volumeEnd);
			MixedFrames += (uint32_t)sampleCount;
		}
	};

	//Expected mixed level of one source at fade factor `fade` (the mixer scales
	//by _bgmVolume, the source by volume/255).
	double FadedLevel(double amplitude, double fade)
	{
		return amplitude * (kMixVolume * fade) / 255.0;
	}

	struct CrossfadeRun
	{
		bool RunAhead = false;
		std::vector<int16_t> Left;
		std::vector<std::shared_ptr<ConstantOggSource>> Sources;

		OggMixer::SourceFactory Factory()
		{
			return [this](string filename, bool loop, uint32_t sampleRate, uint32_t startOffset, uint32_t loopPosition) -> shared_ptr<IOggSource> {
				auto source = std::make_shared<ConstantOggSource>((int16_t)(filename == "A" ? kAmpA : kAmpB), &RunAhead);
				Sources.push_back(source);
				return source;
			};
		}

		void MixBlock(OggMixer& mixer)
		{
			std::vector<int16_t> out(kBlockSamples * 2, 0);
			mixer.MixAudio(out.data(), kBlockSamples, 44100);
			for(uint32_t f = 0; f < kBlockSamples; f++) {
				Left.push_back(out[f * 2]);
			}
		}
	};

	//Records A fading in, A->B crossfading, then B fading out on StopBgm.
	//`runAheadBlock` (when >= 0) inserts one run-ahead block before that block
	//index of the fade-in, which must produce silence and must not advance the
	//fade counters.
	void RecordCrossfade(CrossfadeRun& run, int runAheadBlock)
	{
		OggMixer mixer([&run]() { return run.RunAhead; }, run.Factory());
		mixer.Reset(44100);

		mixer.Play("A", false, 0, 0);
		for(int i = 0; i < 5; i++) {
			if(i == runAheadBlock) {
				run.RunAhead = true;
				std::vector<int16_t> out(kBlockSamples * 2, 0);
				mixer.MixAudio(out.data(), kBlockSamples, 44100);
				bool silent = true;
				for(int16_t sample : out) {
					silent = silent && sample == 0;
				}
				Check(silent, "BlocoI: a run-ahead block produces no audio");
				run.RunAhead = false;
			}
			run.MixBlock(mixer);
		}
		mixer.Play("B", false, 0, 0);
		for(int i = 0; i < 5; i++) {
			run.MixBlock(mixer);
		}
		mixer.StopBgm();
		for(int i = 0; i < 5; i++) {
			run.MixBlock(mixer);
		}
	}

	void TestBgmCrossfadeIsPerSampleRamp()
	{
		CrossfadeRun run;
		RecordCrossfade(run, -1);
		const std::vector<int16_t>& left = run.Left;
		const size_t switchAt = 5 * kBlockSamples;
		const size_t stopAt = 10 * kBlockSamples;

		//(a) No sample-to-sample jump larger than the two linear ramps can
		//produce. The old block-stepped code jumped ~1250 here (0.42 * a full
		//block volume step); the ramp's own slope is under 5.
		double maxJump = (kAmpA + kAmpB) * (kMixVolume / 255.0) / kFadeSamples + 2.0;
		int worstJump = 0;
		size_t worstAt = 0;
		for(size_t i = 1; i < left.size(); i++) {
			int delta = std::abs((int)left[i] - (int)left[i - 1]);
			if(delta > worstJump) {
				worstJump = delta;
				worstAt = i;
			}
		}
		Check(worstJump <= maxJump, "BlocoI: no sample-to-sample jump beyond the linear ramp slope",
			"worst " + std::to_string(worstJump) + " at " + std::to_string(worstAt) + ", allowed " + std::to_string(maxJump));

		//(b) The envelope tracks the expected linear curves. Tolerance covers
		//the 8-bit quantisation of the per-block endpoint volumes: one LSB of
		//volume is amplitude/255 of level (~0.8% of the loudest source here,
		//against the ~1250 step the block-stepped fade produced).
		double tolerance = kAmpB / 255.0 + 2.0;
		double worstFadeIn = 0;
		for(uint32_t t = 0; t < kFadeSamples; t++) {
			worstFadeIn = std::max(worstFadeIn, std::abs(left[t] - FadedLevel(kAmpA, (double)t / kFadeSamples)));
		}
		Check(worstFadeIn <= tolerance, "BlocoI: fade-in follows the linear 0->1 ramp over kBgmFadeSamples",
			"worst " + std::to_string(worstFadeIn) + " > " + std::to_string(tolerance));

		Check(std::abs(left[switchAt - 1] - FadedLevel(kAmpA, 1.0)) <= tolerance,
			"BlocoI: fade-in settles at the full BGM volume", std::to_string(left[switchAt - 1]));

		double worstCrossfade = 0;
		for(uint32_t t = 0; t < kFadeSamples; t++) {
			double u = (double)t / kFadeSamples;
			double expected = FadedLevel(kAmpA, 1.0 - u) + FadedLevel(kAmpB, u);
			worstCrossfade = std::max(worstCrossfade, std::abs(left[switchAt + t] - expected));
		}
		Check(worstCrossfade <= 2 * tolerance, "BlocoI: a switch crossfades - the two linear ramps overlap and sum",
			"worst " + std::to_string(worstCrossfade) + " > " + std::to_string(2 * tolerance));

		double worstFadeOut = 0;
		for(uint32_t t = 0; t < kFadeSamples; t++) {
			worstFadeOut = std::max(worstFadeOut, std::abs(left[stopAt + t] - FadedLevel(kAmpB, 1.0 - (double)t / kFadeSamples)));
		}
		Check(worstFadeOut <= tolerance, "BlocoI: StopBgm follows the linear 1->0 ramp over kBgmFadeSamples",
			"worst " + std::to_string(worstFadeOut) + " > " + std::to_string(tolerance));

		//(c) Silence once the stop window is over.
		bool silent = true;
		for(size_t i = stopAt + kFadeSamples; i < left.size(); i++) {
			silent = silent && left[i] == 0;
		}
		Check(silent, "BlocoI: nothing is mixed after the stop fade window");
	}

	void TestBgmCrossfadeIgnoresRunAheadBlocks()
	{
		CrossfadeRun plain;
		RecordCrossfade(plain, -1);

		//Same run with one extra run-ahead block in the middle of the fade-in:
		//it must be silent (asserted inside RecordCrossfade) and must leave the
		//fade counters and the sources' positions untouched, so every real
		//block that follows is sample-identical to the plain run.
		CrossfadeRun withRunAhead;
		RecordCrossfade(withRunAhead, 1);

		Check(plain.Left == withRunAhead.Left, "BlocoI: a run-ahead block advances neither the fade counters nor the sources");
		Check(plain.Sources.size() == 2 && withRunAhead.Sources.size() == 2 && plain.Sources[0]->MixedFrames == withRunAhead.Sources[0]->MixedFrames,
			"BlocoI: the run-ahead block consumed no source samples");
	}
}

//--- Bloco J: OGG track loop point (ADR-0134, F5.4g Block C item 8) ----------
//A replaced track used to always loop from sample 0, so its intro repeated
//forever. ADR-0134 Option A puts an optional loop point on the track
//(fingerprints.json `tracks[i].loop`, PCM samples at the OGG's own rate):
//once the stream runs out, playback resumes there. OggLoopStream holds that
//rule; the stub decoder below stands in for stb_vorbis, so the case needs no
//OGG file and no VirtualFile.
namespace
{
	//A decoder of `length` samples whose sample value is its own position, so
	//the caller can read back exactly where each frame came from.
	class StubOggDecoder : public IOggDecoder
	{
	private:
		uint32_t _length;
		uint32_t _position = 0;

	public:
		uint32_t SeekCount = 0;
		uint32_t LastSeekTarget = UINT32_MAX;

		StubOggDecoder(uint32_t length) : _length(length) {}

		int GetSampleRate() override { return 44100; }
		uint32_t GetStreamLength() override { return _length; }
		uint32_t GetOffset() override { return _position; }

		void Seek(uint32_t sampleOffset) override
		{
			SeekCount++;
			LastSeekTarget = sampleOffset;
			_position = sampleOffset;
		}

		uint32_t ReadFrames(int16_t* buffer, uint32_t frames) override
		{
			uint32_t produced = 0;
			while(produced < frames && _position < _length) {
				buffer[produced * 2] = (int16_t)_position;
				buffer[produced * 2 + 1] = (int16_t)_position;
				_position++;
				produced++;
			}
			return produced;
		}
	};

	void TestLoopPointReturnsToLoopPosition()
	{
		StubOggDecoder decoder(1000);
		OggLoopStream stream;
		stream.Init(&decoder, true, 400);
		Check(stream.GetLoopPosition() == 400, "BlocoJ: an in-range loop point is kept as-is");

		//Consume the whole track, then one block that runs past its end.
		vector<int16_t> buffer(600 * 2, 0);
		Check(stream.Read(buffer.data(), 600) == 600, "BlocoJ: a full block before the end reads in full");
		uint32_t read = stream.Read(buffer.data(), 600);
		Check(read == 600, "BlocoJ: the block that crosses the end is still filled in full", std::to_string(read));
		Check(decoder.SeekCount == 1 && decoder.LastSeekTarget == 400,
			"BlocoJ: consuming past the end seeks back to loopPosition, not to 0",
			"seeks " + std::to_string(decoder.SeekCount) + " -> " + std::to_string(decoder.LastSeekTarget));
		//The first 400 frames of that block are the tail of the track; the rest
		//is the loop, i.e. samples 400.. - the intro (0..399) is never replayed.
		Check(buffer[0] == 600 && buffer[399 * 2] == 999, "BlocoJ: the block starts with the track's tail");
		Check(buffer[400 * 2] == 400 && buffer[401 * 2] == 401, "BlocoJ: playback resumes at the loop point",
			std::to_string(buffer[400 * 2]));
		Check(decoder.GetOffset() == 600, "BlocoJ: the read position is past the loop point, not past 0");
		Check(!stream.IsDone(), "BlocoJ: a looping track never reports playback over");
	}

	void TestNoLoopPointBehavesAsBefore()
	{
		//Backward compatibility (ADR-0134): a pack that omits `loop` keeps the
		//pre-item-8 behaviour and loops the whole file from 0.
		StubOggDecoder decoder(1000);
		OggLoopStream stream;
		stream.Init(&decoder, true, 0);
		Check(stream.GetLoopPosition() == 0, "BlocoJ: a track with no loop point loops from 0");

		vector<int16_t> buffer(1200 * 2, 0);
		stream.Read(buffer.data(), 1200);
		Check(decoder.SeekCount == 1 && decoder.LastSeekTarget == 0, "BlocoJ: without a loop point the wrap seeks to 0",
			std::to_string(decoder.LastSeekTarget));
		Check(buffer[1000 * 2] == 0 && buffer[1001 * 2] == 1, "BlocoJ: without a loop point the intro is replayed");

		//An out-of-range loop point degrades to the same behaviour instead of
		//seeking past the end of the stream.
		StubOggDecoder farLoop(1000);
		OggLoopStream clamped;
		clamped.Init(&farLoop, true, 5000);
		Check(clamped.GetLoopPosition() == 0, "BlocoJ: a loop point at or past the end of the stream clamps to 0");

		//A non-looping track still ends instead of wrapping.
		StubOggDecoder once(1000);
		OggLoopStream oneShot;
		oneShot.Init(&once, false, 400);
		oneShot.Read(buffer.data(), 1200);
		Check(once.SeekCount == 0 && oneShot.IsDone(), "BlocoJ: a non-looping track ends instead of seeking to the loop point");
	}
}

//--- Bloco K: replacement mute mask (ADR-0133, F5.4g Block C item 9) ---------
//While a fingerprint-matched OGG replaces the music, the APU's tonal channels
//are muted - but a channel the ChannelRoleClassifier flags as SFX must pass
//through dry, or the game's jumps and hits disappear. ReplacementMuteMask
//holds both halves of that contract: Compute() is the policy
//NesAudioReplacer::UpdateReplacementMuteMask pushes, IsMuted() is the exact
//test NesSoundMixer::GetChannelOutput applies, so the two cannot drift.
namespace
{
	//Stands in for ChannelRoleClassifier (Compute is a template so the mixer
	//never has to include it): a fixed set of SFX-flagged channels.
	struct StubRoles
	{
		bool Sfx[4] = {};
		bool IsSfx(int i) const { return i >= 0 && i < 4 && Sfx[i]; }
	};

	//Mixer-side: which AudioChannel indices a mask silences. 0..3 are the
	//tonal channels, 4 is DMC, 5+ are the expansion chips.
	string MutedChannels(uint8_t mask)
	{
		string result;
		for(int i = 0; i < 11; i++) {
			if(ReplacementMuteMask::IsMuted(mask, i)) {
				result += std::to_string(i) + " ";
			}
		}
		return result;
	}

	void TestReplacementMuteMaskDefaultsToFullTonalMute()
	{
		//No classifier at all (Enhanced Audio off) and a warmed-up classifier
		//that flagged nothing both mute exactly Square1, Square2, Triangle and
		//Noise - pre-item-9 behaviour, never "unmute all".
		Check(ReplacementMuteMask::Compute<StubRoles>(nullptr) == 0x0F, "BlocoK: no classifier falls back to the full tonal mute");
		StubRoles quiet;
		Check(ReplacementMuteMask::Compute(&quiet) == 0x0F, "BlocoK: a classifier flagging no SFX keeps the full tonal mute");
		Check(MutedChannels(0x0F) == "0 1 2 3 ", "BlocoK: the full tonal mute silences exactly Square1, Square2, Triangle and Noise",
			MutedChannels(0x0F));
	}

	void TestReplacementMuteMaskLetsSfxChannelsThrough()
	{
		//Square2 flagged as SFX: its bit is cleared and nothing else moves.
		StubRoles square2Sfx;
		square2Sfx.Sfx[1] = true;
		uint8_t mask = ReplacementMuteMask::Compute(&square2Sfx);
		Check(mask == 0x0D, "BlocoK: an SFX-flagged channel clears exactly its own bit", MutedChannels(mask));
		Check(MutedChannels(mask) == "0 2 3 ", "BlocoK: the other tonal channels stay muted", MutedChannels(mask));

		//All three melodic channels flagged: only Noise stays muted (the
		//classifier has no opinion on it).
		StubRoles allSfx;
		allSfx.Sfx[0] = allSfx.Sfx[1] = allSfx.Sfx[2] = true;
		Check(ReplacementMuteMask::Compute(&allSfx) == 0x08, "BlocoK: with every melodic channel on SFX only Noise stays muted",
			MutedChannels(ReplacementMuteMask::Compute(&allSfx)));

		//A flag on the Noise slot is not read: it is not one of the three
		//melodic channels the classifier judges.
		StubRoles noiseSfx;
		noiseSfx.Sfx[3] = true;
		Check(ReplacementMuteMask::Compute(&noiseSfx) == 0x0F, "BlocoK: the Noise channel is not unmuted by an SFX flag");
	}

	void TestReplacementMuteMaskNeverTouchesDmcOrExpansion()
	{
		//DMC (index 4) and every expansion channel keep playing under every
		//mask the policy can produce - ADR-0133 point 1.
		for(int sfxBits = 0; sfxBits < 8; sfxBits++) {
			StubRoles roles;
			for(int i = 0; i < 3; i++) {
				roles.Sfx[i] = (sfxBits & (1 << i)) != 0;
			}
			uint8_t mask = ReplacementMuteMask::Compute(&roles);
			bool higherChannelsPass = true;
			for(int channel = ReplacementMuteMask::DmcChannelIndex; channel < 11; channel++) {
				higherChannelsPass = higherChannelsPass && !ReplacementMuteMask::IsMuted(mask, channel);
			}
			Check(higherChannelsPass, "BlocoK: DMC and the expansion channels are never masked (sfx bits " + std::to_string(sfxBits) + ")",
				MutedChannels(mask));
		}

		//A cleared mask (no replacement playing, or any stop path) mutes nothing.
		Check(MutedChannels(0).empty(), "BlocoK: mask 0 mutes no channel at all");
	}
}

//--- Bloco L: EnhancedSynthEngine rendered PCM golden (F5.4g Bloco B) --------
//The level-2 synth was only ever validated by listening. This renders a fixed
//APU/role snapshot through the real Render() and diffs the samples against
//docs/specs/golden/synth/enhanced-synth-pcm.txt (ADR-0129: golden paths are
//cwd-relative from the repo root). It is a regression net, not a judgement of
//timbre: any change to the voices, the drums, the FX chain or the mix that
//moves the output shows up here and has to be re-blessed deliberately.
//No SoundFont is loaded and InitPresets is never called, so the case does no
//file I/O and never depends on the user's EnhancedAudioPresets.cfg; the noise
//RNG of a freshly constructed engine is seeded to a fixed value.
namespace
{
	constexpr uint32_t kGoldenSampleRate = 44100;
	constexpr uint32_t kGoldenBlockFrames = 32;
	constexpr uint32_t kGoldenBlocks = 4;
	//8-bit-ish slack for platform libm differences in the transcendental parts
	//of the voices; the defects this case targets move samples by hundreds.
	constexpr int kGoldenTolerance = 2;

	//A synthetic preset written out here on purpose: it belongs to the test,
	//not to any console's built-in table, so re-tuning the NES or SMS presets
	//does not invalidate the golden.
	EnhancedSynthPreset GoldenPreset()
	{
		EnhancedSynthPreset p = {};
		p.LeadDetune = 0.12;
		p.HarmDetune = 0.08;
		p.FollowDuty = true;
		p.FixedWidth = 0.5;
		p.LeadAlwaysSaw = false;
		p.LeadOctaveUpMix = 0.25;
		p.LeadLpHz = 6000;
		p.HarmLpHz = 4500;
		p.LeadDrive = 1.2;
		p.BassSine = 0.6;
		p.BassSaw = 0.3;
		p.BassSub = 0.2;
		p.BassLpHz = 900;
		p.BassDrive = 1.1;
		p.DrumBodyLoHz = 180;
		p.DrumBodyHiHz = 2400;
		p.DrumTopHz = 9000;
		p.DrumBodyGain = 0.7;
		p.ThumpGain = 0.5;
		p.ThumpDecayS = 0.09;
		p.ThumpFreqHz = 55;
		p.AttackMs = 4;
		p.ReleaseMs = 60;
		p.EchoDelayS = 0.12;
		p.EchoGainL = 0.2;
		p.EchoGainR = 0.15;
		p.ReverbWet = 0.18;
		p.LeadGain = 0.9;
		p.HarmGain = 0.7;
		p.BassGain = 0.8;
		p.DrumGain = 0.6;
		p.CompThreshold = 0.7;
		p.CompRatio = 4;
		p.CompAttackMs = 5;
		p.CompReleaseMs = 120;
		p.CompMakeup = 1.1;
		p.GmLeadProgram = 80;
		p.GmHarmProgram = 81;
		p.GmBassProgram = 38;
		p.GmDrums = false;
		p.FixedRole[0] = p.FixedRole[1] = p.FixedRole[2] = p.FixedRole[3] = -1;
		return p;
	}

	//A fixed snapshot: lead A4, harmony C#5, bass A2, a bright-ish noise hit
	//eligible for the low thump, plus one dry SFX voice.
	EnhancedSynthEngine::Input GoldenInput()
	{
		EnhancedSynthEngine::Input in;
		in.LeadFreq = 440.0;
		in.LeadVol = 0.80;
		in.LeadWidth = 0.5;
		in.HarmFreq = 554.365;
		in.HarmVol = 0.55;
		in.HarmWidth = 0.25;
		in.BassFreq = 110.0;
		in.BassVol = 0.70;
		in.NoiseVol = 0.45;
		in.NoiseBrightness = 0.30;
		in.ThumpEligible = true;
		in.SfxCount = 1;
		in.Sfx[0] = { 1320.0, 0.35, 0.5 };
		return in;
	}

	//Renders the fixed snapshot in kGoldenBlocks blocks, exactly as the audio
	//path does (Render adds onto a zeroed block buffer).
	vector<int16_t> RenderGoldenPcm()
	{
		EnhancedSynthEngine engine;
		EnhancedSynthPreset preset = GoldenPreset();
		EnhancedSynthEngine::Input in = GoldenInput();
		vector<int16_t> pcm;
		for(uint32_t block = 0; block < kGoldenBlocks; block++) {
			vector<int16_t> out(kGoldenBlockFrames * 2, 0);
			engine.Render(out.data(), kGoldenBlockFrames, kGoldenSampleRate, in, preset, 100.0);
			pcm.insert(pcm.end(), out.begin(), out.end());
		}
		return pcm;
	}

	void TestEnhancedSynthPcmGolden()
	{
		string fixturePath = "docs/specs/golden/synth/enhanced-synth-pcm.txt";
		ifstream fixture(fixturePath);
		if(!fixture) {
			Check(false, "BlocoL: enhanced-synth-pcm.txt fixture opens", "could not open " + fixturePath + " (run from the repo root)");
			return;
		}

		vector<int16_t> expected;
		string line;
		while(std::getline(fixture, line)) {
			if(line.empty() || line[0] == '#') {
				continue;
			}
			std::istringstream parser(line);
			int index = 0, left = 0, right = 0;
			if(!(parser >> index >> left >> right)) {
				Check(false, "BlocoL: golden line parses", line);
				return;
			}
			expected.push_back((int16_t)left);
			expected.push_back((int16_t)right);
		}

		vector<int16_t> actual = RenderGoldenPcm();
		Check(expected.size() == actual.size(), "BlocoL: the golden covers every rendered frame",
			std::to_string(expected.size() / 2) + " golden vs " + std::to_string(actual.size() / 2) + " rendered");
		if(expected.size() != actual.size()) {
			return;
		}

		int worst = 0;
		size_t worstAt = 0;
		for(size_t i = 0; i < actual.size(); i++) {
			int delta = std::abs((int)actual[i] - (int)expected[i]);
			if(delta > worst) {
				worst = delta;
				worstAt = i;
			}
		}
		Check(worst <= kGoldenTolerance, "BlocoL: the rendered PCM matches docs/specs/golden/synth/enhanced-synth-pcm.txt",
			"worst |diff| " + std::to_string(worst) + " at frame " + std::to_string(worstAt / 2) + " (allowed " + std::to_string(kGoldenTolerance) + ")");

		//A golden of silence would match anything: make sure the snapshot
		//really produced audio.
		int peak = 0;
		for(int16_t sample : actual) {
			peak = std::max(peak, std::abs((int)sample));
		}
		Check(peak > 1000, "BlocoL: the fixed snapshot renders audible audio", "peak " + std::to_string(peak));
	}
}


//--- Bloco M: the ADR-0120 §4 zip pipeline against real archive bytes -------
//§4 deferred a "standalone C++ E2E zip-pipeline harness"; §2's pure-function
//extraction only covered FindFallbackSubfolder with literal string fixtures,
//and the zip/slip kinds of scripts/gen_mep_test_pack.py were a manual
//headless_record log inspection. This drives the whole MepZipExtract pipeline
//(the code MepPackManager::PrepareZip now delegates to) on zips built here
//with Utilities/miniz.cpp: extraction, zip-slip rejection on real bytes, the
//.mep-source cache-reuse branch and the wrapped-subfolder fallback.
namespace
{
	const char* kZipRomName = "Contra80s";

	//A zip entry: archive name + contents. Names miniz's writer refuses to
	//write (a leading '/', a backslash, a drive colon) are produced by
	//building the archive with a same-length placeholder name and patching
	//the raw bytes afterwards - see BuildZipWithRawName.
	struct ZipEntry
	{
		string Name;
		string Content;
	};

	vector<uint8_t> BuildZip(const vector<ZipEntry>& entries)
	{
		mz_zip_archive zip;
		memset(&zip, 0, sizeof(zip));
		if(!mz_zip_writer_init_heap(&zip, 0, 64 * 1024)) {
			return {};
		}
		for(const ZipEntry& entry : entries) {
			mz_zip_writer_add_mem(&zip, entry.Name.c_str(), entry.Content.data(), entry.Content.size(), MZ_BEST_SPEED);
		}
		void* buffer = nullptr;
		size_t size = 0;
		vector<uint8_t> bytes;
		if(mz_zip_writer_finalize_heap_archive(&zip, &buffer, &size)) {
			bytes.assign((uint8_t*)buffer, (uint8_t*)buffer + size);
		}
		mz_zip_writer_end(&zip);
		return bytes;
	}

	//miniz's writer validates archive names (no leading '/', no '\', no ':'),
	//so a hostile entry name has to be written after the fact. `placeholder`
	//and `rawName` MUST have the same length: the name appears verbatim in
	//both the local file header and the central directory record.
	vector<uint8_t> BuildZipWithRawName(vector<ZipEntry> entries, const string& placeholder, const string& rawName)
	{
		vector<uint8_t> bytes = BuildZip(entries);
		if(placeholder.size() != rawName.size()) {
			return {};
		}
		for(size_t i = 0; i + placeholder.size() <= bytes.size(); i++) {
			if(memcmp(bytes.data() + i, placeholder.data(), placeholder.size()) == 0) {
				memcpy(bytes.data() + i, rawName.data(), rawName.size());
			}
		}
		return bytes;
	}

	//The unit-test side of MepZipExtract::IArchive: miniz straight on the
	//bytes, no ZipReader/ArchiveReader (which would drag SevenZip in).
	class MinizArchive : public MepZipExtract::IArchive
	{
	public:
		~MinizArchive() override
		{
			if(_loaded) {
				mz_zip_reader_end(&_zip);
			}
		}

		bool Load(const string& zipPath, vector<string>& entries, string& error) override
		{
			ifstream in(zipPath, std::ios::in | std::ios::binary);
			if(!in) {
				error = "cannot open zip";
				return false;
			}
			std::stringstream ss;
			ss << in.rdbuf();
			string content = ss.str();
			_bytes.assign(content.begin(), content.end());
			memset(&_zip, 0, sizeof(_zip));
			if(!mz_zip_reader_init_mem(&_zip, _bytes.data(), _bytes.size(), 0)) {
				error = "not a valid zip archive";
				return false;
			}
			_loaded = true;
			for(mz_uint i = 0, len = mz_zip_reader_get_num_files(&_zip); i < len; i++) {
				mz_zip_archive_file_stat stat;
				if(mz_zip_reader_file_stat(&_zip, i, &stat)) {
					entries.push_back(stat.m_filename);
				}
			}
			return true;
		}

		bool ExtractFile(const string& entry, vector<uint8_t>& content) override
		{
			size_t size = 0;
			void* data = mz_zip_reader_extract_file_to_heap(&_zip, entry.c_str(), &size, 0);
			if(!data) {
				return false;
			}
			content.assign((uint8_t*)data, (uint8_t*)data + size);
			mz_free(data);
			return true;
		}

	private:
		mz_zip_archive _zip;
		bool _loaded = false;
		vector<uint8_t> _bytes;
	};

	string ZipPackJson(const string& name)
	{
		return "{\"mep\":\"1.0.0\",\"name\":\"" + name + "\",\"version\":\"1.0.0\",\"license\":\"CC0\","
			"\"targets\":[{\"system\":\"nes\",\"sha1\":\"0000000000000000000000000000000000000000\",\"name\":\"test rom\"}],"
			"\"sections\":{\"textures\":{\"path\":\"textures/\"}}}";
	}

	//Runs the whole PrepareZip pipeline against an existing <dir>/<fileName>,
	//with <dir>/cache as the cache root. Kept separate from writing the file
	//so the cache-reuse case can re-run it without touching the zip's mtime.
	bool PrepareZipAt(const std::filesystem::path& dir, const string& fileName, string& outFolder, string& error)
	{
		MinizArchive archive;
		string cacheRoot = (dir / "cache").u8string();
		return MepZipExtract::PrepareZip(archive, (dir / fileName).u8string(), cacheRoot, kZipRomName, outFolder, error);
	}

	//Writes `bytes` as <dir>/<fileName>, then prepares it.
	bool RunPrepareZip(const std::filesystem::path& dir, const string& fileName, const vector<uint8_t>& bytes,
		string& outFolder, string& error)
	{
		{
			std::ofstream out(dir / fileName, std::ios::out | std::ios::binary);
			out.write((const char*)bytes.data(), bytes.size());
		}
		return PrepareZipAt(dir, fileName, outFolder, error);
	}

	bool FileExists(const std::filesystem::path& path)
	{
		std::error_code ec;
		return std::filesystem::exists(path, ec);
	}

	void TestZipWellFormedPackExtracts()
	{
		//gen_mep_test_pack.py's "zip" kind: pack.json at the root plus content.
		std::filesystem::path dir = MakeTempPackDir("zip_ok");
		vector<uint8_t> bytes = BuildZip({
			{ "pack.json", ZipPackJson("MEP test (zip)") },
			{ "textures/hires.txt", "<ver>106\n<scale>1\n" },
			{ "synth/preset.cfg", "[Studio]\nCompThreshold=0.5\n" },
		});
		Check(!bytes.empty(), "BlocoM: the miniz-built control archive has bytes");

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "mep-test-zip.zip", bytes, outFolder, error);
		Check(ok, "BlocoM: a well-formed zip pack is accepted", error);
		Check(FileExists(std::filesystem::u8path(outFolder) / "pack.json"), "BlocoM: pack.json is extracted to the cache folder", outFolder);
		Check(FileExists(std::filesystem::u8path(outFolder) / "textures" / "hires.txt"), "BlocoM: a nested entry keeps its relative path");
		Check(FileExists(std::filesystem::u8path(outFolder) / ".mep-source"), "BlocoM: the .mep-source cache stamp is written");
		std::filesystem::remove_all(dir);
	}

	void TestZipSlipTraversalEntryIsRejected()
	{
		//gen_mep_test_pack.py's "slip" kind: a valid pack plus '../evil.txt'.
		//The plan is validated before anything is written, so the whole pack
		//is refused and no file - inside or outside the cache - is created.
		std::filesystem::path dir = MakeTempPackDir("zip_slip");
		vector<uint8_t> bytes = BuildZip({
			{ "pack.json", ZipPackJson("MEP slip") },
			{ "textures/hires.txt", "<ver>106\n" },
			{ "../evil.txt", "pwned" },
		});

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "mep-test-slip.zip", bytes, outFolder, error);
		Check(!ok, "BlocoM: a '../' zip-slip entry is rejected on real archive bytes");
		Check(error.find("escapes the pack root") != string::npos, "BlocoM: the zip-slip rejection names the offending entry", error);
		Check(!FileExists(dir / "cache" / "mep-test-slip" / "pack.json"), "BlocoM: nothing is extracted from a rejected zip-slip pack");
		Check(!FileExists(dir / "cache" / "evil.txt") && !FileExists(dir / "evil.txt"),
			"BlocoM: the '../' target is never written outside the cache folder");
		std::filesystem::remove_all(dir);
	}

	void TestZipAbsolutePathEntryIsRejected()
	{
		//An absolute entry name cannot come out of miniz's writer, so it is
		//patched into the raw bytes: "Xtmp/evil.txt" -> "/tmp/evil.txt".
		std::filesystem::path dir = MakeTempPackDir("zip_abs");
		vector<uint8_t> bytes = BuildZipWithRawName({
			{ "pack.json", ZipPackJson("MEP absolute") },
			{ "Xtmp/evil.txt", "pwned" },
		}, "Xtmp/evil.txt", "/tmp/evil.txt");
		Check(!bytes.empty(), "BlocoM: the absolute-path archive was patched");

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "mep-test-abs.zip", bytes, outFolder, error);
		Check(!ok, "BlocoM: an absolute '/tmp/...' zip entry is rejected");
		Check(!FileExists(dir / "cache" / "mep-test-abs" / "pack.json"), "BlocoM: nothing is extracted from a rejected absolute-path pack");
		std::filesystem::remove_all(dir);
	}

	void TestZipWindowsPathEntryIsRejected()
	{
		//The other absolute shape mep_lint.py and MepPack reject: a drive
		//letter with backslashes ("C:\evil.dll"), also unwritable by miniz.
		std::filesystem::path dir = MakeTempPackDir("zip_win");
		vector<uint8_t> bytes = BuildZipWithRawName({
			{ "pack.json", ZipPackJson("MEP windows") },
			{ "CXevilYdll", "pwned" },
		}, "CXevilYdll", "C:\\evil.dll");

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "mep-test-win.zip", bytes, outFolder, error);
		Check(!ok, "BlocoM: a 'C:\\...' zip entry is rejected");
		std::filesystem::remove_all(dir);
	}

	void TestZipSymlinkEntryCannotEscape()
	{
		//The zip-symlink attack has two halves and this covers both:
		//(1) an entry whose *payload* is a path is extracted as an ordinary
		//file, never as a symlink (the extractor writes bytes, it never
		//consults the entry's unix mode);
		//(2) a symlink left inside the cache folder by an earlier extraction
		//is not written through, because PrepareZip wipes a stale cache
		//before extracting anything.
		std::filesystem::path dir = MakeTempPackDir("zip_symlink");
		std::filesystem::path outside = dir / "outside.txt";
		WriteTestFile(outside, "original");

		std::error_code ec;
		std::filesystem::path cachedPack = dir / "cache" / "mep-test-symlink";
		std::filesystem::create_directories(cachedPack, ec);
		//A stale cache whose "textures/hires.txt" is a symlink pointing out of
		//the cache, and a stamp that does not match the zip about to be read
		std::filesystem::create_directories(cachedPack / "textures", ec);
		std::filesystem::create_symlink(outside, cachedPack / "textures" / "hires.txt", ec);
		WriteTestFile(cachedPack / ".mep-source", "0:0");
		bool symlinkReady = !ec && std::filesystem::is_symlink(cachedPack / "textures" / "hires.txt", ec);
		Check(symlinkReady, "BlocoM: the stale cache symlink fixture was created");

		vector<uint8_t> bytes = BuildZip({
			{ "pack.json", ZipPackJson("MEP symlink") },
			{ "textures/hires.txt", "<ver>106\n" },
			{ "link-payload", "../../outside.txt" },
		});
		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "mep-test-symlink.zip", bytes, outFolder, error);
		Check(ok, "BlocoM: the symlink-fixture pack itself extracts", error);

		std::filesystem::path extractedLink = std::filesystem::u8path(outFolder) / "textures" / "hires.txt";
		Check(!std::filesystem::is_symlink(extractedLink, ec), "BlocoM: the stale symlink is wiped, not written through");
		string outsideContent;
		{
			ifstream in(outside);
			std::stringstream ss;
			ss << in.rdbuf();
			outsideContent = ss.str();
		}
		Check(outsideContent == "original", "BlocoM: the file outside the cache is left untouched", outsideContent);
		Check(!std::filesystem::is_symlink(std::filesystem::u8path(outFolder) / "link-payload", ec),
			"BlocoM: an entry whose payload is a path is extracted as a plain file");
		std::filesystem::remove_all(dir);
	}

	void TestZipNestedWrapperFolderFallback()
	{
		//ADR-0120's motivating shape: a release zip named after neither the
		//ROM nor a root pack.json, wrapping everything in a ROM-named folder.
		std::filesystem::path dir = MakeTempPackDir("zip_wrapper");
		vector<uint8_t> bytes = BuildZip({
			{ "Contra80s/pack.json", ZipPackJson("MEP wrapped") },
			{ "Contra80s/textures/hires.txt", "<ver>106\n" },
			{ "readme.txt", "release notes" },
		});

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "Contra80s-HD-v2.zip", bytes, outFolder, error);
		Check(ok, "BlocoM: a wrapped (ROM-named subfolder) zip is accepted", error);
		Check(StringUtilities::EndsWith(outFolder, "Contra80s"), "BlocoM: the fallback prefix is folded into the returned folder", outFolder);
		Check(FileExists(std::filesystem::u8path(outFolder) / "pack.json"), "BlocoM: the wrapped pack.json is where the caller looks for it");
		std::filesystem::remove_all(dir);
	}

	void TestZipUnwrappedNoPackJsonIsRejected()
	{
		//No root pack.json, zip name != ROM name, and no ROM-named subfolder
		//either: the fallback finds nothing, so the pack is rejected.
		std::filesystem::path dir = MakeTempPackDir("zip_norule");
		vector<uint8_t> bytes = BuildZip({
			{ "SomeOtherGame/textures/hires.txt", "<ver>106\n" },
		});

		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "random-upload.zip", bytes, outFolder, error);
		Check(!ok, "BlocoM: a zip with neither a root pack.json nor a ROM-named folder is rejected");
		Check(error == "zip has no pack.json at its root", "BlocoM: the rejection reason is the ADR-0040 one", error);
		std::filesystem::remove_all(dir);
	}

	void TestZipCacheIsReusedUntilTheZipChanges()
	{
		//The .mep-source stamp branch: a second PrepareZip on unchanged bytes
		//must not re-extract (a marker dropped in the cache survives), and a
		//changed zip must wipe the cache and extract again.
		std::filesystem::path dir = MakeTempPackDir("zip_cache");
		vector<uint8_t> bytes = BuildZip({
			{ "pack.json", ZipPackJson("MEP cached") },
			{ "textures/hires.txt", "<ver>106\n" },
		});

		string outFolder;
		string error;
		Check(RunPrepareZip(dir, "cached.zip", bytes, outFolder, error), "BlocoM: the cached-pack fixture extracts once", error);

		std::filesystem::path marker = std::filesystem::u8path(outFolder) / "marker.txt";
		WriteTestFile(marker, "still here");
		string secondFolder;
		//The very same file, untouched: same size, same mtime, same stamp
		Check(PrepareZipAt(dir, "cached.zip", secondFolder, error), "BlocoM: re-preparing the same zip succeeds", error);
		Check(secondFolder == outFolder, "BlocoM: the cache folder is stable across runs");
		Check(FileExists(marker), "BlocoM: an unchanged zip reuses the cache instead of re-extracting");

		//Same file name, different content (and therefore a different size):
		//the stamp no longer matches, so the folder is wiped and rebuilt
		vector<uint8_t> changed = BuildZip({
			{ "pack.json", ZipPackJson("MEP cached v2 - a longer name to change the archive size") },
			{ "textures/hires.txt", "<ver>106\n<scale>2\n" },
		});
		string thirdFolder;
		Check(RunPrepareZip(dir, "cached.zip", changed, thirdFolder, error), "BlocoM: a changed zip re-extracts", error);
		Check(!FileExists(marker), "BlocoM: a changed zip wipes the stale cache before extracting");
		std::filesystem::remove_all(dir);
	}

	void TestZipEmptyArchiveIsRejected()
	{
		std::filesystem::path dir = MakeTempPackDir("zip_empty");
		vector<uint8_t> bytes = BuildZip({});
		string outFolder;
		string error;
		bool ok = RunPrepareZip(dir, "empty.zip", bytes, outFolder, error);
		Check(!ok && error == "zip is empty", "BlocoM: an empty archive is rejected", error);
		std::filesystem::remove_all(dir);
	}
}

//--- Bloco N: aspect-ratio geometry per setting (P.7 "16:9 stretch") --------
//Geometry only: this asserts the ratio the renderer is asked to draw at (and
//the stretched width that follows from it), NOT the pixels on screen. The
//visual pass on a real display stays manual - a unit test cannot see a
//stretched image, only the number that produces it.
namespace
{
	const uint32_t kNesWidth = 256;
	const uint32_t kNesHeight = 240;

	AspectRatioMath::Inputs NesInputs(VideoAspectRatio setting)
	{
		AspectRatioMath::Inputs in;
		in.Setting = setting;
		in.BaseWidth = kNesWidth;
		in.BaseHeight = kNesHeight;
		in.Region = ConsoleRegion::Ntsc;
		return in;
	}

	bool NearlyEqual(double a, double b)
	{
		return std::fabs(a - b) < 1e-9;
	}

	void TestAspectRatioPerSetting()
	{
		double square = (double)kNesWidth / kNesHeight; //256/240 = 16/15

		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::NoStretching)), square),
			"BlocoN: NoStretching keeps the base screen ratio (square pixels)");
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::Standard)), 4.0 / 3.0),
			"BlocoN: Standard is exactly 4:3 regardless of the base size");
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::Widescreen)), 16.0 / 9.0),
			"BlocoN: Widescreen is exactly 16:9 regardless of the base size");
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::NTSC)), square * 8.0 / 7.0),
			"BlocoN: NTSC applies the 8:7 pixel aspect ratio");
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::PAL)), square * 11.0 / 8.0),
			"BlocoN: PAL applies the 11:8 pixel aspect ratio");

		AspectRatioMath::Inputs custom = NesInputs(VideoAspectRatio::Custom);
		custom.CustomRatio = 2.5;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(custom), 2.5), "BlocoN: Custom returns the configured ratio verbatim");

		//4:3 and 16:9 are absolute, so a different base resolution (SMS) must
		//not move them, while the PAR-based settings must follow it
		AspectRatioMath::Inputs sms = NesInputs(VideoAspectRatio::Widescreen);
		sms.BaseWidth = 256;
		sms.BaseHeight = 192;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(sms), 16.0 / 9.0), "BlocoN: Widescreen ignores the base resolution");
		sms.Setting = VideoAspectRatio::NTSC;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(sms), (256.0 / 192.0) * 8.0 / 7.0), "BlocoN: NTSC follows the base resolution");
	}

	void TestAspectRatioAutoPerConsole()
	{
		AspectRatioMath::Inputs autoNtsc = NesInputs(VideoAspectRatio::Auto);
		double square = (double)kNesWidth / kNesHeight;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(autoNtsc), square * 8.0 / 7.0), "BlocoN: Auto on an NTSC console is the 8:7 PAR");

		AspectRatioMath::Inputs autoPal = autoNtsc;
		autoPal.Region = ConsoleRegion::Pal;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(autoPal), square * 11.0 / 8.0), "BlocoN: Auto on a PAL console is the 11:8 PAR");
		autoPal.Region = ConsoleRegion::Dendy;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(autoPal), square * 11.0 / 8.0), "BlocoN: Auto treats Dendy like PAL");

		AspectRatioMath::Inputs handheld = autoNtsc;
		handheld.BaseWidth = 160;
		handheld.BaseHeight = 144;
		handheld.SquarePixelInAuto = true;
		handheld.Region = ConsoleRegion::Pal; //must be ignored for GB/GBA/WS
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(handheld), 160.0 / 144.0),
			"BlocoN: Auto on GB/GBA/WS stays square, even in a PAL region");

		AspectRatioMath::Inputs gameGear = autoNtsc;
		gameGear.BaseWidth = 160;
		gameGear.BaseHeight = 144;
		gameGear.GameGearPar = true;
		Check(NearlyEqual(AspectRatioMath::ComputeAspectRatio(gameGear), (160.0 / 144.0) * 6.0 / 5.0),
			"BlocoN: Auto on Game Gear applies its 6:5 PAR");
	}

	void TestStretchedSizePerSetting()
	{
		//The destination size the ratio produces for a 240-row NES frame -
		//height preserved, width = round(height * ratio). 16:9 is the P.7 case
		//and must widen the frame past both 4:3 and the unstretched 256.
		AspectRatioMath::Size square = AspectRatioMath::ComputeStretchedSize(kNesHeight,
			AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::NoStretching)));
		AspectRatioMath::Size standard = AspectRatioMath::ComputeStretchedSize(kNesHeight,
			AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::Standard)));
		AspectRatioMath::Size wide = AspectRatioMath::ComputeStretchedSize(kNesHeight,
			AspectRatioMath::ComputeAspectRatio(NesInputs(VideoAspectRatio::Widescreen)));

		Check(square.Width == kNesWidth && square.Height == kNesHeight, "BlocoN: NoStretching renders at the native 256x240",
			std::to_string(square.Width) + "x" + std::to_string(square.Height));
		Check(standard.Width == 320 && standard.Height == kNesHeight, "BlocoN: 4:3 stretches 240 rows to 320 columns",
			std::to_string(standard.Width) + "x" + std::to_string(standard.Height));
		Check(wide.Width == 427 && wide.Height == kNesHeight, "BlocoN: 16:9 stretches 240 rows to 427 columns",
			std::to_string(wide.Width) + "x" + std::to_string(wide.Height));
		Check(wide.Width > standard.Width && standard.Width > square.Width, "BlocoN: 16:9 is wider than 4:3, which is wider than native");
		Check(wide.Height == square.Height, "BlocoN: stretching never changes the row count");
	}
}

//--- Bloco O: the P.4 keyboard-block exemption (Esc while playing) ----------
//A keyboard game (Family BASIC, a SMS keyboard peripheral, ...) turns every
//keyboard shortcut into a dead key so the game gets the keystrokes. Pause has
//always been exempt; P.4 added ToggleOverlay, because in Player mode the
//overlay is how the player pauses. These assert the exemption directly on the
//extracted rule, with a stubbed "which host keys are down" probe.
namespace
{
	const uint16_t kEscKey = 27;
	const uint16_t kMouseKey = IKeyManager::BaseMouseButtonIndex + 1;

	KeyCombination SingleKey(uint16_t key)
	{
		KeyCombination comb = {};
		comb.Key1 = key;
		return comb;
	}

	//Only the listed key codes read as pressed
	ShortcutKeyRules::KeyDownProbe ProbeFor(vector<uint16_t> down)
	{
		return [down](uint16_t keyCode) {
			return std::find(down.begin(), down.end(), keyCode) != down.end();
		};
	}

	bool FiresWithEsc(EmulatorShortcut shortcut, bool keyboardConnected, bool paused)
	{
		return ShortcutKeyRules::IsShortcutPressed(shortcut, SingleKey(kEscKey), {}, keyboardConnected, paused,
			true, ProbeFor({ kEscKey }));
	}

	void TestToggleOverlayStaysReachableInAKeyboardGame()
	{
		Check(FiresWithEsc(EmulatorShortcut::ToggleOverlay, true, false),
			"BlocoO: ToggleOverlay still fires while a keyboard game blocks keys");
		Check(FiresWithEsc(EmulatorShortcut::Pause, true, false),
			"BlocoO: Pause is exempt from the keyboard block, as it always was");

		//Every other shortcut bound to the same key is dead while the keyboard
		//game is running
		EmulatorShortcut blocked[] = { EmulatorShortcut::Reset, EmulatorShortcut::TakeScreenshot,
			EmulatorShortcut::ToggleFullscreen, EmulatorShortcut::SaveState, EmulatorShortcut::Exit };
		for(EmulatorShortcut shortcut : blocked) {
			Check(!FiresWithEsc(shortcut, true, false),
				"BlocoO: shortcut " + std::to_string((int)shortcut) + " does not fire while a keyboard game blocks keys");
		}
	}

	void TestKeyboardBlockOnlyAppliesWhileRunning()
	{
		Check(FiresWithEsc(EmulatorShortcut::Reset, false, false),
			"BlocoO: with no keyboard plugged in, an ordinary shortcut fires");
		Check(FiresWithEsc(EmulatorShortcut::Reset, true, true),
			"BlocoO: while paused, the keyboard block is lifted for every shortcut");
		Check(!ShortcutKeyRules::ShouldBlockKeyboardKeys(EmulatorShortcut::ToggleOverlay, true, false),
			"BlocoO: ToggleOverlay is never blocked");
		Check(!ShortcutKeyRules::ShouldBlockKeyboardKeys(EmulatorShortcut::Pause, true, false),
			"BlocoO: Pause is never blocked");
		Check(ShortcutKeyRules::ShouldBlockKeyboardKeys(EmulatorShortcut::Reset, true, false),
			"BlocoO: any other shortcut is blocked in a running keyboard game");
	}

	void TestKeyboardBlockSparesNonKeyboardInputs()
	{
		//The block is keyboard-only: a shortcut bound to a mouse button or a
		//pad input (>= BaseMouseButtonIndex) keeps working in a keyboard game
		bool mouseBound = ShortcutKeyRules::IsShortcutPressed(EmulatorShortcut::Reset, SingleKey(kMouseKey), {},
			true, false, true, ProbeFor({ kMouseKey }));
		Check(mouseBound, "BlocoO: a shortcut bound to a mouse/pad input is not affected by the keyboard block");

		//And with nothing pressed at all, nothing fires
		bool nothingDown = ShortcutKeyRules::IsShortcutPressed(EmulatorShortcut::ToggleOverlay, SingleKey(kEscKey), {},
			false, false, false, ProbeFor({}));
		Check(!nothingDown, "BlocoO: no key down means no shortcut fires");
	}

	void TestSupersetStillShadowsTheExemptShortcut()
	{
		//The exemption does not change superset precedence: Ctrl+Esc bound to
		//another action shadows the bare-Esc ToggleOverlay while both are down
		KeyCombination superset = {};
		superset.Key1 = 116; //left ctrl
		superset.Key2 = kEscKey;
		bool fires = ShortcutKeyRules::IsShortcutPressed(EmulatorShortcut::ToggleOverlay, SingleKey(kEscKey), { superset },
			true, false, true, ProbeFor({ kEscKey, (uint16_t)116, (uint16_t)117 }));
		Check(!fires, "BlocoO: a pressed superset still shadows ToggleOverlay in a keyboard game");
	}

	//--- Bloco P: artist-legible sheet pipeline (ADR-0153) -------------------

	using namespace MesenSheets;

	//A tile whose 16 CHR bytes are just the shape id repeated, so every shape
	//renders to distinguishable pixels without needing a real CHR dump.
	SheetTileKey SheetTileFor(ShapeId shape)
	{
		SheetTileKey tile;
		for(int i = 0; i < 16; i++) {
			tile.TileData[i] = (uint8_t)((shape + i) & 0xFF);
		}
		tile.PaletteColors = 0x0F162A30;
		return tile;
	}

	//RenderTile indexes a 512-entry NES master palette; the values only have to
	//be distinct for the geometry tests below.
	NesPalette SheetPalette()
	{
		static uint32_t palette[512];
		for(uint32_t i = 0; i < 512; i++) {
			palette[i] = 0x00010101u * i;
		}
		return palette;
	}

	TileLookup SheetLookup()
	{
		return [](ShapeId shape) -> const SheetTileKey* {
			static std::map<ShapeId, SheetTileKey> cache;
			std::map<ShapeId, SheetTileKey>::iterator it = cache.find(shape);
			if(it == cache.end()) {
				it = cache.insert(std::make_pair(shape, SheetTileFor(shape))).second ? cache.find(shape) : cache.end();
			}
			return it == cache.end() ? nullptr : &it->second;
		};
	}

	//A screen built out of a small vocabulary of 2x2 blocks, placed
	//pseudo-randomly: at phase (0,0) the screen holds exactly `shapes` distinct
	//metatiles, at any other phase every tuple straddles two blocks and the
	//count explodes. That gap is what ADR-0153 §1 calls the phase advantage.
	GridFrame SheetBlockScreen(uint32_t blockOffset, uint32_t shapes)
	{
		GridFrame frame;
		for(uint32_t r = 0; r < kGridRows; r++) {
			for(uint32_t c = 0; c < kGridCols; c++) {
				uint32_t state = ((r / 2) * 31u + (c / 2) + blockOffset) * 2654435761u;
				uint32_t block = (state >> 13) % shapes;
				frame.Cells[r][c] = (ShapeId)(1 + block * 4 + (r % 2) * 2 + (c % 2));
			}
		}
		return frame;
	}

	//A screen with no grid at all: every cell an independent pseudo-random shape.
	GridFrame SheetNoiseScreen(uint32_t seed)
	{
		GridFrame frame;
		uint32_t state = seed * 2654435761u + 1u;
		for(uint32_t r = 0; r < kGridRows; r++) {
			for(uint32_t c = 0; c < kGridCols; c++) {
				state = state * 1664525u + 1013904223u;
				frame.Cells[r][c] = (ShapeId)(1 + (state >> 16) % 64);
			}
		}
		return frame;
	}

	void TestSheetStableScreensCollapseRepeats()
	{
		//The recorder collapses duplicate frames into RepeatCount; a fixture may
		//hold literal repeats. Both forms must select the same screens.
		GridFrame a = SheetBlockScreen(0, 3);
		GridFrame b = SheetBlockScreen(1, 3);

		std::vector<GridFrame> collapsed;
		a.RepeatCount = 30;
		b.RepeatCount = 30;
		collapsed.push_back(a);
		collapsed.push_back(b);

		std::vector<GridFrame> literal;
		a.RepeatCount = 1;
		b.RepeatCount = 1;
		for(int i = 0; i < 30; i++) { literal.push_back(a); }
		for(int i = 0; i < 30; i++) { literal.push_back(b); }

		uint32_t distinctCollapsed = 0;
		uint32_t distinctLiteral = 0;
		std::vector<const GridFrame*> keptCollapsed = SelectStableScreens(collapsed, 20, distinctCollapsed);
		std::vector<const GridFrame*> keptLiteral = SelectStableScreens(literal, 20, distinctLiteral);

		Check(keptCollapsed.size() == 2 && keptLiteral.size() == 2,
			"BlocoP: a collapsed run and a literal run both yield two stable screens");
		Check(distinctCollapsed == 2 && distinctLiteral == 2,
			"BlocoP: both forms report the same distinct-screen count");
	}

	void TestSheetHudRowsSurviveAChangingScore()
	{
		//Regression for the 2026-09-05 amendment: byte-identity found zero HUD
		//rows on any game whose status bar holds a score or a timer.
		std::vector<GridFrame> screens;
		for(uint32_t i = 0; i < 3; i++) {
			GridFrame frame = SheetNoiseScreen(i + 1);
			for(uint32_t c = 0; c < kGridCols; c++) {
				frame.Cells[0][c] = kEmptyCell;                       //blank band above the bar
				frame.Cells[1][c] = (ShapeId)(500 + c);               //frozen labels
				frame.Cells[2][c] = (ShapeId)(500 + c);
			}
			//A handful of digits change between screens, the labels do not.
			for(uint32_t c = 24; c < kGridCols; c++) {
				frame.Cells[2][c] = (ShapeId)(900 + i * 32 + c);
			}
			screens.push_back(frame);
		}
		std::vector<const GridFrame*> pointers;
		for(size_t i = 0; i < screens.size(); i++) { pointers.push_back(&screens[i]); }

		uint32_t top = 0;
		uint32_t bottom = 0;
		DetectHudRows(pointers, top, bottom);
		Check(top == 3, "BlocoP: a status bar with a changing score is still a HUD band",
			"top=" + std::to_string(top));
		Check(bottom == 0, "BlocoP: a scrolling playfield contributes no bottom HUD rows");
	}

	void TestSheetHudRowsIgnoreAnAllSkyScreen()
	{
		//Sky rows are identical everywhere but draw nothing, so they must not
		//pass the status-bar test on their own content.
		std::vector<GridFrame> screens;
		for(uint32_t i = 0; i < 3; i++) {
			GridFrame frame = SheetNoiseScreen(i + 7);
			for(uint32_t r = 0; r < 4; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					frame.Cells[r][c] = kEmptyCell;
				}
			}
			screens.push_back(frame);
		}
		std::vector<const GridFrame*> pointers;
		for(size_t i = 0; i < screens.size(); i++) { pointers.push_back(&screens[i]); }

		uint32_t top = 0;
		uint32_t bottom = 0;
		DetectHudRows(pointers, top, bottom);
		Check(top == 4, "BlocoP: a blank band counts as HUD rows but stops at the first drawn, varying row",
			"top=" + std::to_string(top));
	}

	void TestSheetHudRowsSurviveATitleScreenInTheRecording()
	{
		//Regression for the second 2026-09-05 amendment: a recording is a whole
		//session, so a title card sits in the screen set next to the gameplay
		//screens and shares no row with them. Requiring unanimity hid
		//Excitebike's gauge bar and Metroid's energy bar completely.
		std::vector<GridFrame> screens;
		for(uint32_t i = 0; i < 8; i++) {
			GridFrame frame = SheetNoiseScreen(i + 21);
			for(uint32_t r = kGridRows - 2; r < kGridRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					frame.Cells[r][c] = (ShapeId)(600 + r * 32 + c);
				}
			}
			//The clock in the corner ticks; the labels next to it do not.
			frame.Cells[kGridRows - 1][30] = (ShapeId)(1000 + i);
			frame.Cells[kGridRows - 1][31] = (ShapeId)(1100 + i);
			screens.push_back(frame);
		}
		//Two title/menu screens that share nothing with the playfield.
		screens.push_back(SheetNoiseScreen(91));
		screens.push_back(SheetNoiseScreen(92));

		std::vector<const GridFrame*> pointers;
		for(size_t i = 0; i < screens.size(); i++) { pointers.push_back(&screens[i]); }

		uint32_t top = 0;
		uint32_t bottom = 0;
		DetectHudRows(pointers, top, bottom);
		Check(bottom == 2, "BlocoP: a status bar survives a minority of unrelated screens",
			"bottom=" + std::to_string(bottom));

		//...but a bar that only two screens out of ten agree on is not one.
		std::vector<GridFrame> rare;
		for(uint32_t i = 0; i < 10; i++) {
			rare.push_back(SheetNoiseScreen(i + 41));
		}
		for(uint32_t i = 0; i < 2; i++) {
			for(uint32_t c = 0; c < kGridCols; c++) {
				rare[i].Cells[kGridRows - 1][c] = (ShapeId)(700 + c);
			}
		}
		std::vector<const GridFrame*> rarePtrs;
		for(size_t i = 0; i < rare.size(); i++) { rarePtrs.push_back(&rare[i]); }
		DetectHudRows(rarePtrs, top, bottom);
		Check(bottom == 0, "BlocoP: a row two screens in ten agree on is not a status bar",
			"bottom=" + std::to_string(bottom));
	}

	void TestSheetGridPhaseAdvantageSeparatesGridFromNoise()
	{
		std::vector<GridFrame> gridded;
		gridded.push_back(SheetBlockScreen(0, 3));
		gridded.push_back(SheetBlockScreen(1, 3));
		std::vector<const GridFrame*> griddedPtrs;
		for(size_t i = 0; i < gridded.size(); i++) { griddedPtrs.push_back(&gridded[i]); }
		GridDetection gridDet = DetectGrid(griddedPtrs, 0, 0);

		Check(gridDet.HasGrid, "BlocoP: a 2x2-block screen is detected as having a grid",
			"advantage=" + std::to_string(gridDet.PhaseAdvantage));
		Check(gridDet.PhaseX == 0 && gridDet.PhaseY == 0,
			"BlocoP: the winning phase is the one the blocks are aligned to");
		Check(gridDet.PhaseAdvantage >= kGridPhaseAdvantage,
			"BlocoP: the winning phase clears the advantage threshold");
		Check(gridDet.Unit == 16, "BlocoP: a gridded recording keeps unit 16");

		std::vector<GridFrame> noisy;
		noisy.push_back(SheetNoiseScreen(11));
		noisy.push_back(SheetNoiseScreen(12));
		std::vector<const GridFrame*> noisyPtrs;
		for(size_t i = 0; i < noisy.size(); i++) { noisyPtrs.push_back(&noisy[i]); }
		GridDetection noiseDet = DetectGrid(noisyPtrs, 0, 0);

		Check(!noiseDet.HasGrid, "BlocoP: a screen of independent tiles has no grid",
			"advantage=" + std::to_string(noiseDet.PhaseAdvantage));
		Check(noiseDet.Unit == 16,
			"BlocoP: no grid still means unit 16 - HasGrid selects the parity, not the unit");
	}

	void TestSheetVocabularyCountsAndIsolationRule()
	{
		//One block shape repeated all over the screen, plus a single stray
		//metatile that neighbours nothing recurring: the stray is the noise.
		std::vector<GridFrame> frames;
		for(uint32_t i = 0; i < 2; i++) {
			GridFrame frame;
			for(uint32_t r = 0; r < kGridRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					frame.Cells[r][c] = 1;
				}
			}
			//A distinct 2x2 stray, and a second one so the two screens differ.
			for(uint32_t r = 0; r < 2; r++) {
				for(uint32_t c = 0; c < 2; c++) {
					frame.Cells[r][c] = (ShapeId)(50 + i);
				}
			}
			frame.RepeatCount = 30;
			frames.push_back(frame);
		}
		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());

		int32_t common = vocab.Find(MetatileKey{ { 1, 1, 1, 1 } });
		Check(common >= 0, "BlocoP: the repeated block is in the vocabulary");
		Check(common >= 0 && vocab.Entries[(size_t)common].Count > 100,
			"BlocoP: the repeated block carries its placement count");
		Check(common >= 0 && vocab.Entries[(size_t)common].Context == SheetContext::Scene,
			"BlocoP: the repeated block is scene, not noise");

		int32_t stray = vocab.Find(MetatileKey{ { 50, 50, 50, 50 } });
		Check(stray >= 0 && vocab.Entries[(size_t)stray].Count == 1,
			"BlocoP: the stray metatile is seen exactly once");
		//The amended §3 rule: rarity alone is not noise. This stray borders the
		//recurring block, so it is part of the scene the artist paints.
		Check(stray >= 0 && vocab.Entries[(size_t)stray].Context == SheetContext::Scene,
			"BlocoP: a count-1 metatile bordering a recurring scene block is not misc");
		Check(vocab.Entries.size() >= 2 && vocab.Entries[0].Count >= vocab.Entries[1].Count,
			"BlocoP: the vocabulary is ordered most-seen first (ADR-0153 §3)");
	}

	void TestSheetIsolatedMetatilesAreMisc()
	{
		//Nothing repeats and nothing borders anything recurring: every entry is
		//isolated, which is exactly what the noise budget is meant to catch.
		std::vector<GridFrame> frames;
		for(uint32_t i = 0; i < 2; i++) {
			GridFrame frame = SheetNoiseScreen(31 + i);
			frame.RepeatCount = 30;
			frames.push_back(frame);
		}
		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());

		size_t misc = 0;
		for(size_t i = 0; i < vocab.Entries.size(); i++) {
			misc += vocab.Entries[i].Context == SheetContext::Misc ? 1 : 0;
		}
		Check(!vocab.Entries.empty() && misc == vocab.Entries.size(),
			"BlocoP: a screen where nothing recurs is entirely misc",
			std::to_string(misc) + "/" + std::to_string(vocab.Entries.size()));
	}

	//Vocabulary built by hand so the grouping criterion can be tested without
	//going through a recording: A is always followed east by B, while S (sand)
	//sits east of everything.
	Vocabulary SheetGroupingFixture()
	{
		Vocabulary vocab;
		vocab.Grid.Unit = 16;
		vocab.Grid.HasGrid = true;
		for(uint32_t i = 0; i < 4; i++) {
			MetatileEntry entry;
			entry.Key = MetatileKey{ { (ShapeId)(10 + i), (ShapeId)(10 + i), (ShapeId)(10 + i), (ShapeId)(10 + i) } };
			entry.Count = 20;
			vocab.Entries.push_back(entry);
			vocab.Index[entry.Key] = i;
		}
		//0 -> 1 exclusively, in both directions.
		vocab.East[std::make_pair(0u, 1u)] = 8;
		//2 (sand) sits east of 3 sometimes, but also east of everything else,
		//so neither direction predicts the other.
		vocab.East[std::make_pair(3u, 2u)] = 8;
		vocab.East[std::make_pair(3u, 0u)] = 7;
		vocab.East[std::make_pair(1u, 2u)] = 9;
		return vocab;
	}

	void TestSheetMutualPredictabilityRejectsPromiscuousPairs()
	{
		Vocabulary vocab = SheetGroupingFixture();
		std::vector<GroupEdge> edges = SelectPredictiveEdges(vocab, kSheetMinPairCount, kSheetMinPairProb);

		bool hasExclusivePair = false;
		bool hasSandPair = false;
		for(size_t i = 0; i < edges.size(); i++) {
			if(edges[i].A == 0 && edges[i].B == 1) { hasExclusivePair = true; }
			if(edges[i].B == 2) { hasSandPair = true; }
		}
		Check(hasExclusivePair, "BlocoP: a pair that predicts itself in both directions is kept");
		Check(!hasSandPair, "BlocoP: a tile that sits next to everything joins nothing");
	}

	void TestSheetObjectsAreLaidOutFromPredictiveEdges()
	{
		std::vector<SheetGroup> groups = BuildObjects(SheetGroupingFixture());
		Check(groups.size() == 1, "BlocoP: exactly one object comes out of the fixture",
			"groups=" + std::to_string(groups.size()));
		if(groups.size() == 1) {
			Check(groups[0].Cells.size() == 2, "BlocoP: the object is the two mutually predictive cells");
			Check(groups[0].Columns == 2 && groups[0].Rows == 1,
				"BlocoP: an east-joined pair lays out side by side");
		}
	}

	void TestSheetBestShiftRecoversTheScroll()
	{
		GridFrame a = SheetNoiseScreen(21);
		GridFrame b;
		//b is a, scrolled four cells to the left (the playfield moved east).
		for(uint32_t r = 0; r < kGridRows; r++) {
			for(uint32_t c = 0; c + 4 < kGridCols; c++) {
				b.Cells[r][c] = a.Cells[r][c + 4];
			}
		}
		ShiftMatch match = BestShift(a, b, 0, 0, 8, 0);
		Check(match.Dx == 4 && match.Dy == 0, "BlocoP: BestShift recovers a four-cell horizontal scroll",
			"dx=" + std::to_string(match.Dx) + " dy=" + std::to_string(match.Dy));
		Check(match.Score > 0.9, "BlocoP: the recovered shift matches nearly every cell");
	}

	//---- F9.8: adjacency evidence before two screens share a map -----------

	//A pseudo-random world, addressed in cells; a screen is a 32-column window
	//onto it, so two windows 32 columns apart are genuine neighbours and any
	//other pair is not.
	ShapeId SheetWorldCell(int32_t col, int32_t row)
	{
		uint32_t state = ((uint32_t)(col + 4096) * 73856093u) ^ ((uint32_t)(row + 4096) * 19349663u);
		state ^= state >> 13;
		state *= 1274126177u;
		return (ShapeId)(1 + (state >> 11) % 211);
	}

	GridFrame SheetWorldWindow(int32_t col0)
	{
		GridFrame frame;
		for(uint32_t r = 0; r < kGridRows; r++) {
			for(uint32_t c = 0; c < kGridCols; c++) {
				frame.Cells[r][c] = SheetWorldCell(col0 + (int32_t)c, (int32_t)r);
			}
		}
		return frame;
	}

	//A Punch-Out!!-shaped card: a tiled backdrop with a small figure on it and
	//nothing else. Two such cards match each other at any multiple of the
	//backdrop's period, so a bare "the shift matched" test glues them into one
	//map even though the game never scrolled a pixel.
	GridFrame SheetCardScreen(uint32_t figureCol, uint32_t figureRow, ShapeId figure)
	{
		GridFrame frame;
		for(uint32_t r = 0; r < kGridRows; r++) {
			for(uint32_t c = 0; c < kGridCols; c++) {
				frame.Cells[r][c] = (ShapeId)(2 + (c % 8) + (r % 2) * 8);
			}
		}
		for(uint32_t r = 0; r < 8; r++) {
			for(uint32_t c = 0; c < 8; c++) {
				frame.Cells[figureRow + r][figureCol + c] = (ShapeId)(figure + (r / 2) * 4 + (c / 2));
			}
		}
		return frame;
	}

	//Every aligned metatile of the given frames, no HUD band: the stitcher
	//tests are about geometry, not about classification.
	Vocabulary SheetStitchVocabulary(const std::vector<GridFrame>& frames)
	{
		Vocabulary vocab;
		vocab.Grid.Unit = 16;
		vocab.Grid.HasGrid = true;
		for(size_t i = 0; i < frames.size(); i++) {
			for(uint32_t r = 0; r + 1 < kGridRows; r += 2) {
				for(uint32_t c = 0; c + 1 < kGridCols; c += 2) {
					MetatileKey key;
					key.Tiles[0] = frames[i].Cells[r][c];
					key.Tiles[1] = frames[i].Cells[r][c + 1];
					key.Tiles[2] = frames[i].Cells[r + 1][c];
					key.Tiles[3] = frames[i].Cells[r + 1][c + 1];
					if(vocab.Index.find(key) != vocab.Index.end()) {
						continue;
					}
					vocab.Index[key] = (uint32_t)vocab.Entries.size();
					MetatileEntry entry;
					entry.Key = key;
					entry.Count = 1;
					vocab.Entries.push_back(entry);
				}
			}
		}
		return vocab;
	}

	void TestSheetStitchJoinsScreensThatShareABorderBand()
	{
		//Anchor at world column 0, candidate at 32, with the scroll caught in
		//between: each transition frame exposes a band that really is the
		//candidate's west edge, which is the evidence a join needs.
		std::vector<GridFrame> frames;
		const int32_t offsets[] = { 0, 8, 16, 24, 32 };
		for(size_t i = 0; i < 5; i++) {
			frames.push_back(SheetWorldWindow(offsets[i]));
		}
		std::vector<const GridFrame*> screens;
		screens.push_back(&frames[0]);
		screens.push_back(&frames[4]);

		std::vector<StitchedMap> maps = BuildMaps(frames, screens, SheetStitchVocabulary(frames));
		Check(maps.size() == 1, "BlocoP: two screens with a shared border band make one map",
			"maps=" + std::to_string(maps.size()));
		if(maps.size() == 1) {
			Check(maps[0].Mode == StitchMode::Screen && maps[0].Width == 2 * kGridCols * 8,
				"BlocoP: the joined map is exactly two screens wide",
				"width=" + std::to_string(maps[0].Width));
		}
	}

	void TestSheetStitchRefusesScreensWithoutAdjacencyEvidence()
	{
		//Two cards that never scroll, with the redraw caught in between. The
		//best shift between them still scores 0.85 - the backdrop matches
		//itself every two rows - and the band that shift exposes really is
		//backdrop, so even the band test alone would pass it: measured on this
		//fixture, band 1.00 over 64 cells, and with kStitchBandLead at 0 the
		//two cards come out stacked into one 256x480 map. What rejects it is that the band says nothing
		//the anchor did not already say (lead 0.00). With no evidence anywhere
		//there is no map at all: a map of one screen would only duplicate the
		//backgrounds/screenNNN.png the bootstrap already writes.
		std::vector<GridFrame> frames;
		frames.push_back(SheetCardScreen(4, 4, 100));
		frames.push_back(SheetCardScreen(4, 4, 100));
		frames[1].Cells[4][20] = 140; //a redraw has started
		frames.push_back(SheetCardScreen(20, 4, 140));
		frames[2].Cells[4][4] = 100;  //...and is not finished
		frames.push_back(SheetCardScreen(20, 4, 140));
		std::vector<const GridFrame*> screens;
		screens.push_back(&frames[0]);
		screens.push_back(&frames[3]);

		std::vector<StitchedMap> maps = BuildMaps(frames, screens, SheetStitchVocabulary(frames));
		size_t joined = 0;
		for(size_t i = 0; i < maps.size(); i++) {
			joined += maps[i].Width > kGridCols * 8 || maps[i].Height > kGridRows * 8 ? 1 : 0;
		}
		Check(joined == 0, "BlocoP: two unrelated screens are never concatenated",
			"joined=" + std::to_string(joined));
		Check(maps.empty(), "BlocoP: with no adjacency evidence anywhere, no map is emitted",
			"maps=" + std::to_string(maps.size()));
	}

	void TestSheetStitchKeepsAContinuousScrollInOneMap()
	{
		//The Excitebike shape: no stable screen at all, the camera walking two
		//cells per frame across a long world. This must still come out as one
		//continuous region - it is the regression guard for the evidence rule.
		std::vector<GridFrame> frames;
		for(int32_t i = 0; i < 120; i++) {
			GridFrame frame = SheetWorldWindow(i * 2);
			frame.FrameNumber = (uint32_t)i;
			frames.push_back(frame);
		}
		std::vector<const GridFrame*> screens;

		std::vector<StitchedMap> maps = BuildMaps(frames, screens, SheetStitchVocabulary(frames));
		Check(maps.size() == 1, "BlocoP: a continuous scroll stays one map",
			"maps=" + std::to_string(maps.size()));
		if(maps.size() == 1) {
			//119 frames of travel at 2 cells each, plus the 32-cell window.
			Check(maps[0].Mode == StitchMode::Continuous && maps[0].Width > kContinuousMinWidth * 3,
				"BlocoP: the continuous map spans the whole world it walked",
				"width=" + std::to_string(maps[0].Width));
		}
	}

	//---- F9.12: a continuous region ends when the world is replaced --------

	//The Super Mario Bros. shape: a title screen that *is* the level's first
	//screen with art stamped into it. `overlayCols` x `overlayRows` cells of
	//the window are replaced, so the two frames agree over
	//1 - (overlayCols * overlayRows) / (kGridRows * kGridCols) of the
	//playfield; 18x16 gives 0.70, which is what the installed recording
	//measures between screen001 and screen003 (see TileSheetTypes.h).
	GridFrame SheetOverlayScreen(int32_t col0, ShapeId overlay)
	{
		GridFrame frame = SheetWorldWindow(col0);
		for(uint32_t r = 2; r < 18; r++) {
			for(uint32_t c = 2; c < 20; c++) {
				frame.Cells[r][c] = (ShapeId)(overlay + (r % 4) * 4 + (c % 4));
			}
		}
		return frame;
	}

	void TestSheetStitchEndsARegionWhenTheWorldIsReplaced()
	{
		//Six title frames, then the same world with the title art gone and the
		//camera walking right. The step between them reports dx == 0 - the
		//camera really did not move - at 0.70 agreement, which clears kMinMatch
		//and used to keep one region: first-writer-wins then kept the overlay
		//and the level filled in around it. The title's own region is 256 px, so
		//it is dropped by kContinuousMinWidth and one map is left either way -
		//what the rule buys is that the map contains no title art.
		std::vector<GridFrame> frames;
		const ShapeId overlay = 400;
		for(int32_t i = 0; i < 6; i++) {
			GridFrame frame = SheetOverlayScreen(0, overlay);
			frame.FrameNumber = (uint32_t)i;
			frames.push_back(frame);
		}
		for(int32_t i = 0; i < 120; i++) {
			GridFrame frame = SheetWorldWindow(i);
			frame.FrameNumber = (uint32_t)(6 + i);
			frames.push_back(frame);
		}
		std::vector<const GridFrame*> screens;

		Vocabulary vocab = SheetStitchVocabulary(frames);
		std::vector<StitchedMap> maps = BuildMaps(frames, screens, vocab);
		Check(maps.size() == 1, "BlocoP: the replaced world leaves exactly one continuous map",
			"maps=" + std::to_string(maps.size()));
		if(maps.empty()) {
			return;
		}
		Check(maps[0].Mode == StitchMode::Continuous && maps[0].Width > kContinuousMinWidth,
			"BlocoP: the surviving map is the walked world, not the title screen",
			"width=" + std::to_string(maps[0].Width));

		//The load-bearing assertion: no placement on the map resolves to a
		//metatile that carries an overlay shape.
		size_t overlayPlacements = 0;
		for(size_t i = 0; i < maps[0].Placements.size(); i++) {
			uint32_t index = maps[0].Placements[i].Cell;
			if(index >= vocab.Entries.size()) {
				continue;
			}
			const MetatileKey& key = vocab.Entries[index].Key;
			for(size_t t = 0; t < key.Tiles.size(); t++) {
				overlayPlacements += key.Tiles[t] >= overlay ? 1 : 0;
			}
		}
		Check(overlayPlacements == 0, "BlocoP: no title-screen cell is welded into the level map",
			"overlayCells=" + std::to_string(overlayPlacements));
	}

	void TestSheetStitchKeepsAStillSceneInOneMap()
	{
		//The other side of the same rule: a scroller that stops. Sampled frames
		//that are the same place must not be read as a replaced world, or every
		//pause would chop the map. The walk stops for 30 frames halfway, and the
		//still frames are not byte-identical - a paused scene still animates
		//(coins, ? blocks, a waterfall), so 24 of the 960 playfield cells
		//flicker, i.e. the still score is 0.975 and not 1.00. That is the
		//headroom kStitchWorldAgree has to leave.
		std::vector<GridFrame> frames;
		for(int32_t i = 0; i < 60; i++) {
			GridFrame frame = SheetWorldWindow(i);
			frame.FrameNumber = (uint32_t)i;
			frames.push_back(frame);
		}
		for(int32_t i = 0; i < 30; i++) {
			GridFrame frame = SheetWorldWindow(59);
			for(uint32_t c = 0; c < 24; c++) {
				frame.Cells[10][c] = (ShapeId)(300 + (i % 3) * 24 + c);
			}
			frame.FrameNumber = (uint32_t)(60 + i);
			frames.push_back(frame);
		}
		for(int32_t i = 0; i < 60; i++) {
			GridFrame frame = SheetWorldWindow(59 + i);
			frame.FrameNumber = (uint32_t)(90 + i);
			frames.push_back(frame);
		}
		std::vector<const GridFrame*> screens;

		std::vector<StitchedMap> maps = BuildMaps(frames, screens, SheetStitchVocabulary(frames));
		Check(maps.size() == 1, "BlocoP: a scroller that pauses stays one map",
			"maps=" + std::to_string(maps.size()));
	}

	//F9.7 fixture: three renderings of one subject - a CHR bank swap that is
	//byte-identical under another id, a re-upload that lost one bitplane bit,
	//and one genuinely different subject - plus the pair that caught the first
	//budget rule: a blank cell and a cell that draws eight pixels.
	TileLookup SheetAliasLookup()
	{
		return [](ShapeId shape) -> const SheetTileKey* {
			static std::map<ShapeId, SheetTileKey> cache;
			std::map<ShapeId, SheetTileKey>::iterator it = cache.find(shape);
			if(it != cache.end()) {
				return &it->second;
			}
			SheetTileKey tile;
			if(shape >= 300) {
				//A blank cell, and its sparse neighbour drawing one tile row.
				tile.PaletteColors = 0x0F162A30;
				tile.TileData[0] = shape == 301 ? 0xFF : 0x00;
			} else {
				//120..123 mirror 20..23 exactly; 220..223 one bitplane bit off.
				tile = SheetTileFor(shape >= 120 && shape <= 223 ? (ShapeId)(shape % 100) : shape);
				if(shape >= 220) {
					tile.TileData[0] ^= 0x03;
				}
			}
			cache.insert(std::make_pair(shape, tile));
			return &cache.find(shape)->second;
		};
	}

	Vocabulary SheetAliasVocabulary(std::vector<uint32_t>& indexes)
	{
		Vocabulary vocab;
		vocab.Grid.Unit = 16;
		ShapeId keys[6][4] = {
			{ 20, 21, 22, 23 },     //canonical
			{ 40, 41, 42, 43 },     //a genuinely different subject
			{ 120, 121, 122, 123 }, //the same pixels under another CHR bank
			{ 220, 21, 22, 23 },    //the same subject, one bitplane bit off
			{ 300, 300, 300, 300 }, //blank
			{ 301, 300, 300, 300 }, //blank except eight pixels
		};
		indexes.clear();
		for(uint32_t i = 0; i < 6; i++) {
			MetatileEntry entry;
			entry.Key = MetatileKey{ { keys[i][0], keys[i][1], keys[i][2], keys[i][3] } };
			entry.Count = 10 - i;
			vocab.Entries.push_back(entry);
			indexes.push_back(i);
		}
		return vocab;
	}

	void TestSheetAliasesCollapseOntoTheFirstSurvivor()
	{
		std::vector<uint32_t> indexes;
		Vocabulary vocab = SheetAliasVocabulary(indexes);

		std::vector<std::vector<uint32_t>> aliases;
		std::vector<uint32_t> survivors = CollapseAliases(vocab, indexes, SheetAliasLookup(), SheetPalette(), kSheetAliasTolerance, aliases);
		Check(survivors.size() == 4, "BlocoP: three renderings of one subject leave one cell",
			"survivors=" + std::to_string(survivors.size()));
		if(survivors.size() == 4) {
			Check(survivors[0] == 0 && survivors[1] == 1,
				"BlocoP: the first index in the order survives, so the sheet keeps its count ranking");
			Check(aliases[0].size() == 2 && aliases[0][0] == 2 && aliases[0][1] == 3,
				"BlocoP: both duplicates are recorded as aliases of the survivor");
			Check(aliases[1].empty(), "BlocoP: a subject with no duplicate collects no aliases");
			//The regression the area-based budget caused: a near-empty cell
			//matched anything else that was mostly background, so one cell
			//absorbed 335 of Ninja Gaiden's 465 entries.
			Check(survivors[2] == 4 && survivors[3] == 5 && aliases[2].empty(),
				"BlocoP: a blank cell does not absorb a cell that draws something");
		}

		//At tolerance 0 only the byte-identical bank swap collapses - the
		//near-duplicate stays its own cell, so the tolerance is a real knob.
		aliases.clear();
		survivors = CollapseAliases(vocab, indexes, SheetAliasLookup(), SheetPalette(), 0.0, aliases);
		Check(survivors.size() == 5, "BlocoP: at tolerance 0 only exact duplicates collapse",
			"survivors=" + std::to_string(survivors.size()));
	}


	//--- F9.9 (ADR-0156): which surface owns a cell --------------------------
	//
	//A captured screen is written as backgrounds/screenNNN.png and drawn at
	//priority 20 (BehindFgSpritesPriority), i.e. *over* the background tiles.
	//So a cell whose every sighting sits where a captured screen already shows
	//it is never the pixel that reaches the display, and a cell spent on it in
	//metatiles.png is paint the artist can never see. These cases pin the two
	//halves of the disqualifier: an unexplained position, and an unexplained
	//fine scroll.

	//Shapes 900+ are the fixture's "figure": a 2x2 block an artist would
	//recognise as a subject, distinct from the backdrop vocabulary.
	const ShapeId kSheetFigureShape = 900;

	void SheetPlaceFigure(GridFrame& frame, uint32_t row, uint32_t col)
	{
		for(uint32_t r = 0; r < 2; r++) {
			for(uint32_t c = 0; c < 2; c++) {
				frame.Cells[row + r][col + c] = (ShapeId)(kSheetFigureShape + r * 2 + c);
			}
		}
	}

	//Two static screens, each held far past StableFramesNeeded, with a figure
	//standing on the first one. `captured` is what the recorder would set after
	//CaptureScreen wrote the PNG.
	std::vector<GridFrame> SheetScreenRecording(bool captured)
	{
		std::vector<GridFrame> frames;
		for(uint32_t i = 0; i < 2; i++) {
			GridFrame frame = SheetBlockScreen(i, 3);
			if(i == 0) {
				SheetPlaceFigure(frame, 10, 10);
			}
			frame.RepeatCount = 30;
			frame.FrameNumber = i;
			frame.Captured = captured;
			frames.push_back(frame);
		}
		return frames;
	}

	int32_t SheetFigureIndex(const Vocabulary& vocab)
	{
		return vocab.Find(MetatileKey{ { kSheetFigureShape, (ShapeId)(kSheetFigureShape + 1),
			(ShapeId)(kSheetFigureShape + 2), (ShapeId)(kSheetFigureShape + 3) } });
	}

	uint32_t SheetResidentCount(const Vocabulary& vocab)
	{
		uint32_t n = 0;
		for(size_t i = 0; i < vocab.Entries.size(); i++) {
			n += vocab.Entries[i].ScreenResident ? 1 : 0;
		}
		return n;
	}

	uint32_t SheetSceneCount(const Vocabulary& vocab)
	{
		uint32_t n = 0;
		for(size_t i = 0; i < vocab.Entries.size(); i++) {
			n += vocab.Entries[i].Context == SheetContext::Scene ? 1 : 0;
		}
		return n;
	}

	void TestSheetCapturedScreensOwnTheirCells()
	{
		std::vector<GridFrame> frames = SheetScreenRecording(true);
		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());

		uint32_t scene = SheetSceneCount(vocab);
		Check(scene > 0 && SheetResidentCount(vocab) == scene,
			"BlocoP: a recording that is nothing but captured screens routes every scene cell to them",
			"scene=" + std::to_string(scene) + " resident=" + std::to_string(SheetResidentCount(vocab)));
		//Routing is a sheet decision, never a vocabulary one: maps, objects and
		//sprites address entries by index (ADR-0153 §4, F9.7).
		Check(SheetFigureIndex(vocab) >= 0,
			"BlocoP: a routed cell keeps its vocabulary entry and its index");
	}

	void TestSheetACellSeenOffTheScreenStaysOnTheSheet()
	{
		//The figure walks: one frame nobody captured shows it two columns to the
		//right, where no <background> covers it. Its tiles do render there, so
		//the cell has to stay reachable on metatiles.png.
		std::vector<GridFrame> frames = SheetScreenRecording(true);
		GridFrame moved = SheetBlockScreen(0, 3);
		SheetPlaceFigure(moved, 10, 10);
		SheetPlaceFigure(moved, 10, 12);
		moved.FrameNumber = 2;
		frames.push_back(moved);

		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());
		int32_t figure = SheetFigureIndex(vocab);
		Check(figure >= 0, "BlocoP: the moving figure is in the vocabulary to begin with");
		if(figure < 0) {
			return;
		}
		Check(!vocab.Entries[figure].ScreenResident,
			"BlocoP: a cell seen at a position no captured screen explains stays on the contact sheet");
		Check(SheetResidentCount(vocab) > 0,
			"BlocoP: one moving cell does not drag the whole backdrop off the sheet",
			"resident=" + std::to_string(SheetResidentCount(vocab)));
	}

	void TestSheetAScrolledSightingIsNotExplained()
	{
		//The other half of the disqualifier, and the one that separates a
		//non-scrolling game from a scroller: the same cells, at the same grid
		//positions, under a fine scroll the captured screen was not showing.
		//The screen PNG is pixel-positional, so those are different pixels.
		std::vector<GridFrame> still = SheetScreenRecording(true);
		Vocabulary before = BuildVocabulary(still, SheetLookup());

		std::vector<GridFrame> scrolled = SheetScreenRecording(true);
		GridFrame shifted = SheetBlockScreen(0, 3);
		SheetPlaceFigure(shifted, 10, 10);
		shifted.FineX = 3;
		shifted.FrameNumber = 2;
		scrolled.push_back(shifted);
		Vocabulary after = BuildVocabulary(scrolled, SheetLookup());

		Check(SheetResidentCount(after) < SheetResidentCount(before),
			"BlocoP: a sighting under another fine scroll takes cells back off the screen surface",
			"before=" + std::to_string(SheetResidentCount(before)) + " after=" + std::to_string(SheetResidentCount(after)));
		int32_t figure = SheetFigureIndex(after);
		Check(figure >= 0 && !after.Entries[figure].ScreenResident,
			"BlocoP: the scrolled frame disqualifies the very cells it re-showed");
	}

	void TestSheetNothingIsRoutedWithoutACapturedScreen()
	{
		//A recording whose screens were never written out (the PNG failed, the
		//per-session cap was hit, or the frames never held still) has no
		//positional surface to route to, so nothing may leave the sheet.
		std::vector<GridFrame> frames = SheetScreenRecording(false);
		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());
		Check(SheetSceneCount(vocab) > 0 && SheetResidentCount(vocab) == 0,
			"BlocoP: with no captured screen, no cell is routed off the contact sheet",
			"resident=" + std::to_string(SheetResidentCount(vocab)));
	}

	void TestSheetResidencyLeavesTheHudSheetAlone()
	{
		//A status bar sits inside every captured screen, so the residency test
		//would empty hud.png and font.png - the two sheets whose whole point is
		//that the artist finds the HUD without hunting for it. Scene only.
		std::vector<GridFrame> frames;
		for(uint32_t i = 0; i < 3; i++) {
			GridFrame frame = SheetNoiseScreen(i + 1);
			//Four frozen rows, not two: a unit-16 metatile spans two rows, and
			//InHudBand only counts a cell whose every row is inside the band -
			//the reason ADR-0153 records hud.png coming out empty on Zelda,
			//whose status bar is three rows tall.
			for(uint32_t row = 0; row < 4; row++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					frame.Cells[row][c] = (ShapeId)(500 + row * 32 + c);
				}
			}
			for(uint32_t c = 24; c < kGridCols; c++) {
				frame.Cells[3][c] = (ShapeId)(900 + i * 32 + c);
			}
			frame.RepeatCount = 30;
			frame.FrameNumber = i;
			frame.Captured = true;
			frames.push_back(frame);
		}

		Vocabulary vocab = BuildVocabulary(frames, SheetLookup());
		uint32_t band = 0;
		uint32_t routedBand = 0;
		for(size_t i = 0; i < vocab.Entries.size(); i++) {
			SheetContext context = vocab.Entries[i].Context;
			if(context != SheetContext::Hud && context != SheetContext::Font) {
				continue;
			}
			band++;
			routedBand += vocab.Entries[i].ScreenResident ? 1 : 0;
		}
		Check(band > 0, "BlocoP: the fixture really does produce a status bar",
			"band=" + std::to_string(band));
		Check(routedBand == 0, "BlocoP: hud and font cells are never routed to the screen surface",
			"routed=" + std::to_string(routedBand));
	}


	void TestSheetContactSheetGeometry()
	{
		Vocabulary vocab;
		vocab.Grid.Unit = 16;
		std::vector<uint32_t> indexes;
		for(uint32_t i = 0; i < 4; i++) {
			MetatileEntry entry;
			entry.Key = MetatileKey{ { (ShapeId)(20 + i), (ShapeId)(20 + i), (ShapeId)(20 + i), (ShapeId)(20 + i) } };
			entry.Count = 10 - i;
			vocab.Entries.push_back(entry);
			indexes.push_back(i);
		}
		std::vector<SheetCell> cells;
		SheetImage image = BuildContactSheet(vocab, indexes, SheetLookup(), SheetPalette(), 2, cells);

		//2 columns x 2 rows of 16px cells, one gutter around and between.
		Check(image.Width == 2 * 17 + 1 && image.Height == 2 * 17 + 1,
			"BlocoP: the contact sheet is cells + gutters",
			std::to_string(image.Width) + "x" + std::to_string(image.Height));
		Check(cells.size() == 4, "BlocoP: every index gets a cell");
		if(cells.size() == 4) {
			Check(cells[0].X == 1 && cells[0].Y == 1, "BlocoP: the first cell starts after the gutter");
			Check(cells[1].X == 18 && cells[1].Y == 1, "BlocoP: the second cell is one stride east");
			Check(cells[2].X == 1 && cells[2].Y == 18, "BlocoP: the third cell wraps to the next row");
			Check(cells[3].Metatile == 3, "BlocoP: a cell carries its vocabulary index for the round-trip");
		}
	}

	void TestSheetUpscaleIsNearestNeighbour()
	{
		SheetImage source;
		source.Reset(2, 2);
		source.Row(0)[0] = 0xFF112233;
		source.Row(0)[1] = 0xFF445566;
		source.Row(1)[0] = 0xFF778899;
		source.Row(1)[1] = 0xFFAABBCC;

		SheetImage scaled = Upscale(source, 4);
		Check(scaled.Width == 8 && scaled.Height == 8, "BlocoP: Upscale multiplies both axes");
		Check(scaled.Row(0)[3] == 0xFF112233 && scaled.Row(3)[0] == 0xFF112233,
			"BlocoP: every source pixel becomes a solid NxN block");
		Check(scaled.Row(4)[4] == 0xFFAABBCC, "BlocoP: the last source pixel lands in the last block");
		Check(Upscale(source, 1).Pixels == source.Pixels, "BlocoP: a factor of 1 is the identity");
	}

	//F9.5 fixture: a four-tile figure that always holds the same 2x2 offsets
	//while the whole thing moves across the screen, plus a fifth sprite that
	//drifts to a fresh offset every frame - the bullet the criterion must
	//reject. Every offset the drifter takes is unique over these frames, so it
	//never reaches kSheetMinPairCount on any single one of them.
	std::vector<OamFrame> SpriteFigureFrames(uint32_t frames)
	{
		std::vector<OamFrame> out;
		for(uint32_t f = 0; f < frames; f++) {
			uint32_t x0 = 40 + f * 3;
			uint32_t y0 = 90 + (f % 5);
			OamFrame frame;
			frame.FrameNumber = f;
			for(uint32_t i = 0; i < 4; i++) {
				OamEntry entry;
				entry.Shape = (ShapeId)(1 + i);
				entry.X = (uint8_t)(x0 + (i % 2) * 8);
				entry.Y = (uint8_t)(y0 + (i / 2) * 8);
				frame.Entries.push_back(entry);
			}
			OamEntry drifter;
			drifter.Shape = 9;
			drifter.X = (uint8_t)(x0 + 24 - (f % 7) * 4);
			drifter.Y = (uint8_t)(y0 - 16 + (f % 5) * 6);
			frame.Entries.push_back(drifter);
			out.push_back(frame);
		}
		return out;
	}

	void TestSpriteOffsetGroupingRejectsADrifter()
	{
		std::vector<OamFrame> frames = SpriteFigureFrames(12);
		Vocabulary vocab = BuildSpriteVocabulary(frames);
		Check(vocab.Entries.size() == 5, "BlocoP: every distinct OAM shape reaches the sprite vocabulary",
			"entries=" + std::to_string(vocab.Entries.size()));
		Check(vocab.Grid.Unit == 8, "BlocoP: a sprite vocabulary is built on the 8x8 OAM unit");

		int32_t drifter = vocab.Find(MetatileKey{ { 9, kEmptyCell, kEmptyCell, kEmptyCell } });
		Check(drifter >= 0 && vocab.Entries[(size_t)drifter].Count == 12,
			"BlocoP: the drifter is on screen as often as the figure");

		std::vector<GroupEdge> edges = SelectSpriteEdges(frames, vocab, kSheetMinPairCount, kSheetMinPairProb);
		Check(edges.size() == 6, "BlocoP: the four figure tiles pair up in both directions",
			"edges=" + std::to_string(edges.size()));
		bool touchesDrifter = false;
		for(size_t i = 0; i < edges.size(); i++) {
			touchesDrifter |= (int32_t)edges[i].A == drifter || (int32_t)edges[i].B == drifter;
		}
		Check(!touchesDrifter, "BlocoP: a sprite that never holds one offset joins nothing");
	}

	void TestSpriteGroupIsLaidOutAtItsOamOffsets()
	{
		std::vector<OamFrame> frames = SpriteFigureFrames(12);
		Vocabulary vocab = BuildSpriteVocabulary(frames);
		std::vector<SheetGroup> groups = BuildSprites(frames, vocab);

		Check(groups.size() == 1, "BlocoP: exactly one sprite group comes out of the fixture",
			"groups=" + std::to_string(groups.size()));
		if(groups.size() != 1) {
			return;
		}
		Check(groups[0].Cells.size() == 4, "BlocoP: the group is the whole 2x2 figure, drifter excluded",
			"cells=" + std::to_string(groups[0].Cells.size()));
		Check(groups[0].Columns == 2 && groups[0].Rows == 2,
			"BlocoP: a 2x2 metasprite lays out 2x2, not in a row",
			std::to_string(groups[0].Columns) + "x" + std::to_string(groups[0].Rows));

		std::vector<SheetCell> cells;
		SheetImage image = RenderGroup(groups[0], vocab, SheetLookup(), SheetPalette(), cells, true);
		//2 columns x 2 rows of 8px cells, one gutter around and between.
		Check(image.Width == 2 * 9 + 1 && image.Height == 2 * 9 + 1,
			"BlocoP: a sprite sheet is 8px cells + gutters",
			std::to_string(image.Width) + "x" + std::to_string(image.Height));
		Check(cells.size() == 4 && cells[0].X == 1 && cells[0].Y == 1,
			"BlocoP: the first sprite cell starts after the gutter");
		Check(image.Pixels[0] == 0, "BlocoP: the gutter of a sprite sheet stays transparent");

		//Colour index 0 is the OAM backdrop: it must not ship as a box around
		//the figure. SheetTileFor's byte 0 is the shape id, byte 8 the shape id
		//plus 8, so the top-left pixel of shape 1 is index 0 either way.
		bool anyTransparentInsideACell = false;
		for(uint32_t y = 1; y < 9; y++) {
			for(uint32_t x = 1; x < 9; x++) {
				anyTransparentInsideACell |= image.Row(y)[x] == 0;
			}
		}
		Check(anyTransparentInsideACell, "BlocoP: OAM colour 0 is punched out of a sprite cell");
	}

	void TestSpriteSheetJsonCarriesTheOffsetEvidence()
	{
		std::vector<OamFrame> frames = SpriteFigureFrames(12);
		Vocabulary vocab = BuildSpriteVocabulary(frames);
		std::vector<SheetGroup> groups = BuildSprites(frames, vocab);
		Check(!groups.empty(), "BlocoP: the sprite JSON fixture has a group to serialise");
		if(groups.empty()) {
			return;
		}

		SheetJsonDoc doc;
		doc.Kind = "sprite";
		doc.SheetFile = "spr000.png";
		doc.ReferenceFile = "spr000.orig.png";
		doc.Grid = vocab.Grid;
		doc.CellWidth = doc.CellHeight = vocab.Grid.Unit;
		doc.Columns = groups[0].Columns;
		doc.Edges = groups[0].Edges;
		RenderGroup(groups[0], vocab, SheetLookup(), SheetPalette(), doc.Cells, true);

		std::string json = SerializeSheet(doc, SheetLookup());
		Check(json.find("\"kind\": \"sprite\"") != std::string::npos,
			"BlocoP: the sprite sidecar declares its kind");
		Check(json.find("\"gridUnit\": 8") != std::string::npos,
			"BlocoP: the sprite sidecar reports the 8x8 OAM unit");
		Check(json.find("\"reference\": \"spr000.orig.png\"") != std::string::npos,
			"BlocoP: the sprite sheet names its pixel-exact twin (F5.4d convention)");
		Check(json.find("\"dx\": 1, \"dy\": 0") != std::string::npos,
			"BlocoP: the evidence carries the OAM offset that joined two sprites");
		Check(json.find("\"pAB\": 1.0000") != std::string::npos,
			"BlocoP: a figure that never comes apart predicts itself perfectly");
		Check(json.find("\"metatile\": ") != std::string::npos,
			"BlocoP: a sprite cell carries its vocabulary index for the round-trip");
		Check(SerializeSheet(doc, SheetLookup()) == json, "BlocoP: sprite serialisation is deterministic");
	}

	void TestSheetJsonCarriesTheGridDecision()
	{
		SheetJsonDoc doc;
		doc.Kind = "metatiles";
		doc.SheetFile = "metatiles.png";
		doc.ReferenceFile = "metatiles.orig.png";
		doc.Grid.Unit = 16;
		doc.Grid.HasGrid = true;
		doc.Grid.PhaseAdvantage = 0.3447;
		doc.Grid.ChosenConsistency = 0.9938;
		doc.Grid.Alt8x8 = 0.9994;
		doc.Columns = 4;

		SheetCell cell;
		cell.Index = 0;
		cell.X = 1;
		cell.Y = 1;
		cell.Count = 431;
		cell.Metatile = 0;
		cell.Key = MetatileKey{ { 7, 7, 7, 7 } };
		doc.Cells.push_back(cell);

		std::string json = SerializeSheet(doc, SheetLookup());
		Check(json.find("\"version\": 1") != std::string::npos, "BlocoP: the sidecar declares schema version 1");
		Check(json.find("\"hasGrid\": true") != std::string::npos,
			"BlocoP: the sidecar carries the amended grid decision");
		Check(json.find("\"phaseAdvantage\": 0.3447") != std::string::npos,
			"BlocoP: the sidecar carries the phase advantage that made it");
		Check(json.find("\"label\": \"\"") != std::string::npos,
			"BlocoP: the artist's label field is always emitted and always empty");
		Check(json.find("\"tiles\": [{ \"tile\": \"") != std::string::npos,
			"BlocoP: a cell carries the exact hires.txt keys of its tiles");
		Check(SerializeSheet(doc, SheetLookup()) == json, "BlocoP: serialisation is deterministic");
	}
}

int main()
{
	TestSilentChannelNotSfx();
	TestFastSweepIsSfx();
	TestSlowGlideStaysMusic();
	TestLeadVsBassByMeanPitch();

	TestNormalizeRelativePathGolden();
	TestNormalizeRelativePathRejectsControlChars();
	TestParseValidPackJson();
	TestParseFailureCases();
	TestParseEmptySectionPath();

	TestFallbackSubfolderContra80sResolves();
	TestFallbackSubfolderAmbiguousIsEmpty();
	TestFallbackSubfolderDepthAndEntryCaps();

	TestDetectConventionLayoutBareRootHiresTxt();
	TestDetectConventionLayoutConventionWinsOverBareRoot();
	TestDetectConventionLayoutNoHiresTxtAtAll();
	TestDetectConventionLayoutMepHumanLayer();
	TestDetectConventionLayoutBorderSection();

	TestSha256KnownAnswer();
	TestFullDepsInstallMatchesPythonReference();
	TestMissingDepWithholdsPatchKeepsTextures();
	TestHashMismatchAbortsWritesNothing();
	TestUnknownOpAndVersionLogsAndSkips();
	TestDiscoveryEdgeCaseParity();

	TestFoldArpeggioToChord();
	TestEvaluateExpression();
	TestFixedRoleOverride();
	TestChannelStealRestore();
	TestArpeggioKeysDetection();

	TestContentIdGoldenParity();
	TestMepContentIdComputeFolder();

	TestFingerprintLoopLoad();
	TestFingerprintLoopAbsent();
	TestFingerprintLoopMalformed();
	TestFingerprintLoopSave();

	TestBorderDefaultHeuristic();
	TestBorderParseScaleMode();
	TestBorderFitLetterboxing();
	TestBorderStretch();
	TestBorderViewportClamping();
	TestBorderBlendOver();
	TestBorderCompositeOrdering();

	TestBgmCrossfadeIsPerSampleRamp();
	TestBgmCrossfadeIgnoresRunAheadBlocks();

	TestLoopPointReturnsToLoopPosition();
	TestNoLoopPointBehavesAsBefore();

	TestReplacementMuteMaskDefaultsToFullTonalMute();
	TestReplacementMuteMaskLetsSfxChannelsThrough();
	TestReplacementMuteMaskNeverTouchesDmcOrExpansion();

	TestEnhancedSynthPcmGolden();

	TestZipWellFormedPackExtracts();
	TestZipSlipTraversalEntryIsRejected();
	TestZipAbsolutePathEntryIsRejected();
	TestZipWindowsPathEntryIsRejected();
	TestZipSymlinkEntryCannotEscape();
	TestZipNestedWrapperFolderFallback();
	TestZipUnwrappedNoPackJsonIsRejected();
	TestZipCacheIsReusedUntilTheZipChanges();
	TestZipEmptyArchiveIsRejected();

	TestAspectRatioPerSetting();
	TestAspectRatioAutoPerConsole();
	TestStretchedSizePerSetting();

	TestToggleOverlayStaysReachableInAKeyboardGame();
	TestKeyboardBlockOnlyAppliesWhileRunning();
	TestKeyboardBlockSparesNonKeyboardInputs();
	TestSupersetStillShadowsTheExemptShortcut();

	TestSheetStableScreensCollapseRepeats();
	TestSheetHudRowsSurviveAChangingScore();
	TestSheetHudRowsIgnoreAnAllSkyScreen();
	TestSheetHudRowsSurviveATitleScreenInTheRecording();
	TestSheetGridPhaseAdvantageSeparatesGridFromNoise();
	TestSheetVocabularyCountsAndIsolationRule();
	TestSheetIsolatedMetatilesAreMisc();
	TestSheetMutualPredictabilityRejectsPromiscuousPairs();
	TestSheetObjectsAreLaidOutFromPredictiveEdges();
	TestSheetBestShiftRecoversTheScroll();
	TestSheetStitchJoinsScreensThatShareABorderBand();
	TestSheetStitchRefusesScreensWithoutAdjacencyEvidence();
	TestSheetStitchKeepsAContinuousScrollInOneMap();
	TestSheetStitchEndsARegionWhenTheWorldIsReplaced();
	TestSheetStitchKeepsAStillSceneInOneMap();
	TestSheetAliasesCollapseOntoTheFirstSurvivor();
	TestSheetCapturedScreensOwnTheirCells();
	TestSheetACellSeenOffTheScreenStaysOnTheSheet();
	TestSheetAScrolledSightingIsNotExplained();
	TestSheetNothingIsRoutedWithoutACapturedScreen();
	TestSheetResidencyLeavesTheHudSheetAlone();
	TestSheetContactSheetGeometry();
	TestSheetUpscaleIsNearestNeighbour();
	TestSheetJsonCarriesTheGridDecision();
	TestSpriteOffsetGroupingRejectsADrifter();
	TestSpriteGroupIsLaidOutAtItsOamOffsets();
	TestSpriteSheetJsonCarriesTheOffsetEvidence();

	printf("\n%d/%d cases passed\n", gCases - gFailures, gCases);
	return gFailures == 0 ? 0 : 1;
}
