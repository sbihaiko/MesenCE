//Headless music-capture harness (F1 regression tool).
//Links directly against the freshly-built core dylib and includes the real
//SettingTypes.h, so config structs are passed with the exact ABI layout the
//core was compiled with - any drift fails at compile time instead of
//corrupting memory at run time.
//
//Build:   make capture-tool
//Usage:   scripts/headless_record <rom> <seconds> <output_prefix> [pal]
//
//Writes <output_prefix>.mid and <output_prefix>.vgm from the ROM's first N
//seconds of audio (power-on attract/title music - no input is ever fed).
//A scratch home folder is created next to the output; the NES game database
//is copied into it automatically when the tool runs from the repo root.
#include "Core/Shared/SettingTypes.h"
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

extern "C" {
	TimingInfoAbi GetTimingInfo(uint8_t cpuType);
	void InitDll();
	void InitializeEmu(const char* homeFolder, void* windowHandle, void* viewerHandle, bool softwareRenderer, bool noAudio, bool noVideo, bool noInput);
	bool LoadRom(char* filename, char* patchFile);
	void SetSmsConfig(SmsConfig config);
	void SetCvConfig(CvConfig config);
	void SetNesConfig(NesConfig config);
	NesConfig GetNesConfig();
	void MidiRecord(char* filename);
	void MidiStop();
	bool MidiIsRecording();
	void VgmRecord(char* filename);
	void VgmStop();
	bool VgmIsRecording();
	bool IsRunning();
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
		for(char& c : ext) c = (char)tolower(c);
		if(ext == ".nes") return kCpuTypeNes;
		if(ext == ".gb" || ext == ".gbc") return kCpuTypeGameboy;
		return kCpuTypeSms; //.sms/.gg/.sg/.col
	}
}

int main(int argc, char** argv)
{
	if(argc < 4) {
		fprintf(stderr, "uso: %s <rom> <segundos> <prefixo-saida> [pal]\n", argv[0]);
		return 1;
	}
	std::string rom = argv[1];
	double seconds = atof(argv[2]);
	std::string prefix = argv[3];
	bool pal = argc > 4 && strcmp(argv[4], "pal") == 0;

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
	for(int i = 0; i < 4; i++) sms.ChannelVolumes[i] = 100;
	if(pal) { sms.Region = ConsoleRegion::Pal; }
	SetSmsConfig(sms);

	CvConfig cv = {};
	for(int i = 0; i < 4; i++) cv.ChannelVolumes[i] = 100;
	SetCvConfig(cv);

	NesConfig nes = GetNesConfig();
	for(int i = 0; i < 11; i++) nes.ChannelVolumes[i] = 100;
	if(pal) { nes.Region = ConsoleRegion::Pal; }
	SetNesConfig(nes);

	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "FALHA ao carregar ROM: %s\n", rom.c_str());
		return 1;
	}
	TimingInfoAbi timing = GetTimingInfo(CpuTypeFromExtension(rom));
	printf("ROM carregada: %s%s\n", rom.c_str(), pal ? " [regiao forcada: PAL]" : "");
	printf("fps emulado: %.3f (clock mestre %u Hz)\n", timing.Fps, timing.MasterClockRate);

	std::string mid = prefix + ".mid", vgm = prefix + ".vgm";
	MidiRecord((char*)mid.c_str());
	VgmRecord((char*)vgm.c_str());
	printf("gravando: midi=%d vgm=%d\n", MidiIsRecording(), VgmIsRecording());

	auto t0 = std::chrono::steady_clock::now();
	while(std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count() < seconds) {
		std::this_thread::sleep_for(std::chrono::milliseconds(250));
		if(!IsRunning()) { fprintf(stderr, "emulacao parou inesperadamente\n"); break; }
	}

	MidiStop();
	VgmStop();
	printf("captura encerrada (%.1fs)\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
	Stop();
	Release();
	return 0;
}
