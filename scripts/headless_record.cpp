//Headless music-capture harness (F1 regression tool).
//Links directly against the freshly-built core dylib and includes the real
//SettingTypes.h, so config structs are passed with the exact ABI layout the
//core was compiled with - any drift fails at compile time instead of
//corrupting memory at run time.
//
//Build:   make capture-tool
//Usage:   scripts/headless_record <rom> <seconds> <output_prefix> [pal] [hdpack] [screenshot] [log] [mep-off|mep-notextures|mep-nosynth|mep-disable=<container>] [romtiles] [filter=<name>] [live=<ms>]
//
//F9.14 (ADR-0157): a run is a number of *emulated frames*, never a number of
//host seconds. <seconds> keeps its name and its meaning for the caller, but is
//converted to a frame count here, at the region's nominal frame rate, and the
//run stops when the core's own frame counter reaches it - both ends of the
//recording are decided from inside the frame (HeadlessInputProvider), so two
//runs of the same ROM, script and binary cover exactly the same frames on any
//host load. The frame limiter is therefore pointless and is turned off
//(EmulationSpeed 0): speed is a free variable that no longer changes what a
//recording contains. Pass "realtime" to keep it on.
//
//<seconds> is *emulated* seconds, and it is the argument, not a frame count -
//passing a frame count by mistake asks for hours of emulation. Measured on an
//M-series host, 2026-09-07: 600 emulated seconds (36060 frames) take 59s of
//wall clock plain and 173s with "bootstrap", i.e. the builder costs about 3x
//the emulator. Budget a validation recording at <= 2 minutes of wall clock -
//roughly 400 emulated seconds with "bootstrap", 1200 without. A recording
//that runs past 5 minutes is a mistake in the invocation, not a slow tool:
//check the unit of <seconds> first.
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
//With the "capture" flag the final frame is pulled into this process' memory
//(HeadlessCaptureFrame/HeadlessReadCapturedPixels, F9.15) instead of - or as
//well as - being written to a PNG, and its dimensions, frame number, FNV-1a
//checksum and uniform border bands are printed. That is what turns a check a
//human used to make by opening a screenshot (letterboxing, a card on screen)
//into a line a shell script can assert on.
//With the "log" flag the core message log is dumped to stdout at the end
//(used by the F3 MEP tests to check "[MEP] ..." matching/rejection lines;
//the MEP folder is <home>/EnhancementPacks/ inside the scratch home).
//The mep-* flags exercise EnhancementPackConfig / SetMepPackEnabled (F3.3).
//"romtiles" runs the static ROM tile export (ExportRomTilesHdPack) into
//<output_prefix>-hdpack/ instead of recording.
//With "live=<ms>" the run publishes itself while it plays (ADR-0169), into a
//scratch folder named <output_prefix>-live/ that is never part of the pack:
//frame.ppm (the composed frame, P6), status.json (frame, target, wall clock)
//and - on a NES run - the sprite layer as data: sprites.json (per-capture OAM,
//palette and the $2000 sprite-control bits from a direct console read, taken
//with the emulation thread held at an end-of-frame boundary) plus chr.bin (the
//mapper-resolved pattern tables) and one palette.json written at startup with
//the exact RGB the run renders with. The viewer that draws these
//is scripts/record_viewer.py. Publishing is lossy-latest on purpose (a slow
//viewer must skip, never block the run) and off by default; if the folder
//cannot be written the run logs one line and continues.
//A scratch home folder is created next to the output; the NES game database
//is copied into it automatically when the tool runs from the repo root.
#include "Core/Shared/SettingTypes.h"
#include "Core/Shared/Video/FrameCapture.h"
//ADR-0169: the live sprite layer is published as data - OAM, palette and the
//mapper-resolved pattern tables are read off the console by the wrapper export
//HeadlessCaptureNesSpriteLayer, and the $2000 sprite-control bits come back in
//a NesPpuState. NesTypes.h keeps the ABI the exact one the core was built with.
#include "NES/NesTypes.h"
#include "Utilities/LiveRecordFormat.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <filesystem>
#include <thread>
#include <chrono>
#include <functional>

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
	void LoadStateFile(char* filepath);
	TimingInfoAbi GetTimingInfo(uint8_t cpuType);
	void InitDll();
	void InitializeEmu(const char* homeFolder, void* windowHandle, void* viewerHandle, bool softwareRenderer, bool noAudio, bool noVideo, bool noInput);
	bool LoadRom(char* filename, char* patchFile);
	void SetSmsConfig(SmsConfig config);
	void SetNesConfig(NesConfig config);
	void SetGameboyConfig(GameboyConfig config);
	void SetEnhancementPackConfig(EnhancementPackConfig config);
	void SetVideoConfig(VideoConfig config);
	void SetEmulationConfig(EmulationConfig config);
	void SetMepPackEnabled(const char* containerName, bool enabled);
	//F9.14 (ADR-0157) - InteropDLL/EmuApiWrapperHeadless.cpp
	bool HeadlessLoadInputScript(const char* scriptText, double frameRate, char* outError, uint32_t maxErrorLength);
	void HeadlessSetPauseFrame(uint32_t frame);
	uint32_t HeadlessGetScriptFrameCount();
	uint32_t HeadlessGetFrameCount();
	//ADR-0169 - the sprite layer is read, not rendered (Decision section 2): the
	//wrapper export holds the emulation thread at an end-of-frame boundary
	//(Emulator::Lock) and reads the OAM/palette buffers, the mapper-resolved
	//pattern tables and the $2000 sprite-control bits (NesPpuState) straight off
	//the NES console - no Debugger is attached, because a run under a live
	//debugger never parks on its target frame.
	//nametables (added 2026-09-08, ADR-0169 "capture every layer") is the
	//background's $2000-$2FFF tile+attribute bytes, mapper-resolved, read the
	//same instant as the sprite layer above.
	//The outHasChrLatch.. outChrFullSize params (same date, MMC2/MMC4 CHR-latch
	//extension) are populated only when the loaded mapper has a tile-index CHR
	//latch (BaseMapper::HasChrBankLatch) - see EmuApiWrapperHeadless.cpp.
	bool HeadlessCaptureNesSpriteLayer(uint8_t* oam, uint8_t* palette, uint8_t* chr, uint8_t* nametables, NesPpuState* ppuState,
		bool* outHasChrLatch, uint16_t* outChrLatchPageSize, uint8_t* outLeftFdBank, uint8_t* outLeftFeBank, uint8_t* outRightFdBank, uint8_t* outRightFeBank,
		uint8_t* outChrFull, uint32_t maxChrFullSize, uint32_t* outChrFullSize);
	//F9.15 - in-memory frame capture (same wrapper file)
	bool HeadlessCaptureFrame(uint32_t* outWidth, uint32_t* outHeight, uint32_t* outFrameNumber, uint32_t* outPixelCount);
	uint32_t HeadlessReadCapturedPixels(uint32_t* outPixels, uint32_t maxPixels);
	//ADR-0167 - HUD-only capture (same wrapper file); DisplayMessage already
	//existed for the GUI (InteropDLL/EmuApiWrapper.cpp) and HeadlessSetOsdEnabled
	//is the sibling seam added in EmuApiWrapperHeadless.cpp - declared here so a
	//headless run can gate the OSD queue and queue a deterministic toast before
	//capturing it.
	bool HeadlessCaptureHud(uint32_t width, uint32_t height, uint32_t* outWidth, uint32_t* outHeight, uint32_t* outPixelCount);
	uint32_t HeadlessReadCapturedHudPixels(uint32_t* outPixels, uint32_t maxPixels);
	void DisplayMessage(char* title, char* message, char* param1);
	void HeadlessSetOsdEnabled(bool osdEnabled);
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
	void Resume();
	bool IsPaused();
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

	//LiveSnapshot and the ComposePpm/ComposeSpritesJson/ComposeStatusJson/
	//AtomicWrite composers now live in Utilities/LiveRecordFormat.{h,cpp}
	//(shared with the interactive UI's LiveFrameRecorder, 2026-09-08 ADR-0169
	//update) - this scripted run only needs to fill one from a direct console
	//read taken with the run parked for an instant (Decision section 2).
	bool CaptureLiveSnapshot(LiveSnapshot& snapshot, bool readSpriteLayer)
	{
		uint32_t pixelCount = 0;
		if(!HeadlessCaptureFrame(&snapshot.Width, &snapshot.Height, &snapshot.CaptureFrame, &pixelCount)) {
			return false; //nothing decoded yet
		}
		snapshot.Pixels.assign(pixelCount, 0);
		if(HeadlessReadCapturedPixels(snapshot.Pixels.data(), pixelCount) != pixelCount) {
			return false;
		}
		if(readSpriteLayer) {
			//The wrapper export holds the emulation thread at an end-of-frame
			//boundary (Emulator::Lock) and reads the sprite layer as one
			//consistent state - the run's pause/stop machinery is untouched.
			NesPpuState ppu = {};
			snapshot.Chr.assign(0x2000, 0); //the $0000-$1FFF pattern tables
			snapshot.Nametables.assign(0x1000, 0); //the $2000-$2FFF background tile+attribute bytes
			//The CHR-latch extension needs an upper bound to size outChrFull -
			//no NES cartridge exceeds 1MB of CHR-ROM (the largest known mapper 9/10
			//titles ship 128KB), so this leaves ample headroom.
			static const uint32_t kMaxChrFull = 1024 * 1024;
			snapshot.ChrRomFull.assign(kMaxChrFull, 0);
			uint32_t chrFullSize = 0;
			if(!HeadlessCaptureNesSpriteLayer(snapshot.Oam, snapshot.Palette, snapshot.Chr.data(), snapshot.Nametables.data(), &ppu,
				&snapshot.HasChrLatch, &snapshot.ChrLatchPageSize, &snapshot.LeftChrFdBank, &snapshot.LeftChrFeBank, &snapshot.RightChrFdBank, &snapshot.RightChrFeBank,
				snapshot.ChrRomFull.data(), kMaxChrFull, &chrFullSize)) {
				return false; //not a NES console - no sprite layer to publish
			}
			snapshot.ChrRomFull.resize(chrFullSize);
			snapshot.SpritePatternAddr = ppu.Control.SpritePatternAddr;
			snapshot.LargeSprites = ppu.Control.LargeSprites;
			snapshot.SpritesEnabled = ppu.Mask.SpritesEnabled;
			//Mask.SpriteMask/BackgroundMask are a "show" flag, not a "clip" one
			//(NesPpu.cpp's own comment: "BackgroundMask = false: Hide background
			//in leftmost 8 pixels") - LeftColumnClip/BackgroundLeftColumnClip name
			//the wire field for what it actually gates (clipping), so the polarity
			//is inverted here rather than at every reader.
			snapshot.LeftColumnClip = !ppu.Mask.SpriteMask;
			snapshot.HasSprites = true;

			snapshot.BackgroundPatternAddr = ppu.Control.BackgroundPatternAddr;
			snapshot.BackgroundEnabled = ppu.Mask.BackgroundEnabled;
			snapshot.BackgroundLeftColumnClip = !ppu.Mask.BackgroundMask;
			//Loopy "v" (VideoRamAddr) has already scanned the whole frame at this
			//end-of-frame capture point, so the base scroll comes from loopy "t"
			//(TmpVideoRamAddr) - the scroll the game wrote for the frame to render.
			snapshot.TmpVideoRamAddr = ppu.TmpVideoRamAddr;
			snapshot.FineScrollX = ppu.ScrollX;
			snapshot.HasBackground = true;
		}
		return true;
	}
}

int main(int argc, char** argv)
{
	if(argc < 4) {
		fprintf(stderr, "usage: %s <rom> <seconds> <output-prefix> [pal] [hdpack] [romtiles]\n"
			"       [screenshot] [capture] [log] [bootstrap] [filter=<name>] [mep-off]\n"
			"       [mep-notextures] [mep-nosynth] [mep-forcepatch] [mep-disable=<pack>]\n"
			"       [state=<file.mss>] [input=<script>] [realtime] [hud-message=<title>|<msg>]\n"
			"       [live=<ms>]\n", argv[0]);
		return 1;
	}
	std::string rom = argv[1];
	double seconds = atof(argv[2]);
	std::string prefix = argv[3];
	bool pal = false;
	bool hdPack = false;
	bool romTiles = false;
	bool screenshot = false;
	bool capture = false;
	bool dumpLog = false;
	VideoFilterType videoFilter = VideoFilterType::None;
	EnhancementPackConfig mep = {};
	mep.BootstrapEnhancementFolder = false; //opt-in headless ("bootstrap" flag) - it writes beside the ROM
	std::string mepDisable;
	std::string stateFile;
	//input script: lines "<count>f <buttons>" or "<count>s <buttons>", buttons
	//in U D L R A B S(elect) T(start) or "-". A bare count is a parse error
	//(ADR-0157 section 1). Parsed core-side by HeadlessInputScript, which is
	//also what scripts/core_unit_tests.cpp covers.
	std::string inputScriptText;
	std::string inputScriptPath;
	bool realtime = false;
	//ADR-0169: live=<ms> publishing interval in wall-clock milliseconds (0=off);
	//the publish lambda below and the scratch folder <prefix>-live/ it writes.
	int liveMs = 0;
	std::string liveDir;
	bool liveReadSprites = false;
	double liveNextWall = 0.0;
	//ADR-0167: queued right before a "capture" run's settle sleep, so a test
	//can assert the HUD capture's blank flag flips. title|message, split on
	//the first '|' (neither Localize()'d key needs one).
	std::string hudMessageTitle;
	std::string hudMessageText;
	for(int i = 4; i < argc; i++) {
		if(strcmp(argv[i], "pal") == 0) {
			pal = true;
		} else if(strcmp(argv[i], "hdpack") == 0) {
			hdPack = true;
		} else if(strcmp(argv[i], "romtiles") == 0) {
			romTiles = true;
		} else if(strcmp(argv[i], "screenshot") == 0) {
			screenshot = true;
		} else if(strcmp(argv[i], "capture") == 0) {
			capture = true;
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
		} else if(strncmp(argv[i], "state=", 6) == 0) {
			stateFile = argv[i] + 6;
		} else if(strncmp(argv[i], "input=", 6) == 0) {
			inputScriptPath = argv[i] + 6;
			FILE* f = fopen(inputScriptPath.c_str(), "rb");
			if(!f) {
				fprintf(stderr, "cannot open input script: %s\n", inputScriptPath.c_str());
				return 1;
			}
			char buffer[4096];
			size_t read;
			while((read = fread(buffer, 1, sizeof(buffer), f)) > 0) {
				inputScriptText.append(buffer, read);
			}
			fclose(f);
		} else if(strcmp(argv[i], "realtime") == 0) {
			realtime = true;
		} else if(strncmp(argv[i], "mep-disable=", 12) == 0) {
			mepDisable = argv[i] + 12;
		} else if(strncmp(argv[i], "hud-message=", 12) == 0) {
			std::string spec = argv[i] + 12;
			size_t sep = spec.find('|');
			if(sep == std::string::npos) {
				fprintf(stderr, "hud-message= needs a '|' between title and message: %s\n", spec.c_str());
				return 1;
			}
			hudMessageTitle = spec.substr(0, sep);
			hudMessageText = spec.substr(sep + 1);
		} else if(strncmp(argv[i], "live=", 5) == 0) {
			//ADR-0169: publish cadence in wall-clock milliseconds. Below ~50ms the
			//capture+publish itself costs more than the interval - just spin disk.
			liveMs = atoi(argv[i] + 5);
			if(liveMs < 50) {
				fprintf(stderr, "live= needs a wall-clock interval of at least 50 ms: %s\n", argv[i]);
				return 1;
			}
		}
	}

	std::filesystem::path outDir = std::filesystem::absolute(prefix).parent_path();
	std::filesystem::path home = outDir / "mesen-home";
	std::filesystem::create_directories(home);

	if(liveMs > 0) {
		//ADR-0169: the live folder is scratch, created up front so a failure to
		//write it disables the feature before the run starts, never mid-run.
		liveDir = std::filesystem::absolute(prefix + "-live").string();
		std::error_code liveError;
		std::filesystem::create_directories(liveDir, liveError);
		if(liveError) {
			fprintf(stderr, "live: cannot create %s (%s) - live view disabled, recording continues\n", liveDir.c_str(), liveError.message().c_str());
			liveDir.clear();
			liveMs = 0;
		}
	}

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
	//The core defaults every port to ControllerType::None, so with no input
	//backend no control device is created at all - and the debugger's input
	//overrides (SetInputOverrides, used by "input=<script>") are dropped on the
	//floor because NesDebugger/SmsDebugger only write into a device that exists.
	sms.Port1.Type = ControllerType::SmsController;
	//Power-on RAM defaults to RamState::Random, which is a second source of
	//run-to-run variation on top of the one F9.14 removed: a game that reads
	//uninitialised RAM takes a different path, and the recording differs even
	//when both runs cover the same frames. The core's own deterministic replay
	//harness zeroes it for the same reason (RecordedRomTest::Run).
	sms.RamPowerOnState = RamState::AllZeros;
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
	//See the SmsConfig note above: without a standard controller in port 1 an
	//input script has nothing to drive.
	nes.Port1.Type = ControllerType::NesController;
	nes.RamPowerOnState = RamState::AllZeros; //see the SmsConfig note above
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
	gameboy.RamPowerOnState = RamState::AllZeros; //see the SmsConfig note above
	SetGameboyConfig(gameboy);

	//The screenshot pipeline (BaseVideoFilter::TakeScreenshot) runs the
	//configured scale filter before writing the PNG, so the video config has
	//to be pushed before the frame is captured. Every other field keeps the
	//struct's own default (neutral pipeline: no scanlines, no rotation).
	VideoConfig video = {};
	video.VideoFilter = videoFilter;
	SetVideoConfig(video);

	//F9.14: the frame limiter only decides how long a run takes on the wall
	//clock, which is now nothing the output depends on. Off by default so a
	//300 s recording does not cost 300 s; "realtime" puts it back for anyone
	//who wants to watch one go by.
	EmulationConfig emulation = {};
	if(!realtime) {
		emulation.EmulationSpeed = 0;
	}
	SetEmulationConfig(emulation);

	SetEnhancementPackConfig(mep);
	if(!mepDisable.empty()) {
		SetMepPackEnabled(mepDisable.c_str(), false);
	}

	//The script's own unit is the frame; 's' steps and the <seconds> argument
	//are resolved at the region's nominal rate (ADR-0157 section 1). This is
	//the region the flags force, not the console's exact fps - the console is
	//not loaded yet, and the provider has to be registered before it is (the
	//control manager that holds it is created by the game load itself).
	const double frameRate = pal ? 50.0070 : 60.0988;
	uint32_t totalFrames = (uint32_t)std::max(1.0, std::round(seconds * frameRate));

	if(!inputScriptPath.empty()) {
		char scriptError[1024] = {};
		if(!HeadlessLoadInputScript(inputScriptText.c_str(), frameRate, scriptError, (uint32_t)sizeof(scriptError))) {
			fprintf(stderr, "%s: %s\n", inputScriptPath.c_str(), scriptError);
			return 1;
		}
		printf("input script: %s (%u frames)\n", inputScriptPath.c_str(), HeadlessGetScriptFrameCount());
	}

	//Freeze the run on its first frame, so what the recorders are started on
	//is a fixed frame rather than "whatever the emulation thread reached while
	//this thread was calling into the DLL".
	HeadlessSetPauseFrame(1);

	//ADR-0167: with the OSD on (the default), LoadRom enqueues a "game loaded"
	//toast (Emulator.cpp) that never ages out of a short parked run, so a HUD
	//capture could never read blank. Gate it off for the load and the run;
	//HeadlessSetOsdEnabled(true) is turned on for the one instant a capture run
	//queues its own test toast (see the capture block below).
	HeadlessSetOsdEnabled(false);

	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "failed to load ROM: %s\n", rom.c_str());
		return 1;
	}

	//The watchdog exists so a *hung* emulator cannot hang CI forever, and it
	//measures exactly that: wall clock since the frame counter last moved.
	//Issue #165: it used to be a budget for the whole run, 120 s + 3x the
	//recording's <seconds>. That relationship died with ADR-0157/F9.14 - the
	//frame limiter is off, so a run's length in emulated frames says nothing
	//about how long it takes on the host, and four parallel jobs on a loaded
	//machine make it say even less. Eight of thirty runs then tripped it at
	//1020 s (= 120 + 3x300) while the emulator was plainly still advancing -
	//Zelda at frame 7482 of 18030, Double Dragon at 15710 - and the message
	//said "the emulator is not advancing", which was simply false. Each one
	//wrote a *truncated* pack that the batch went on to install.
	const double stallTimeout = 90.0;
	auto t0 = std::chrono::steady_clock::now();
	auto elapsed = [&t0]() { return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count(); };
	auto waitForPause = [&](const char* what, std::function<void()> onTick = std::function<void()>()) {
		uint32_t lastFrame = HeadlessGetFrameCount();
		double lastProgress = elapsed();
		while(!IsPaused()) {
			if(!IsRunning()) {
				fprintf(stderr, "emulation stopped unexpectedly while %s\n", what);
				return false;
			}
			uint32_t frame = HeadlessGetFrameCount();
			if(frame != lastFrame) {
				lastFrame = frame;
				lastProgress = elapsed();
			} else if(elapsed() - lastProgress > stallTimeout) {
				fprintf(stderr, "STALLED: no frame in %.1fs of wall clock while %s (stuck on frame %u, %.1fs into the run)\n", elapsed() - lastProgress, what, frame, elapsed());
				return false;
			}
			if(onTick) {
				onTick();
			}
			std::this_thread::sleep_for(std::chrono::milliseconds(2));
		}
		return true;
	};

	if(!waitForPause("waiting for the first frame")) {
		return 1;
	}

	if(!stateFile.empty()) {
		LoadStateFile((char*)stateFile.c_str());
		printf("state loaded: %s\n", stateFile.c_str());
	}
	TimingInfoAbi timing = GetTimingInfo(CpuTypeFromExtension(rom));
	printf("ROM loaded: %s%s\n", rom.c_str(), pal ? " [region forced: PAL]" : "");
	printf("emulated fps: %.3f (master clock %u Hz)\n", timing.Fps, timing.MasterClockRate);

	std::string mid = prefix + ".mid", vgm = prefix + ".vgm";
	std::string packFolder = std::filesystem::absolute(prefix + "-hdpack").string();
	if(romTiles) {
		HdPackBuilderOptions options = {};
		options.SaveFolder = (char*)packFolder.c_str();
		options.FilterType = ScaleFilterType::Prescale;
		options.Scale = 1;
		options.ChrRamBankSize = 0x1000;
		ExecuteShortcut({ EmulatorShortcut::ExportRomTilesHdPack, 0, &options });
		printf("static tile export: hdpack=%s\n", packFolder.c_str());
		//The export is synchronous and needs no gameplay - stop on the frame
		//the run is already paused on.
		totalFrames = 1;
	} else if(hdPack) {
		HdPackBuilderOptions options = {};
		options.SaveFolder = (char*)packFolder.c_str();
		options.FilterType = ScaleFilterType::Prescale;
		options.Scale = 1;
		options.ChrRamBankSize = 0x1000; //NES-only field
		ExecuteShortcut({ EmulatorShortcut::StartRecordHdPack, 0, &options });
		printf("recording: hdpack=%s\n", packFolder.c_str());
	} else if(screenshot || capture) {
		printf("running %u frames for a final %s\n", totalFrames, screenshot ? "screenshot" : "capture");
	} else {
		MidiRecord((char*)mid.c_str());
		VgmRecord((char*)vgm.c_str());
		printf("recording: midi=%d vgm=%d\n", MidiIsRecording(), VgmIsRecording());
	}

	//ADR-0169 live publish. The sprite layer is read, not rendered (Decision
	//section 2): OAM, palette and the mapper-resolved pattern tables come off
	//the console, and the $2000 control bits (sprite pattern table, 8x16) out
	//of the PPU state snapshot - the viewer rebuilds sprite pixels from them.
	//CaptureLiveSnapshot holds the emulation thread at an end-of-frame boundary
	//(Emulator::Lock) for the instant the bytes are read - no Debugger is
	//attached, so the run still parks on its target frame; the cost of that hold
	//is the "must be measured" of the ADR's Consequences, measured against the
	//plain run below.
	auto publishLive = [&]() {
		if(liveMs <= 0 || liveDir.empty()) {
			return;
		}
		double now = elapsed();
		if(now < liveNextWall) {
			return;
		}
		liveNextWall = now + (double)liveMs / 1000.0;

		LiveSnapshot snapshot;
		if(!CaptureLiveSnapshot(snapshot, liveReadSprites)) {
			return; //no decoded frame yet - try on the next tick
		}
		uint32_t cpuFrame = HeadlessGetFrameCount();
		bool ok = LiveRecordFormat::AtomicWrite(liveDir + "/frame.ppm", LiveRecordFormat::ComposePpm(snapshot));
		if(liveReadSprites) {
			ok = LiveRecordFormat::AtomicWrite(liveDir + "/sprites.json", LiveRecordFormat::ComposeSpritesJson(snapshot, cpuFrame)) && ok;
			ok = LiveRecordFormat::AtomicWrite(liveDir + "/chr.bin", snapshot.Chr.data(), snapshot.Chr.size()) && ok;
			ok = LiveRecordFormat::AtomicWrite(liveDir + "/nametables.bin", snapshot.Nametables.data(), snapshot.Nametables.size()) && ok;
			ok = LiveRecordFormat::AtomicWrite(liveDir + "/background.json", LiveRecordFormat::ComposeBackgroundJson(snapshot)) && ok;
			if(snapshot.HasChrLatch) {
				ok = LiveRecordFormat::AtomicWrite(liveDir + "/chrfull.bin", snapshot.ChrRomFull.data(), snapshot.ChrRomFull.size()) && ok;
				ok = LiveRecordFormat::AtomicWrite(liveDir + "/chrlatch.json", LiveRecordFormat::ComposeChrLatchJson(snapshot)) && ok;
			}
		}
		ok = LiveRecordFormat::AtomicWrite(liveDir + "/status.json", LiveRecordFormat::ComposeStatusJson(false, cpuFrame, totalFrames, elapsed())) && ok;
		if(!ok) {
			fprintf(stderr, "live: cannot write %s - live view disabled, recording continues\n", liveDir.c_str());
			liveDir.clear();
		}
	};
	if(liveMs > 0) {
		//NES runs read the sprite layer too; GB/SMS/GG runs publish frames only.
		liveReadSprites = CpuTypeFromExtension(rom) == kCpuTypeNes;
		if(liveReadSprites) {
			//palette.json: the exact RGB this run renders with, so the viewer
			//colors reconstructed sprites like the composed frame. Written once,
			//and the viewer treats it as immutable for the run. The sprite bytes
			//themselves come from a direct console read at publish time
			//(HeadlessCaptureNesSpriteLayer), so no debugger is attached here
			//and the run keeps parking on its target frame.
			std::string colors = "{\n  \"colors\": [";
			char hex[16];
			for(int i = 0; i < 64; i++) {
				if(i) colors += ",";
				snprintf(hex, sizeof(hex), "\"#%06X\"", kDefaultNesPalette[i] & 0xFFFFFF);
				colors += hex;
			}
			colors += "]\n}\n";
			LiveRecordFormat::AtomicWrite(liveDir + "/palette.json", colors);
		}
		liveNextWall = 0.0; //publish on the first tick of the recording wait
	}

	//The run itself: resume, and let the provider stop it from inside the
	//frame it was told to stop on. Nothing here decides how many frames run.
	HeadlessSetPauseFrame(totalFrames);
	Resume();
	bool reachedTarget = waitForPause("recording", publishLive);

	//ADR-0169: one final status so the viewer can show "done" rather than stale
	//- the run stops being published the moment it parks on its target frame.
	if(liveMs > 0 && !liveDir.empty()) {
		LiveRecordFormat::AtomicWrite(liveDir + "/status.json", LiveRecordFormat::ComposeStatusJson(true, HeadlessGetFrameCount(), totalFrames, elapsed()));
	}

	//The hud-message toast is emitted inside the capture block below, not here:
	//with the OSD gated off across the load/run, a DisplayMessage before the
	//OSD is re-enabled for the capture would go to the log instead of the queue.

	if(screenshot || capture) {
		//The video decoder runs on its own thread; give it a moment to drain
		//so what we read is the paused frame and not the one before it. This
		//is a display-pipeline settle, not part of the run length.
		std::this_thread::sleep_for(std::chrono::milliseconds(200));
	}

	if(screenshot) {
		TakeScreenshot();
		printf("screenshot saved in %s\n", (home / "Screenshots").string().c_str());
	}

	bool captureFailed = false;
	if(capture) {
		//F9.15: the frame never reaches the disk. Two calls, because the size
		//of the capture is only known after it is taken and the pixels must
		//come from *that* capture, not from a second one taken later.
		uint32_t width = 0, height = 0, frameNumber = 0, pixelCount = 0;
		if(!HeadlessCaptureFrame(&width, &height, &frameNumber, &pixelCount)) {
			fprintf(stderr, "capture failed: the emulator has no decoded frame\n");
			captureFailed = true;
		} else {
			std::vector<uint32_t> pixels(pixelCount);
			uint32_t copied = HeadlessReadCapturedPixels(pixels.data(), pixelCount);
			if(copied != pixelCount) {
				fprintf(stderr, "capture failed: read %u of %u pixels\n", copied, pixelCount);
				captureFailed = true;
			} else {
				FrameBorders borders = FrameCaptureMath::MeasureBorders(pixels.data(), width, height);
				printf("capture: %ux%u frame=%u pixels=%u checksum=0x%08X\n",
					width, height, frameNumber, pixelCount, FrameCaptureMath::Checksum(pixels.data(), pixelCount));
				printf("capture borders: left=%u right=%u top=%u bottom=%u colour=0x%08X blank=%d\n",
					borders.Left, borders.Right, borders.Top, borders.Bottom, borders.Colour, borders.IsBlank ? 1 : 0);

				//ADR-0167: same canvas size as the frame capture above (the
				//base frame size when no video filter is active). Additive -
				//the two lines above are unchanged, so an existing consumer's
				//parsing does not break.
				//
				//Two details keep the blank flag meaningful:
				//1. The queue holds exactly the messages a test queues. The OSD
				//   has been off since before LoadRom, so no "game loaded" toast
				//   is resident; a hud-message= run re-enables it for just the
				//   DisplayMessage below and disables it again, so the queue
				//   gains exactly that one toast and nothing the resumed run may
				//   throw at the OSD in the meantime.
				//2. The capture is taken *while the emulator is running*, not on
				//   the paused frame the captures above used. SystemHud::Draw
				//   paints the pause icon on every paused frame - its one
				//   always-on element - so a paused HUD capture could never read
				//   blank=1, and blank=0 would not mean a message was queued.
				//   Resuming here (the run's pause latch was consumed when it
				//   stopped at its target frame, so the emulator runs until
				//   re-armed below) drops that icon from the draw.
				//Together they restore the ADR's meaning for blank: uniform
				//transparent = no message, anything else = one is queued.
				bool queuedToast = !hudMessageTitle.empty();
				if(queuedToast) {
					HeadlessSetOsdEnabled(true);
					DisplayMessage((char*)hudMessageTitle.c_str(), (char*)hudMessageText.c_str(), (char*)"");
					HeadlessSetOsdEnabled(false);
				}
				Resume();
				if(queuedToast) {
					//The run's pause latch was consumed, so the emulator is now
					//running frames. Give the decode pipeline a moment to run its
					//first UpdateFrame(s) after the resume before capturing: a HUD
					//capture taken in the first instants after Resume() would
					//occasionally miss the just-queued toast (observed ~1/3 of
					//runs with no settle, 0/N with this one) - the same class of
					//decode-thread transient the 200ms settle above drains before
					//the frame capture. 100ms is comfortably inside the toast's
					//3000ms lifetime.
					std::this_thread::sleep_for(std::chrono::milliseconds(100));
				}
				uint32_t hudWidth = 0, hudHeight = 0, hudPixelCount = 0;
				if(!HeadlessCaptureHud(width, height, &hudWidth, &hudHeight, &hudPixelCount)) {
					fprintf(stderr, "hud capture failed: degenerate size %ux%u\n", width, height);
					captureFailed = true;
				} else {
					std::vector<uint32_t> hudPixels(hudPixelCount);
					uint32_t hudCopied = HeadlessReadCapturedHudPixels(hudPixels.data(), hudPixelCount);
					if(hudCopied != hudPixelCount) {
						fprintf(stderr, "hud capture failed: read %u of %u pixels\n", hudCopied, hudPixelCount);
						captureFailed = true;
					} else {
						FrameBorders hudBorders = FrameCaptureMath::MeasureBorders(hudPixels.data(), hudWidth, hudHeight);
						printf("capture hud: %ux%u checksum=0x%08X blank=%d\n",
							hudWidth, hudHeight, FrameCaptureMath::Checksum(hudPixels.data(), hudPixelCount), hudBorders.IsBlank ? 1 : 0);
					}
				}
				//Re-arm the pause latch at the frame the run has reached so the
				//emulator parks again (within a frame of this call) instead of
				//free-running into the tail's Stop(). Nothing after this reads
				//the frame count as a contract, but the run should end parked.
				HeadlessSetPauseFrame(HeadlessGetFrameCount());
			}
		}
	}

	if(hdPack) {
		ExecuteShortcut({ EmulatorShortcut::StopRecordHdPack, 0, nullptr });
	} else if(!screenshot && !capture) {
		MidiStop();
		VgmStop();
	}
	printf("capture finished: %u frames (target %u), %.1fs of wall clock%s\n", HeadlessGetFrameCount(), totalFrames, elapsed(), reachedTarget ? "" : " - INCOMPLETE");
	if(dumpLog) {
		std::string log(65536, '\0');
		GetLog(log.data(), (uint32_t)log.size());
		log.resize(strlen(log.c_str()));
		printf("--- core log ---\n%s--- end log ---\n", log.c_str());
	}
	Stop();
	Release();
	//A run that did not reach its frame target is a failed capture, not a
	//short one - the caller (bootstrap_auto_packs.sh) must see it.
	return reachedTarget && !captureFailed ? 0 : 1;
}
