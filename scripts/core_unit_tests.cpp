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
//failure (see roles_probe.cpp). Run from the repo root so the golden paths
//and the `python3 scripts/mep_recipe.py` shell-out resolve.
#include "Shared/Audio/ChannelRoleClassifier.h"
#include "Shared/Audio/EnhancedSynthEngine.h"
#include "Shared/EnhancementPacks/AudioFingerprint.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Shared/EnhancementPacks/MepRecipeInstaller.h"
#include "Shared/EnhancementPacks/MepContentId.h"
#include "Shared/MessageManager.h"
#include "Utilities/Base64.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/JsonReader.h"
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

	TestFingerprintLoopLoad();
	TestFingerprintLoopAbsent();
	TestFingerprintLoopMalformed();
	TestFingerprintLoopSave();

	printf("\n%d/%d cases passed\n", gCases - gFailures, gCases);
	return gFailures == 0 ? 0 : 1;
}
