//F5.4g Bloco A validation harness (ADR-0052 item 7): runs a NES ROM headless,
//samples the APU state while the game plays (optionally from a save state and
//with scripted controller input), feeds the very same ChannelRoleClassifier
//the Enhanced Audio synth uses, and prints what it decided: a timeline of
//role assignments and SFX segments plus per-channel statistics. With --wav it
//also records the mixed output (Enhanced Audio on, optional SoundFont) so the
//level-2 render can be checked without the GUI.
//
//Build: `make roles-probe` (after `make core`).
//Usage: scripts/roles_probe <rom.nes> <workdir> [seconds=20]
//         [--state file.mss] [--input "<script>"] [--wav out.wav] [--sf2 file.sf2]
//         [--no-auto-roles] [--no-sfx]
//  --input script: comma-separated "button@start[-end][/period]" (seconds of
//  emulated time). Without /period the button is held for the range; with it,
//  it is pressed for 3 frames every "period" seconds. Buttons: a b start
//  select up down left right. Example: "start@0.5-3/0.25,right@4-20,a@5-20/0.9"
#include "Core/Shared/SettingTypes.h"
#include "Core/Shared/CpuType.h"
#include "Core/Debugger/DebugTypes.h"
#include "Core/NES/NesTypes.h"
#include "Shared/Audio/ChannelRoleClassifier.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

struct ExecuteShortcutParamsAbi
{
	EmulatorShortcut Shortcut;
	uint32_t Param;
	void* ParamPtr;
};

extern "C"
{
	void InitDll();
	void InitializeEmu(const char* homeFolder, void* windowHandle, void* viewerHandle, bool softwareRenderer, bool noAudio, bool noVideo, bool noInput);
	bool LoadRom(char* filename, char* patchFile);
	void ExecuteShortcut(ExecuteShortcutParamsAbi params);
	bool IsRunning();
	void Stop();
	void Release();
	void LoadStateFile(char* filepath);
	NesConfig GetNesConfig();
	void SetNesConfig(NesConfig config);
	void SetAudioConfig(AudioConfig config);
	void SetEnhancementPackConfig(EnhancementPackConfig config);
	void SetPreferences(PreferencesConfig config);
	void SetEmulationFlag(EmulationFlags flag, bool enabled);
	void InitializeDebugger();
	void SetInputOverrides(uint32_t index, DebugControllerState state);
	void GetConsoleState(BaseState& state, ConsoleType consoleType);
	void WaveRecord(char* filename);
	void WaveStop();
}

namespace
{
	void SleepMs(int ms)
	{
		std::this_thread::sleep_for(std::chrono::milliseconds(ms));
	}

	double EnvVolume(const ApuEnvelopeState& env)
	{
		return (env.ConstantVolume ? env.Volume : env.Counter) / 15.0;
	}

	struct InputEvent
	{
		std::string Button;
		double Start = 0;
		double End = 0;
		double Period = 0; //0 = hold
	};

	std::vector<InputEvent> ParseInput(const std::string& script)
	{
		std::vector<InputEvent> events;
		size_t pos = 0;
		while(pos < script.size()) {
			size_t comma = script.find(',', pos);
			std::string tok = script.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
			pos = comma == std::string::npos ? script.size() : comma + 1;
			size_t at = tok.find('@');
			if(at == std::string::npos) {
				continue;
			}
			InputEvent ev;
			ev.Button = tok.substr(0, at);
			std::string rest = tok.substr(at + 1);
			size_t slash = rest.find('/');
			if(slash != std::string::npos) {
				ev.Period = atof(rest.substr(slash + 1).c_str());
				rest = rest.substr(0, slash);
			}
			size_t dash = rest.find('-');
			ev.Start = atof(rest.substr(0, dash).c_str());
			ev.End = dash == std::string::npos ? ev.Start + 0.05 : atof(rest.substr(dash + 1).c_str());
			events.push_back(ev);
		}
		return events;
	}

	void ApplyButton(DebugControllerState& st, const std::string& b, bool on)
	{
		if(b == "a") {
			st.A = on;
		} else if(b == "b") {
			st.B = on;
		} else if(b == "start") {
			st.Start = on;
		} else if(b == "select") {
			st.Select = on;
		} else if(b == "up") {
			st.Up = on;
		} else if(b == "down") {
			st.Down = on;
		} else if(b == "left") {
			st.Left = on;
		} else if(b == "right") {
			st.Right = on;
		}
	}

	const char* ChName(int i)
	{
		return i == 0 ? "sq1" : i == 1 ? "sq2" :
													"tri";
	}
}

int main(int argc, char** argv)
{
	if(argc < 3) {
		fprintf(stderr, "uso: %s <rom.nes> <workdir> [seconds=20] [--state f.mss] [--input script] [--wav out.wav] [--sf2 f.sf2] [--no-auto-roles] [--no-sfx]\n", argv[0]);
		return 1;
	}
	std::string rom = argv[1];
	std::filesystem::path work = argv[2];
	double seconds = 20;
	std::string statePath, inputScript, wavPath, sf2Path;
	bool autoRoles = true, sfxSep = true;
	bool enhanced = true; //--no-enhanced: play the raw APU instead of the F1 synth
	uint32_t apuMix = 0; //--apu-mix N
	uint32_t preset = 4; //--preset N (0 Synthwave, 1 ChipDeluxe, 2 OrchestralLite, 3 Dry, 4 Studio)
	bool packAudio = false; //--pack-audio: enable the pack's OGG layer (EnableAudio)
	bool patches = false; //--patches: let the pack apply its <patch> (ROM patch layer)
	bool synth = false; //--synth: enable the pack synth layer (EnableSynth) like the GUI does
	bool bootstrap = false; //--bootstrap: let the MEP bootstrap recorder run (writes beside the ROM - use a copy!)
	bool packs = false; //--packs: enable the ROM's enhancement packs (textures on, OGG off, patch off)
	for(int i = 3; i < argc; i++) {
		std::string a = argv[i];
		auto next = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
		if(a == "--state") {
			statePath = next();
		} else if(a == "--input") {
			inputScript = next();
		} else if(a == "--wav") {
			wavPath = next();
		} else if(a == "--sf2") {
			sf2Path = next();
		} else if(a == "--no-auto-roles") {
			autoRoles = false;
		} else if(a == "--no-sfx") {
			sfxSep = false;
		} else if(a == "--packs") {
			packs = true;
		} else if(a == "--bootstrap") {
			bootstrap = true;
		} else if(a == "--synth") {
			synth = true;
		} else if(a == "--patches") {
			patches = true;
		} else if(a == "--pack-audio") {
			packAudio = true;
		} else if(a == "--no-enhanced") {
			enhanced = false;
		} else if(a == "--apu-mix") {
			apuMix = (uint32_t)atoi(next().c_str());
		} else if(a == "--preset") {
			preset = (uint32_t)atoi(next().c_str());
		} else {
			seconds = atof(a.c_str());
		}
	}
	std::filesystem::create_directories(work);
	std::filesystem::path home = work / "mesen-home";
	std::filesystem::create_directories(home);

	InitDll();
	InitializeEmu(home.string().c_str(), nullptr, nullptr, true, true, true, true);
	{
		//Never write beside the user's ROM from a harness
		EnhancementPackConfig mep = {};
		mep.EnableMepPacks = packs;
		mep.EnableTextures = packs;
		mep.EnableAudio = packAudio;
		mep.EnablePatches = patches;
		mep.EnableSynth = synth;
		mep.BootstrapEnhancementFolder = bootstrap;
		if(bootstrap) {
			mep.EnableMepPacks = true;
		}
		SetEnhancementPackConfig(mep);
	}
	{
		NesConfig nes = GetNesConfig();
		for(int i = 0; i < 11; i++) {
			nes.ChannelVolumes[i] = 100;
		}
		nes.Port1.Type = ControllerType::NesController;
		SetNesConfig(nes);
	}
	{
		//Same defaults as SettingTypes.h + the level-2 switches under test.
		//Must be set before LoadRom: the synth loads the SoundFont in its
		//constructor.
		AudioConfig audio = {};
		audio.EnableAudio = true;
		audio.MasterVolume = 100;
		audio.EnhancedAudioVolume = 100;
		audio.EnhancedAudioApuMix = apuMix;
		audio.EnhancedAudioPreset = preset;
		audio.EnableEnhancedAudio = enhanced;
		audio.EnhancedAudioAutoRoles = autoRoles;
		audio.EnhancedAudioSfxSeparation = sfxSep;
		audio.EnhancedAudioSoundFontPath = sf2Path.c_str();
		SetAudioConfig(audio);
	}
	{
		//Core log lines ("[EnhancedAudio] SoundFont loaded: ...") to stdout
		SetEmulationFlag(EmulationFlags::OutputToStdout, true);
		PreferencesConfig prefs = {};
		SetPreferences(prefs);
	}
	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "FALHA ao carregar ROM\n");
		return 2;
	}
	InitializeDebugger(); //input overrides + console state
	if(!statePath.empty()) {
		SleepMs(300);
		LoadStateFile((char*)statePath.c_str());
	}
	if(!wavPath.empty()) {
		WaveRecord((char*)wavPath.c_str());
	}

	std::vector<InputEvent> events = ParseInput(inputScript);

	//Offline classifier fed with the same figures the NES wrapper builds
	static constexpr ChannelRoleClassifier::ChannelRole defaultRoles[3] = { ChannelRoleClassifier::ChannelRole::Lead, ChannelRoleClassifier::ChannelRole::Harmony, ChannelRoleClassifier::ChannelRole::Bass };
	ChannelRoleClassifier roles;
	roles.Init(3, defaultRoles);
	roles.SetAutoRoles(autoRoles);
	roles.SetSfxSeparation(sfxSep);

	NesState st = {};
	GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
	uint32_t frame0 = st.Ppu.FrameCount;
	uint32_t lastFrame = frame0;

	ChannelRoleClassifier::ChannelRole lastRole[3] = { defaultRoles[0], defaultRoles[1], defaultRoles[2] };
	bool lastSfx[3] = {};
	double sfxStart[3] = {};
	double sfxMinNote[3] = {}, sfxMaxNote[3] = {};
	uint8_t sfxCues[3] = {};
	auto cueNames = [](uint8_t c) {
		std::string s;
		if(c & ChannelRoleClassifier::CueSweep) {
			s += "sweep ";
		}
		if(c & ChannelRoleClassifier::CueGlide) {
			s += "glide ";
		}
		if(c & ChannelRoleClassifier::CueSqueak) {
			s += "squeak ";
		}
		if(c & ChannelRoleClassifier::CueRetrigger) {
			s += "retrig ";
		}
		return s.empty() ? std::string("hold") : s;
	};
	double roleTime[3][3] = {};
	double sfxTime[3] = {};
	int sfxSegments[3] = {};
	int roleChanges = 0;
	double audibleTime[3] = {};
	double t = 0;
	DebugControllerState pad = {};

	printf("# %s  %.0fs  auto-roles=%d sfx=%d state=%s sf2=%s\n", std::filesystem::path(rom).filename().string().c_str(), seconds, autoRoles, sfxSep, statePath.empty() ? "-" : statePath.c_str(), sf2Path.empty() ? "-" : sf2Path.c_str());
	printf("# t(s)   event\n");
	while(t < seconds) {
		SleepMs(4);
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		uint32_t frame = st.Ppu.FrameCount;
		if(frame == lastFrame) {
			continue;
		}
		double dt = (double)(frame - lastFrame) / 60.0;
		lastFrame = frame;
		t = (frame - frame0) / 60.0;

		//Scripted input
		DebugControllerState want = {};
		for(const InputEvent& ev : events) {
			if(t < ev.Start || t > ev.End) {
				continue;
			}
			bool on = true;
			if(ev.Period > 0) {
				double phase = std::fmod(t - ev.Start, ev.Period);
				on = phase < 3.0 / 60.0;
			}
			if(on) {
				ApplyButton(want, ev.Button, true);
			}
		}
		if(memcmp(&want, &pad, sizeof(pad)) != 0) {
			pad = want;
			SetInputOverrides(0, pad);
		}

		ApuState& a = st.Apu;
		ChannelRoleClassifier::Channel ch[3];
		ch[0].Freq = a.Square1.Frequency;
		if(a.Square1.Enabled && a.Square1.LengthCounter.Counter > 0 && a.Square1.Period >= 8) {
			ch[0].Vol = EnvVolume(a.Square1.Envelope);
		}
		ch[0].HwSweep = a.Square1.SweepEnabled && a.Square1.SweepShift > 0;
		ch[1].Freq = a.Square2.Frequency;
		if(a.Square2.Enabled && a.Square2.LengthCounter.Counter > 0 && a.Square2.Period >= 8) {
			ch[1].Vol = EnvVolume(a.Square2.Envelope);
		}
		ch[1].HwSweep = a.Square2.SweepEnabled && a.Square2.SweepShift > 0;
		ch[2].Freq = a.Triangle.Frequency;
		if(a.Triangle.Enabled && a.Triangle.LengthCounter.Counter > 0 && a.Triangle.LinearCounter > 0 && a.Triangle.Period >= 2) {
			ch[2].Vol = 1.0;
		}
		roles.Update(ch, dt);

		for(int i = 0; i < 3; i++) {
			if(ch[i].Vol > 0.001) {
				audibleTime[i] += dt;
			}
			bool sfx = roles.IsSfx(i);
			if(sfx) {
				sfxTime[i] += dt;
				double note = ch[i].Freq > 1 ? 69.0 + 12.0 * std::log2(ch[i].Freq / 440.0) : 0;
				if(!lastSfx[i]) {
					sfxStart[i] = t;
					sfxMinNote[i] = sfxMaxNote[i] = note;
					sfxSegments[i]++;
					sfxCues[i] = roles.SfxCues(i);
				} else {
					sfxCues[i] |= roles.SfxCues(i);
					sfxMinNote[i] = std::min(sfxMinNote[i], note);
					sfxMaxNote[i] = std::max(sfxMaxNote[i], note);
				}
			} else if(lastSfx[i]) {
				printf("%7.2f  sfx  %s  %.2fs  notes %.0f..%.0f  [%s]\n", sfxStart[i], ChName(i), t - sfxStart[i], sfxMinNote[i], sfxMaxNote[i], cueNames(sfxCues[i]).c_str());
			}
			lastSfx[i] = sfx;
			if(!sfx) {
				roleTime[i][(int)roles.Role(i)] += dt;
			}
		}
		bool changed = false;
		for(int i = 0; i < 3; i++) {
			changed |= roles.Role(i) != lastRole[i];
		}
		if(changed) {
			roleChanges++;
			printf("%7.2f  roles sq1=%s sq2=%s tri=%s  (mean note %.0f/%.0f/%.0f, onsets/s %.1f/%.1f/%.1f)\n", t, ChannelRoleClassifier::RoleName(roles.Role(0)), ChannelRoleClassifier::RoleName(roles.Role(1)), ChannelRoleClassifier::RoleName(roles.Role(2)), roles.MeanNote(0), roles.MeanNote(1), roles.MeanNote(2), roles.OnsetRate(0), roles.OnsetRate(1), roles.OnsetRate(2));
			for(int i = 0; i < 3; i++) {
				lastRole[i] = roles.Role(i);
			}
		}
	}
	for(int i = 0; i < 3; i++) {
		if(lastSfx[i]) {
			printf("%7.2f  sfx  %s  %.2fs  notes %.0f..%.0f (open)\n", sfxStart[i], ChName(i), t - sfxStart[i], sfxMinNote[i], sfxMaxNote[i]);
		}
	}

	printf("\n# summary (%.1fs emulated)\n", t);
	printf("# ch   audible   lead    harm    bass    sfx(segments)\n");
	for(int i = 0; i < 3; i++) {
		printf("# %s  %5.1f%%   %5.1f%%  %5.1f%%  %5.1f%%  %5.1f%% (%d)\n", ChName(i), 100.0 * audibleTime[i] / t, 100.0 * roleTime[i][0] / t, 100.0 * roleTime[i][1] / t, 100.0 * roleTime[i][2] / t, 100.0 * sfxTime[i] / t, sfxSegments[i]);
	}
	printf("# role changes: %d\n", roleChanges);

	if(!wavPath.empty()) {
		WaveStop();
		printf("# wav: %s\n", wavPath.c_str());
	}
	DebugControllerState none = {};
	SetInputOverrides(0, none);
	Stop();
	Release();
	return 0;
}
