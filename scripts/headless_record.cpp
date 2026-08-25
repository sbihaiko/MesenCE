//Headless music-capture harness (F1 regression tool).
//Links directly against the freshly-built core dylib and includes the real
//SettingTypes.h, so config structs are passed with the exact ABI layout the
//core was compiled with - any drift fails at compile time instead of
//corrupting memory at run time.
//
//Build:   make capture-tool
//Usage:   scripts/headless_record <rom> <seconds> <output_prefix> [pal] [hdpack] [screenshot] [log] [mep-off|mep-notextures|mep-nosynth|mep-disable=<container>] [romtiles]
//
//Default mode writes <output_prefix>.mid and <output_prefix>.vgm from the
//ROM's first N seconds of audio (power-on attract/title music - no input is
//ever fed). With the "hdpack" flag it records an HD pack skeleton instead
//(tiles seen during those N seconds), written to <output_prefix>-hdpack/
//via the StartRecordHdPack shortcut (NES, GB and SMS/GG - F2 validation).
//With the "screenshot" flag it runs N seconds and saves the final frame to
//<home>/Screenshots/ - installing a recorded pack into <home>/HdPacks/<rom>/
//between two runs gives a with/without-replacement pair to diff (F2.3).
//With the "log" flag the core message log is dumped to stdout at the end
//(used by the F3 MEP tests to check "[MEP] ..." matching/rejection lines;
//the MEP folder is <home>/EnhancementPacks/ inside the scratch home).
//The mep-* flags exercise EnhancementPackConfig / SetMepPackEnabled (F3.3).
//"romtiles" runs the static ROM tile export (ExportRomTilesHdPack) into
//<output_prefix>-hdpack/ instead of recording.
//A scratch home folder is created next to the output; the NES game database
//is copied into it automatically when the tool runs from the repo root.
#include "Core/Shared/SettingTypes.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <filesystem>
#include <thread>
#include <chrono>

struct TimingInfoAbi
{
	double Fps;
	uint64_t MasterClock;
	uint32_t MasterClockRate;
	uint32_t FrameCount;
	uint32_t ScanlineCount;
	int32_t FirstScanline;
	uint32_t CycleCount;
};

//Same ABI as Core/Shared/Interfaces/INotificationListener.h (see the
//TimingInfoAbi note above about why these are mirrored locally)
struct ExecuteShortcutParamsAbi
{
	EmulatorShortcut Shortcut;
	uint32_t Param;
	void* ParamPtr;
};

extern "C"
{
	TimingInfoAbi GetTimingInfo(uint8_t cpuType);
	void InitDll();
	void InitializeEmu(const char* homeFolder, void* windowHandle, void* viewerHandle, bool softwareRenderer, bool noAudio, bool noVideo, bool noInput);
	bool LoadRom(char* filename, char* patchFile);
	void SetSmsConfig(SmsConfig config);
	void SetCvConfig(CvConfig config);
	void SetNesConfig(NesConfig config);
	void SetGameboyConfig(GameboyConfig config);
	void SetEnhancementPackConfig(EnhancementPackConfig config);
	void SetMepPackEnabled(const char* containerName, bool enabled);
	NesConfig GetNesConfig();
	void ExecuteShortcut(ExecuteShortcutParamsAbi params);
	void TakeScreenshot();
	void MidiRecord(char* filename);
	void MidiStop();
	bool MidiIsRecording();
	void VgmRecord(char* filename);
	void VgmStop();
	bool VgmIsRecording();
	bool IsRunning();
	void GetLog(char* outBuffer, uint32_t maxLength);
	void Stop();
	void Release();
}

namespace
{
	//Core/Shared/CpuType.h values for the consoles this tool records
	constexpr uint8_t kCpuTypeGameboy = 7;
	constexpr uint8_t kCpuTypeNes = 8;
	constexpr uint8_t kCpuTypeSms = 10;

	uint8_t CpuTypeFromExtension(const std::string& rom)
	{
		std::string ext = std::filesystem::path(rom).extension().string();
		for(char& c : ext) {
			c = (char)tolower(c);
		}
		if(ext == ".nes") {
			return kCpuTypeNes;
		}
		if(ext == ".gb" || ext == ".gbc") {
			return kCpuTypeGameboy;
		}
		return kCpuTypeSms; //.sms/.gg/.sg/.col
	}
}

int main(int argc, char** argv)
{
	if(argc < 4) {
		fprintf(stderr, "uso: %s <rom> <segundos> <prefixo-saida> [pal] [hdpack]\n", argv[0]);
		return 1;
	}
	std::string rom = argv[1];
	double seconds = atof(argv[2]);
	std::string prefix = argv[3];
	bool pal = false;
	bool hdPack = false;
	bool romTiles = false;
	bool screenshot = false;
	bool dumpLog = false;
	EnhancementPackConfig mep = {};
	std::string mepDisable;
	for(int i = 4; i < argc; i++) {
		if(strcmp(argv[i], "pal") == 0) {
			pal = true;
		} else if(strcmp(argv[i], "hdpack") == 0) {
			hdPack = true;
		} else if(strcmp(argv[i], "romtiles") == 0) {
			romTiles = true;
		} else if(strcmp(argv[i], "screenshot") == 0) {
			screenshot = true;
		} else if(strcmp(argv[i], "log") == 0) {
			dumpLog = true;
		} else if(strcmp(argv[i], "mep-off") == 0) {
			mep.EnableMepPacks = false;
		} else if(strcmp(argv[i], "mep-notextures") == 0) {
			mep.EnableTextures = false;
		} else if(strcmp(argv[i], "mep-nosynth") == 0) {
			mep.EnableSynth = false;
		} else if(strncmp(argv[i], "mep-disable=", 12) == 0) {
			mepDisable = argv[i] + 12;
		}
	}

	std::filesystem::path outDir = std::filesystem::absolute(prefix).parent_path();
	std::filesystem::path home = outDir / "mesen-home";
	std::filesystem::create_directories(home);

	//NES mapper detection wants the game DB in the home folder; copy it from
	//the repo checkout when available (silently skipped elsewhere).
	std::filesystem::path repoDb = "UI/Dependencies/MesenNesDB.txt";
	if(std::filesystem::exists(repoDb) && !std::filesystem::exists(home / "MesenNesDB.txt")) {
		std::filesystem::copy_file(repoDb, home / "MesenNesDB.txt");
	}

	InitDll();
	//Same headless pattern as UI/Utilities/TestRunner.cs: null handles mean
	//no renderer/sound/input backends are created at all.
	InitializeEmu(home.string().c_str(), nullptr, nullptr, true, true, true, true);

	//The GUI normally pushes every config struct at startup; headless we must
	//supply the audible channel volumes ourselves - the core-side defaults
	//for SMS/CV/NES ChannelVolumes are all ZERO (the UI-side defaults are the
	//100s the user actually hears), which would silence the enhanced synth
	//and therefore the MIDI capture. GB/SNES default to 100 in the core.
	SmsConfig sms = {};
	for(int i = 0; i < 4; i++) {
		sms.ChannelVolumes[i] = 100;
	}
	if(pal) {
		sms.Region = ConsoleRegion::Pal;
	}
	SetSmsConfig(sms);

	CvConfig cv = {};
	for(int i = 0; i < 4; i++) {
		cv.ChannelVolumes[i] = 100;
	}
	SetCvConfig(cv);

	NesConfig nes = GetNesConfig();
	for(int i = 0; i < 11; i++) {
		nes.ChannelVolumes[i] = 100;
	}
	if(pal) {
		nes.Region = ConsoleRegion::Pal;
	}
	SetNesConfig(nes);

	//Pin the GB model to the ROM extension so the HD pack capture path
	//(DMG vs CGB tile keys - ADR-0036) is deterministic; the default
	//AutoFavorGbc would run plain .gb ROMs on CGB hardware.
	GameboyConfig gameboy = {};
	gameboy.Model = std::filesystem::path(rom).extension() == ".gb" ? GameboyModel::Gameboy : GameboyModel::AutoFavorGbc;
	//Neutral video pipeline so a 1:1 HD pack screenshot matches the default
	//filter's output exactly (GbcAdjustColors/BlendFrames both recolor pixels)
	gameboy.GbcAdjustColors = false;
	gameboy.BlendFrames = false;
	SetGameboyConfig(gameboy);

	SetEnhancementPackConfig(mep);
	if(!mepDisable.empty()) {
		SetMepPackEnabled(mepDisable.c_str(), false);
	}

	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "FALHA ao carregar ROM: %s\n", rom.c_str());
		return 1;
	}
	TimingInfoAbi timing = GetTimingInfo(CpuTypeFromExtension(rom));
	printf("ROM carregada: %s%s\n", rom.c_str(), pal ? " [regiao forcada: PAL]" : "");
	printf("fps emulado: %.3f (clock mestre %u Hz)\n", timing.Fps, timing.MasterClockRate);

	std::string mid = prefix + ".mid", vgm = prefix + ".vgm";
	std::string packFolder = std::filesystem::absolute(prefix + "-hdpack").string();
	if(romTiles) {
		HdPackBuilderOptions options = {};
		options.SaveFolder = (char*)packFolder.c_str();
		options.FilterType = ScaleFilterType::Prescale;
		options.Scale = 1;
		options.ChrRamBankSize = 0x1000;
		ExecuteShortcut({ EmulatorShortcut::ExportRomTilesHdPack, 0, &options });
		printf("export estatico de tiles: hdpack=%s\n", packFolder.c_str());
		//short grace period so the emulation thread is fully up before Stop()
		seconds = std::min(seconds, 0.5);
	} else if(hdPack) {
		HdPackBuilderOptions options = {};
		options.SaveFolder = (char*)packFolder.c_str();
		options.FilterType = ScaleFilterType::Prescale;
		options.Scale = 1;
		options.ChrRamBankSize = 0x1000; //NES-only field
		ExecuteShortcut({ EmulatorShortcut::StartRecordHdPack, 0, &options });
		printf("gravando: hdpack=%s\n", packFolder.c_str());
	} else if(screenshot) {
		printf("rodando %.1fs para screenshot final\n", seconds);
	} else {
		MidiRecord((char*)mid.c_str());
		VgmRecord((char*)vgm.c_str());
		printf("gravando: midi=%d vgm=%d\n", MidiIsRecording(), VgmIsRecording());
	}

	auto t0 = std::chrono::steady_clock::now();
	while(std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count() < seconds) {
		std::this_thread::sleep_for(std::chrono::milliseconds(250));
		if(!IsRunning()) {
			fprintf(stderr, "emulacao parou inesperadamente\n");
			break;
		}
	}

	if(screenshot) {
		TakeScreenshot();
		printf("screenshot salvo em %s\n", (home / "Screenshots").string().c_str());
	}

	if(hdPack) {
		ExecuteShortcut({ EmulatorShortcut::StopRecordHdPack, 0, nullptr });
	} else if(!screenshot) {
		MidiStop();
		VgmStop();
	}
	printf("captura encerrada (%.1fs)\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
	if(dumpLog) {
		std::string log(65536, '\0');
		GetLog(log.data(), (uint32_t)log.size());
		log.resize(strlen(log.c_str()));
		printf("--- core log ---\n%s--- end log ---\n", log.c_str());
	}
	Stop();
	Release();
	return 0;
}
