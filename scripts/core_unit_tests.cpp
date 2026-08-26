//Fase 4 (docs/roadmap/plano-testes-unitarios.md): framework-free C++ unit
//test harness - no MesenCore/emulator/ROM. Bloco A exercises
//ChannelRoleClassifier; Bloco B exercises MepPack::NormalizeRelativePath
//(driven by docs/specs/golden/mep/path-cases.txt) and MepPack::Parse. No
//framework: cases print PASS/FAIL, exit is non-zero on any failure (see
//roles_probe.cpp). Run from the repo root so the golden paths resolve.
#include "Shared/Audio/ChannelRoleClassifier.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>

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

	printf("\n%d/%d cases passed\n", gCases - gFailures, gCases);
	return gFailures == 0 ? 0 : 1;
}
