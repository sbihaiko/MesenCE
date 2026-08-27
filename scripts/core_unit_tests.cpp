//Fase 4 (docs/roadmap/plano-testes-unitarios.md): framework-free C++ unit
//test harness - no MesenCore/emulator/ROM. Bloco A exercises
//ChannelRoleClassifier; Bloco B exercises MepPack::NormalizeRelativePath
//(driven by docs/specs/golden/mep/path-cases.txt) and MepPack::Parse; Bloco C
//(ADR-0120) exercises MepPack::FindFallbackSubfolder, the pure last-priority
//zip-fallback search PrepareZip consults, with literal fixtures; Bloco D
//(ADR-0121) exercises MepPack::DetectConventionLayout's bare-root hires.txt
//recognition against a real throwaway temp-dir tree (the one block here that
//touches the filesystem, since DetectConventionLayout itself does). No
//framework: cases print PASS/FAIL, exit is non-zero on any failure (see
//roles_probe.cpp). Run from the repo root so the golden paths resolve.
#include "Shared/Audio/ChannelRoleClassifier.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
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
}

int main()
{
	TestSilentChannelNotSfx();
	TestFastSweepIsSfx();
	TestSlowGlideStaysMusic();
	TestLeadVsBassByMeanPitch();

	TestNormalizeRelativePathGolden();
	TestParseValidPackJson();
	TestParseFailureCases();

	TestFallbackSubfolderContra80sResolves();
	TestFallbackSubfolderAmbiguousIsEmpty();
	TestFallbackSubfolderDepthAndEntryCaps();

	TestDetectConventionLayoutBareRootHiresTxt();
	TestDetectConventionLayoutConventionWinsOverBareRoot();
	TestDetectConventionLayoutNoHiresTxtAtAll();

	printf("\n%d/%d cases passed\n", gCases - gFailures, gCases);
	return gFailures == 0 ? 0 : 1;
}
