//Spike (F5.4f research): can the NES sound driver of a game be found and driven
//automatically, NSF-style, to enumerate every music track / SFX without playing?
//
//  A) write breakpoints on the APU registers + callstacks -> the driver's per-frame
//     "tick" routine P and the code region it lives in
//  B) execute breakpoints on the CDL function entries of that region while a
//     scripted Start press changes the music -> candidate "play song" routine S
//     (called from outside the driver, with the song id in a register)
//  C) for id = 0..N: reload the title save state, hijack the CPU into S with A=id,
//     return into a JMP-self stub in RAM (NMIs keep ticking the driver), sample the
//     APU for a few seconds -> kind (bgm/sfx/silent), length, note fingerprint
//
//Build: `make spike-sound-driver` (or, from repo root after `make core`):
//  c++ -std=c++17 -O2 -I . -I Core -Wl,-headerpad_max_install_names scripts/spike_sound_driver.cpp InteropDLL/obj.osx-arm64/MesenCore.dylib -o scripts/spike_sound_driver
//  install_name_tool -change MesenCore.dylib $PWD/InteropDLL/obj.osx-arm64/MesenCore.dylib scripts/spike_sound_driver
//Usage: scripts/spike_sound_driver <rom.nes> <workdir> [maxIds=40] [secondsPerId=4] [startAt=3.0]
//  startAt = seconds of emulated time (frames/60) before the title save state is taken
//  SPIKE_BOOTSTRAP=1  run on a private copy of the ROM with the MEP bootstrap on: the F5.3
//                     recorder writes <workdir>/rom/<Game>/auto/audio/ for every enumerated track
//  SPIKE_NODEBUG=1 / SPIKE_NOPOWER=1  diagnostics (skip the debugger / the power cycle)
#include "Core/Shared/SettingTypes.h"
#include "Core/Shared/CpuType.h"
#include "Core/Shared/MemoryType.h"
#include "Core/Debugger/DebugTypes.h"
#include "Core/Debugger/ITraceLogger.h"
#include "Core/NES/NesTypes.h"
#include "Core/Shared/Interfaces/INotificationListener.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <map>
#include <set>
#include <string>
#include <thread>
#include <vector>

struct ExecuteShortcutParamsAbi
{
	EmulatorShortcut Shortcut;
	uint32_t Param;
	void* ParamPtr;
};

//Same layout as Core/Debugger/Breakpoint.h (private fields, passed by value)
struct BreakpointAbi
{
	uint32_t Id;
	CpuType Cpu;
	MemoryType Memory;
	BreakpointTypeFlags Type;
	int32_t StartAddr;
	int32_t EndAddr;
	bool Enabled;
	bool MarkEvent;
	bool IgnoreDummyOperations;
	char Condition[1000];
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
	void SaveStateFile(char* filepath);
	void LoadStateFile(char* filepath);
	NesConfig GetNesConfig();
	void SetNesConfig(NesConfig config);

	typedef void (*NotificationCb)(int, void*);
	void* RegisterNotificationCallback(NotificationCb callback);
	void SetTraceOptions(CpuType type, TraceLoggerOptions options);
	void SetEnhancementPackConfig(EnhancementPackConfig config);
	void StartLogTraceToFile(const char* filename);
	void StopLogTraceToFile();
	void InitializeDebugger();
	void ReleaseDebugger();
	bool IsExecutionStopped();
	void ResumeExecution();
	void Step(CpuType cpuType, uint32_t count, StepType type);
	void SetBreakpoints(BreakpointAbi breakpoints[], uint32_t length);
	void SetInputOverrides(uint32_t index, DebugControllerState state);
	void GetCallstack(CpuType cpuType, StackFrameInfo* callstackArray, uint32_t& callstackSize);
	void GetConsoleState(BaseState& state, ConsoleType consoleType);
	void GetCpuState(BaseState& state, CpuType cpuType);
	void SetCpuState(BaseState& state, CpuType cpuType);
	uint32_t GetProgramCounter(CpuType cpuType, bool getInstPc);
	uint8_t GetMemoryValue(MemoryType type, uint32_t address);
	void SetMemoryValue(MemoryType type, uint32_t address, uint8_t value);
	uint32_t GetCdlFunctions(MemoryType memoryType, uint32_t functions[], uint32_t maxSize);
	AddressInfo GetRelativeAddress(AddressInfo absAddress, CpuType cpuType);
	AddressInfo GetAbsoluteAddress(AddressInfo relAddress);
}

namespace
{
	using Clock = std::chrono::steady_clock;

	void SleepMs(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

	double Seconds(Clock::time_point t0) { return std::chrono::duration<double>(Clock::now() - t0).count(); }

	BreakpointAbi MakeBp(BreakpointTypeFlags type, int32_t start, int32_t end, uint32_t id)
	{
		BreakpointAbi bp = {};
		bp.Id = id;
		bp.Cpu = CpuType::Nes;
		bp.Memory = MemoryType::NesMemory;
		bp.Type = type;
		bp.StartAddr = start;
		bp.EndAddr = end;
		bp.Enabled = true;
		bp.MarkEvent = false;
		bp.IgnoreDummyOperations = true;
		bp.Condition[0] = 0;
		return bp;
	}

	std::atomic<uint32_t> g_breaks{0};
	uint32_t g_seen = 0;
	BreakEvent g_lastBreak = {};

	void OnNotification(int type, void* param)
	{
		if(type == (int)ConsoleNotificationType::CodeBreak) {
			if(param) g_lastBreak = *(BreakEvent*)param;
			g_breaks++;
		}
	}

	//Wait until the debugger reports a real code break (CodeBreak notification) or timeout.
	//IsExecutionStopped() is NOT usable for this: it is also true while the emu thread is
	//paused by our own API calls (WaitForLock), so it reports phantom stops.
	bool WaitForBreak(double timeoutSec)
	{
		Clock::time_point t0 = Clock::now();
		while(g_breaks.load() == g_seen) {
			if(Seconds(t0) > timeoutSec) {
				return false;
			}
			SleepMs(1);
		}
		g_seen = g_breaks.load();
		//the emu thread sets _executionStopped right before sending the notification; make sure it is parked
		while(!IsExecutionStopped()) SleepMs(1);
		return true;
	}

	//Per-frame note snapshot (same audibility rules as NesAudioFingerprint::FromApu)
	struct Note { int8_t Sq1 = -1, Sq2 = -1, Tri = -1; bool Noise = false; bool Silent() const { return Sq1 < 0 && Sq2 < 0 && Tri < 0 && !Noise; } };

	int8_t FreqToNote(double f)
	{
		if(f <= 0) {
			return -1;
		}
		int n = (int)std::lround(69.0 + 12.0 * std::log2(f / 440.0));
		return (n < 0 || n > 127) ? -1 : (int8_t)n;
	}

	double EnvVolume(const ApuEnvelopeState& env) { return (env.ConstantVolume ? env.Volume : env.Counter) / 15.0; }

	Note Snapshot()
	{
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		ApuState& a = st.Apu;
		Note n;
		if(a.Square1.Enabled && a.Square1.LengthCounter.Counter > 0 && a.Square1.Period >= 8 && EnvVolume(a.Square1.Envelope) > 0.001) {
			n.Sq1 = FreqToNote(a.Square1.Frequency);
		}
		if(a.Square2.Enabled && a.Square2.LengthCounter.Counter > 0 && a.Square2.Period >= 8 && EnvVolume(a.Square2.Envelope) > 0.001) {
			n.Sq2 = FreqToNote(a.Square2.Frequency);
		}
		if(a.Triangle.Enabled && a.Triangle.LengthCounter.Counter > 0 && a.Triangle.LinearCounter > 0 && a.Triangle.Period >= 2) {
			n.Tri = FreqToNote(a.Triangle.Frequency);
		}
		if(a.Noise.Enabled && a.Noise.LengthCounter.Counter > 0 && EnvVolume(a.Noise.Envelope) > 0.001) {
			n.Noise = true;
		}
		return n;
	}

	struct Sample
	{
		uint32_t Frames = 0;
		uint32_t Audible = 0;
		uint32_t LastAudible = 0;
		std::vector<int16_t> Onsets; //(voice<<8 | note) at note changes, first 48
		uint32_t Hash() const
		{
			uint32_t h = 2166136261u;
			for(int16_t o : Onsets) {
				h = (h ^ (uint16_t)o) * 16777619u;
			}
			return h;
		}
	};

	Sample SampleApu(double seconds)
	{
		Sample s;
		Note prev;
		Clock::time_point t0 = Clock::now();
		while(Seconds(t0) < seconds) {
			Note n = Snapshot();
			s.Frames++;
			if(!n.Silent()) {
				s.Audible++;
				s.LastAudible = s.Frames;
			}
			if(s.Onsets.size() < 48) {
				if(n.Sq1 >= 0 && n.Sq1 != prev.Sq1) s.Onsets.push_back((int16_t)(0x000 | n.Sq1));
				if(n.Sq2 >= 0 && n.Sq2 != prev.Sq2) s.Onsets.push_back((int16_t)(0x100 | n.Sq2));
				if(n.Tri >= 0 && n.Tri != prev.Tri) s.Onsets.push_back((int16_t)(0x200 | n.Tri));
			}
			prev = n;
			SleepMs(16);
		}
		return s;
	}

	void PressStart(int frames)
	{
		DebugControllerState st = {};
		st.Start = true;
		SetInputOverrides(0, st);
		SleepMs(frames * 17);
		DebugControllerState none = {};
		SetInputOverrides(0, none);
	}

	//Title screens often ignore input during timed waits and detect presses by edge:
	//pulse Start (3 frames down, 3 up) for the whole window
	void PulseStart(double seconds)
	{
		Clock::time_point t0 = Clock::now();
		while(Seconds(t0) < seconds) {
			PressStart(3);
			SleepMs(3 * 17);
		}
	}
}

int main(int argc, char** argv)
{
	if(argc < 3) {
		fprintf(stderr, "uso: %s <rom.nes> <workdir> [maxIds=40] [secondsPerId=4] [startAt=3.0]\n", argv[0]);
		return 1;
	}
	std::string rom = argv[1];
	std::filesystem::path work = argv[2];
	int maxIds = argc > 3 ? atoi(argv[3]) : 40;
	double secondsPerId = argc > 4 ? atof(argv[4]) : 4.0;
	double startAt = argc > 5 ? atof(argv[5]) : 3.0;
	std::filesystem::create_directories(work);
	std::filesystem::path home = work / "mesen-home";
	std::filesystem::create_directories(home);

	//SPIKE_BOOTSTRAP=1: run the MEP audio/texture bootstrap on a private copy of the ROM so the
	//F5.3 recorder captures every track we enumerate (fingerprints.json + midi/). Off by default:
	//BootstrapEnhancementFolder defaults to true and would write beside the user's ROM.
	bool bootstrap = getenv("SPIKE_BOOTSTRAP") != nullptr;
	if(bootstrap) {
		std::filesystem::path copy = work / "rom" / std::filesystem::path(rom).filename();
		std::filesystem::create_directories(copy.parent_path());
		std::filesystem::copy_file(rom, copy, std::filesystem::copy_options::overwrite_existing);
		rom = copy.string();
	}
	InitDll();
	InitializeEmu(home.string().c_str(), nullptr, nullptr, true, true, true, true);
	{
		EnhancementPackConfig mep = {};
		mep.EnableMepPacks = bootstrap;
		mep.EnableTextures = false;
		mep.EnableSynth = false;
		mep.BootstrapEnhancementFolder = bootstrap;
		SetEnhancementPackConfig(mep);
	}
	//Same as scripts/headless_record.cpp: the GUI normally pushes every config at startup
	{
		NesConfig nes = GetNesConfig();
		for(int i = 0; i < 11; i++) nes.ChannelVolumes[i] = 100;
		nes.Port1.Type = ControllerType::NesController; //debugger input overrides need a controller to write into
		SetNesConfig(nes);
	}
	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "FALHA ao carregar ROM\n");
		return 2;
	}
	RegisterNotificationCallback(OnNotification);
	if(!getenv("SPIKE_NODEBUG")) InitializeDebugger();
	if(!getenv("SPIKE_NOPOWER")) {
		ExecuteShortcut({ EmulatorShortcut::PowerCycle, 0, nullptr });
		SleepMs(300);
	}
	std::string titleState = (work / "title.mss").string();
	//wait by emulated frames (breaks slow the emulation down; wall-clock is meaningless here)
	uint32_t startFrame = (uint32_t)(startAt * 60);
	for(;;) {
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		if(st.Ppu.FrameCount >= startFrame) break;
		SleepMs(20);
	}
	{
		Sample probe = SampleApu(1.0);
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		printf("   frame %u: %u/%u frames audíveis no título (hash %08X)\n", st.Ppu.FrameCount, probe.Audible, probe.Frames, probe.Hash());
	}
	SaveStateFile((char*)titleState.c_str());
	SleepMs(100);
	if(getenv("SPIKE_NODEBUG")) { Stop(); return 0; }

	//---------------------------------------------------------------- A) driver tick
	printf("== A) quem escreve nos registradores do APU?\n");
	{
		BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Write, 0x4000, 0x4017, 1);
		SetBreakpoints(&bp, 1);
	}
	std::map<uint32_t, uint32_t> writerPcs;         //PC -> hits
	std::map<uint32_t, uint32_t> outerFrameVotes;   //callstack target -> votes (all frames)
	std::vector<std::vector<uint32_t>> stacks;
	Clock::time_point tA = Clock::now();
	int hits = 0;
	while(hits < 600 && Seconds(tA) < 8.0) {
		if(!WaitForBreak(2.0)) {
			break;
		}
		uint32_t pc = GetProgramCounter(CpuType::Nes, true);
		writerPcs[pc]++;
		StackFrameInfo frames[64];
		uint32_t count = 0;
		GetCallstack(CpuType::Nes, frames, count);
		std::vector<uint32_t> targets;
		for(uint32_t i = 0; i < count && i < 64; i++) {
			targets.push_back(frames[i].Target);
			outerFrameVotes[frames[i].Target]++;
		}
		stacks.push_back(targets);
		hits++;
		ResumeExecution();
	}
	if(hits == 0) {
		fprintf(stderr, "nenhuma escrita no APU observada\n");
		return 3;
	}
	uint32_t regionLo = 0xFFFF, regionHi = 0;
	for(auto& kv : writerPcs) {
		regionLo = std::min(regionLo, kv.first);
		regionHi = std::max(regionHi, kv.first);
	}
	printf("   %d escritas, %zu PCs distintos em $%04X-$%04X\n", hits, writerPcs.size(), regionLo, regionHi);
	//Driver region: writer PCs +- 1 KB, clipped to the same 8 KB bank
	uint32_t bankLo = regionLo & 0xE000;
	uint32_t driverLo = std::max<int32_t>((int32_t)bankLo, (int32_t)regionLo - 0x800);
	uint32_t driverHi = std::min<uint32_t>(bankLo + 0x1FFF, regionHi + 0x800);
	//P = the outermost callstack frame (closest to the interrupt) that lands inside the region, majority vote
	std::map<uint32_t, uint32_t> pVotes;
	for(auto& st : stacks) {
		for(uint32_t t : st) { //callstack is ordered from oldest to newest frame
			if(t >= driverLo && t <= driverHi) {
				pVotes[t]++;
				break;
			}
		}
	}
	uint32_t P = 0, pBest = 0;
	for(auto& kv : pVotes) {
		if(kv.second > pBest) {
			P = kv.first;
			pBest = kv.second;
		}
	}
	printf("   região do driver ~ $%04X-$%04X; tick P = $%04X (%u/%d pilhas)\n", driverLo, driverHi, P, pBest, hits);
	{
		printf("   callstack típica: ");
		for(uint32_t t : stacks[stacks.size() / 2]) printf("$%04X ", t);
		printf("\n");
	}
	SetBreakpoints(nullptr, 0);
	SleepMs(50);
	if(IsExecutionStopped()) ResumeExecution();
	SleepMs(100);

	//---------------------------------------------------------------- B) song routine
	printf("== B) quem chama o driver quando a música muda?\n");
	//Title save state for phase C (before any input)

	//B1) Where does code OUTSIDE the driver's bank JSR into the driver? Scan the whole PRG ROM
	//(file bytes) for JSR opcodes whose target lands in the driver's CPU region, skipping sites that
	//live in the driver's own bank, and break on them by ABSOLUTE address (NesPrgRom) so bank
	//aliasing cannot fool us. The function containing the hit is the game-facing trampoline T.
	AddressInfo absP = GetAbsoluteAddress({ (int32_t)P, MemoryType::NesMemory });
	int32_t absDriverLo = absP.Address - (int32_t)(P - driverLo);
	int32_t absDriverHi = absP.Address + (int32_t)(driverHi - P);
	printf("   P=$%04X está em PRG $%05X; banco do driver (abs) ~ $%05X-$%05X\n", P, absP.Address, absDriverLo, absDriverHi);
	std::vector<uint8_t> prg;
	{
		FILE* f = fopen(rom.c_str(), "rb");
		std::vector<uint8_t> file;
		if(f) { uint8_t buf[65536]; size_t n; while((n = fread(buf, 1, sizeof(buf), f)) > 0) file.insert(file.end(), buf, buf + n); fclose(f); }
		size_t off = 16 + ((file.size() > 6 && (file[6] & 4)) ? 512 : 0);
		size_t prgSize = file.size() > 4 ? file[4] * 16384 : 0;
		if(off + prgSize <= file.size()) prg.assign(file.begin() + off, file.begin() + off + prgSize);
	}
	struct JsrSite { uint32_t Abs; uint32_t Target; };
	vector<JsrSite> sites;
	for(size_t a = 0; a + 2 < prg.size(); a++) {
		if(prg[a] != 0x20) continue;
		uint32_t target = prg[a + 1] | (prg[a + 2] << 8);
		bool inDriverBank = (int32_t)a >= absDriverLo && (int32_t)a <= absDriverHi;
		if(!inDriverBank && target >= driverLo && target <= driverHi) {
			sites.push_back({ (uint32_t)a, target });
		}
	}
	std::map<uint32_t, int> targetSites;
	for(JsrSite& j : sites) targetSites[j.Target]++;
	printf("   %zu JSRs (fora do banco do driver) para dentro dele, %zu alvos:", sites.size(), targetSites.size());
	for(auto& kv : targetSites) printf(" $%04X(x%d)", kv.first, kv.second);
	printf("\n");
	std::vector<BreakpointAbi> bps;
	for(size_t i = 0; i < sites.size() && i < 400; i++) {
		BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Execute, sites[i].Abs, sites[i].Abs, (uint32_t)(10 + i));
		bp.Memory = MemoryType::NesPrgRom;
		bps.push_back(bp);
	}
	SetBreakpoints(bps.data(), (uint32_t)bps.size());
	SleepMs(100);

	struct Candidate { uint32_t Target; uint32_t Tramp; uint8_t A, X, Y; uint32_t Site; uint32_t Hits; bool AfterStart; double FirstAfterStart; std::set<uint8_t> As, Xs, Ys; };
	std::map<uint32_t, Candidate> candidates; //keyed by JSR site (CPU address)
	Clock::time_point tB = Clock::now();
	std::thread presser;
	bool pressed = false;
	int stops = 0;
	while(Seconds(tB) < 6.0) {
		if(!pressed && Seconds(tB) > 1.0) {
			pressed = true;
			presser = std::thread([]() { PulseStart(3.0); });
			printf("   Start pulsado a partir de t=%.1fs\n", Seconds(tB));
		}
		if(!WaitForBreak(0.2)) {
			continue;
		}
		stops++;
		uint32_t pc = GetProgramCounter(CpuType::Nes, true);
		if(GetMemoryValue(MemoryType::NesMemory, pc) != 0x20) {
			//the $20 byte we matched is an operand (e.g. STA $2007), not a JSR opcode - exec breakpoints also fire on operand fetches
			ResumeExecution();
			continue;
		}
		uint32_t target = GetMemoryValue(MemoryType::NesMemory, pc + 1) | (GetMemoryValue(MemoryType::NesMemory, pc + 2) << 8);
		if(target < driverLo || target > driverHi) { ResumeExecution(); continue; }
		NesCpuState cpu = {};
		GetCpuState(cpu, CpuType::Nes);
		StackFrameInfo frames[64];
		uint32_t count = 0;
		GetCallstack(CpuType::Nes, frames, count);
		uint32_t tramp = count > 0 && count <= 64 ? frames[count - 1].Target : 0;
		Candidate& c = candidates[pc];
		if(c.Hits == 0) { c.Target = target; c.Tramp = tramp; c.Site = pc; c.A = cpu.A; c.X = cpu.X; c.Y = cpu.Y; c.AfterStart = pressed; c.FirstAfterStart = pressed ? Seconds(tB) : -1; }
		c.Hits++;
		c.As.insert(cpu.A); c.Xs.insert(cpu.X); c.Ys.insert(cpu.Y);
		if(pressed && !c.AfterStart) { c.AfterStart = true; c.FirstAfterStart = Seconds(tB); c.A = cpu.A; c.X = cpu.X; c.Y = cpu.Y; }
		if(target != P) printf("     t=%.2fs JSR $%04X em $%04X  A=%02X X=%02X Y=%02X\n", Seconds(tB), target, pc, cpu.A, cpu.X, cpu.Y);
		ResumeExecution();
	}
	if(presser.joinable()) presser.join();
	SetBreakpoints(nullptr, 0);
	SleepMs(50);
	printf("   %d paradas; sítios de chamada (fora do banco do driver):\n", stops);
	uint32_t S = 0;
	double bestT = 1e9;
	char regConv = 'A';
	for(auto& kv : candidates) {
		Candidate& c = kv.second;
		printf("     JSR $%04X em $%04X (função $%04X)  hits=%u  A∈%zu X∈%zu Y∈%zu valores %s\n", c.Target, c.Site, c.Tramp, c.Hits, c.As.size(), c.Xs.size(), c.Ys.size(), c.AfterStart ? "(após Start)" : "");
		if(c.Target == P) continue; //the per-frame tick
		if(c.AfterStart && c.FirstAfterStart >= 0 && c.FirstAfterStart < bestT) {
			bestT = c.FirstAfterStart;
			S = c.Target;
			//the register that varies across calls carries the id
			regConv = c.As.size() >= c.Xs.size() && c.As.size() >= c.Ys.size() ? 'A' : (c.Xs.size() >= c.Ys.size() ? 'X' : 'Y'); //ties -> A (6502 convention)
		}
	}
	if(S == 0) {
		fprintf(stderr, "nenhuma chamada ao driver fora do tick observada\n");
		Stop();
		return 4;
	}
	printf("   S = $%04X, id passado em %c (primeira chamada %.2fs após o início da fase)\n", S, regConv, bestT);

	//---------------------------------------------------------------- C) enumerate
	printf("== C) chamando S=$%04X com %c=id para id 0..%d (%.0fs cada)\n", S, regConv, maxIds - 1, secondsPerId);
	struct Result { int Id; std::string Kind; uint32_t Audible, LastAudible, Frames; uint32_t Hash; std::string FirstNotes; };
	std::vector<Result> results;
	std::set<uint32_t> seenHashes;
	for(int id = 0; id < maxIds; id++) {
		LoadStateFile((char*)titleState.c_str());
		//the F5.3 segmenter closes a track after 60 silent frames: leave a gap between ids
		SleepMs(bootstrap ? 1300 : 60);
		//Stop at the next driver tick (inside the NMI handler), then hijack
		BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Execute, P, P, 500);
		SetBreakpoints(&bp, 1);
		if(!WaitForBreak(2.0)) {
			printf("   id %2d: sem tick - abortado\n", id);
			SetBreakpoints(nullptr, 0);
			continue;
		}
		SetBreakpoints(nullptr, 0);
		//Hijack: we are stopped at the first instruction of the tick, inside the NMI handler.
		//Redirect the CPU into S with the id in the convention register and make S return into a
		//JMP-self stub in RAM: the game logic never runs again, but NMIs keep firing and ticking
		//the driver, so whatever S started keeps playing.
		NesCpuState cpu = {};
		GetCpuState(cpu, CpuType::Nes);
		SetMemoryValue(MemoryType::NesMemory, 0x0780, 0x4C);
		SetMemoryValue(MemoryType::NesMemory, 0x0781, 0x80);
		SetMemoryValue(MemoryType::NesMemory, 0x0782, 0x07);
		uint16_t ret = 0x077F;
		SetMemoryValue(MemoryType::NesMemory, 0x0100 + cpu.SP, (uint8_t)(ret >> 8));
		cpu.SP--;
		SetMemoryValue(MemoryType::NesMemory, 0x0100 + cpu.SP, (uint8_t)(ret & 0xFF));
		cpu.SP--;
		cpu.PC = (uint16_t)S;
		if(regConv == 'A') cpu.A = (uint8_t)id; else if(regConv == 'X') cpu.X = (uint8_t)id; else cpu.Y = (uint8_t)id;
		SetCpuState(cpu, CpuType::Nes);
		ResumeExecution();
		SleepMs(120); //let the driver react (and the old song stop)
		Sample s = SampleApu(secondsPerId);
		Result r;
		r.Id = id;
		r.Frames = s.Frames;
		r.Audible = s.Audible;
		r.LastAudible = s.LastAudible;
		r.Hash = s.Hash();
		if(s.Audible < 6) {
			r.Kind = "silent";
		} else if(s.LastAudible < s.Frames - 30 && s.LastAudible < 180) {
			r.Kind = "sfx";
		} else {
			r.Kind = "bgm";
		}
		char buf[256] = {};
		size_t pos = 0;
		for(size_t i = 0; i < s.Onsets.size() && i < 12 && pos < 200; i++) {
			pos += snprintf(buf + pos, sizeof(buf) - pos, "%c%d ", "stTn"[(s.Onsets[i] >> 8) & 3], s.Onsets[i] & 0xFF);
		}
		r.FirstNotes = buf;
		bool dup = r.Kind != "silent" && seenHashes.count(r.Hash) > 0;
		seenHashes.insert(r.Hash);
		printf("   id %2d: %-6s audible=%3u/%3u last=%3u hash=%08X %s%s\n", id, r.Kind.c_str(), r.Audible, r.Frames, r.LastAudible, r.Hash, r.FirstNotes.c_str(), dup ? " (repetida)" : "");
		results.push_back(r);
	}
	int bgm = 0, sfx = 0, silent = 0;
	std::set<uint32_t> uniq;
	for(Result& r : results) {
		if(r.Kind == "bgm") bgm++;
		else if(r.Kind == "sfx") sfx++;
		else silent++;
		if(r.Kind != "silent") uniq.insert(r.Hash);
	}
	printf("== resumo: %d bgm, %d sfx, %d silenciosos, %zu assinaturas distintas em %d ids\n", bgm, sfx, silent, uniq.size(), maxIds);
	Stop();
	return 0;
}
