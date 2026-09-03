//Headless music-capture harness (F1 regression tool).
//Links directly against the freshly-built core dylib and includes the real
//SettingTypes.h, so config structs are passed with the exact ABI layout the
//core was compiled with - any drift fails at compile time instead of
//corrupting memory at run time.
//
//Build:   make capture-tool
//Usage:   scripts/headless_record <rom> <seconds> <output_prefix> [pal] [hdpack] [screenshot] [log] [mep-off|mep-notextures|mep-nosynth|mep-disable=<container>] [romtiles] [filter=<name>]
//
//Default mode writes <output_prefix>.mid and <output_prefix>.vgm from the
//ROM's first N seconds of audio (power-on attract/title music - no input is
//ever fed). With the "hdpack" flag it records an HD pack skeleton instead
//(tiles seen during those N seconds), written to <output_prefix>-hdpack/
//via the StartRecordHdPack shortcut (NES, GB and SMS/GG - F2 validation).
//With the "screenshot" flag it runs N seconds and saves the final frame to
//<home>/Screenshots/ - installing a recorded pack into <home>/HdPacks/<rom>/
//between two runs gives a with/without-replacement pair to diff (F2.3).
//With "filter=<name>" the video filter used by the screenshot pipeline is
//selected (none, hq2x, hq3x, hq4x, scale2x/3x/4x, xbrz2x..6x, prescale2x/3x/
//4x/6x/8x/10x); the default is "none", i.e. a 1:1 native-resolution frame.
//A scaling filter multiplies the PNG dimensions by its scale factor - this is
//what scripts/check_hq4x_screenshot.sh asserts for HQ4x (P.7).
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
	void SetNesConfig(NesConfig config);
	void SetGameboyConfig(GameboyConfig config);
	void SetEnhancementPackConfig(EnhancementPackConfig config);
	void SetVideoConfig(VideoConfig config);
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
		fprintf(stderr, "usage: %s <rom> <seconds> <output-prefix> [pal] [hdpack]\n", argv[0]);
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
	VideoFilterType videoFilter = VideoFilterType::None;
	EnhancementPackConfig mep = {};
	mep.BootstrapEnhancementFolder = false; //opt-in headless ("bootstrap" flag) - it writes beside the ROM
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
		} else if(strncmp(argv[i], "filter=", 7) == 0) {
			const char* name = argv[i] + 7;
			if(strcmp(name, "none") == 0) { videoFilter = VideoFilterType::None; }
			else if(strcmp(name, "hq2x") == 0) { videoFilter = VideoFilterType::HQ2x; }
			else if(strcmp(name, "hq3x") == 0) { videoFilter = VideoFilterType::HQ3x; }
			else if(strcmp(name, "hq4x") == 0) { videoFilter = VideoFilterType::HQ4x; }
			else if(strcmp(name, "scale2x") == 0) { videoFilter = VideoFilterType::Scale2x; }
			else if(strcmp(name, "scale3x") == 0) { videoFilter = VideoFilterType::Scale3x; }
			else if(strcmp(name, "scale4x") == 0) { videoFilter = VideoFilterType::Scale4x; }
			else if(strcmp(name, "xbrz2x") == 0) { videoFilter = VideoFilterType::xBRZ2x; }
			else if(strcmp(name, "xbrz3x") == 0) { videoFilter = VideoFilterType::xBRZ3x; }
			else if(strcmp(name, "xbrz4x") == 0) { videoFilter = VideoFilterType::xBRZ4x; }
			else if(strcmp(name, "xbrz5x") == 0) { videoFilter = VideoFilterType::xBRZ5x; }
			else if(strcmp(name, "xbrz6x") == 0) { videoFilter = VideoFilterType::xBRZ6x; }
			else if(strcmp(name, "prescale2x") == 0) { videoFilter = VideoFilterType::Prescale2x; }
			else if(strcmp(name, "prescale3x") == 0) { videoFilter = VideoFilterType::Prescale3x; }
			else if(strcmp(name, "prescale4x") == 0) { videoFilter = VideoFilterType::Prescale4x; }
			else if(strcmp(name, "prescale6x") == 0) { videoFilter = VideoFilterType::Prescale6x; }
			else if(strcmp(name, "prescale8x") == 0) { videoFilter = VideoFilterType::Prescale8x; }
			else if(strcmp(name, "prescale10x") == 0) { videoFilter = VideoFilterType::Prescale10x; }
			else {
				fprintf(stderr, "unknown filter name: %s\n", name);
				return 1;
			}
		} else if(strcmp(argv[i], "log") == 0) {
			dumpLog = true;
		} else if(strcmp(argv[i], "mep-off") == 0) {
			mep.EnableMepPacks = false;
		} else if(strcmp(argv[i], "mep-notextures") == 0) {
			mep.EnableTextures = false;
		} else if(strcmp(argv[i], "mep-nosynth") == 0) {
			mep.EnableSynth = false;
		} else if(strcmp(argv[i], "bootstrap") == 0) {
			mep.BootstrapEnhancementFolder = true;
		} else if(strcmp(argv[i], "mep-forcepatch") == 0) {
			mep.ApplyPatchOnHashMismatch = true;
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

	NesConfig nes = GetNesConfig();
	for(int i = 0; i < 11; i++) {
		nes.ChannelVolumes[i] = 100;
	}
	//Default 2C02 palette (the UI writes it into UserPalette; the core reads it
	//as-is, so without this every NES color - tiles, HD pack builder - is black)
	static const uint32_t kDefaultNesPalette[64] = {
		0xFF666666, 0xFF002A88, 0xFF1412A7, 0xFF3B00A4, 0xFF5C007E, 0xFF6E0040, 0xFF6C0600, 0xFF561D00, 0xFF333500, 0xFF0B4800, 0xFF005200, 0xFF004F08, 0xFF00404D, 0xFF000000, 0xFF000000, 0xFF000000, 0xFFADADAD, 0xFF155FD9, 0xFF4240FF, 0xFF7527FE, 0xFFA01ACC, 0xFFB71E7B, 0xFFB53120, 0xFF994E00, 0xFF6B6D00, 0xFF388700, 0xFF0C9300, 0xFF008F32, 0xFF007C8D, 0xFF000000, 0xFF000000, 0xFF000000, 0xFFFFFEFF, 0xFF64B0FF, 0xFF9290FF, 0xFFC676FF, 0xFFF36AFF, 0xFFFE6ECC, 0xFFFE8170, 0xFFEA9E22, 0xFFBCBE00, 0xFF88D800, 0xFF5CE430, 0xFF45E082, 0xFF48CDDE, 0xFF4F4F4F, 0xFF000000, 0xFF000000, 0xFFFFFEFF, 0xFFC0DFFF, 0xFFD3D2FF, 0xFFE8C8FF, 0xFFFBC2FF, 0xFFFEC4EA, 0xFFFECCC5, 0xFFF7D8A5, 0xFFE4E594, 0xFFCFEF96, 0xFFBDF4AB, 0xFFB3F3CC, 0xFFB5EBF2, 0xFFB8B8B8, 0xFF000000, 0xFF000000
	};
	bool paletteEmpty = true;
	for(int i = 0; i < 64; i++) {
		if(nes.UserPalette[i] != 0) {
			paletteEmpty = false;
			break;
		}
	}
	if(paletteEmpty) {
		memcpy(nes.UserPalette, kDefaultNesPalette, sizeof(kDefaultNesPalette));
		nes.IsFullColorPalette = false;
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

	//The screenshot pipeline (BaseVideoFilter::TakeScreenshot) runs the
	//configured scale filter before writing the PNG, so the video config has
	//to be pushed before the frame is captured. Every other field keeps the
	//struct's own default (neutral pipeline: no scanlines, no rotation).
	VideoConfig video = {};
	video.VideoFilter = videoFilter;
	SetVideoConfig(video);

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
