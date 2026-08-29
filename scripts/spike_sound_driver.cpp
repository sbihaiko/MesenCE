//Spike (F5.4f research): can the NES sound driver of a game be found and driven
//automatically, NSF-style, to enumerate every music track / SFX without playing?
//
//  A) write breakpoints on the APU registers + callstacks -> the driver's per-frame
//     "tick" routine P and the code region it lives in
//  B) execute breakpoints (absolute PRG addresses) on the JSRs that enter that region
//     from outside the driver's bank while Start is pulsed -> candidate "play id"
//     routines; each candidate is VALIDATED by calling it with a few ids over the title
//     save state and checking the APU output differs from the title's baseline
//  B') fallback when the game never JSRs into its driver: trace ~3 s and find the RAM
//     mailbox (written by the game outside the tick, read by the tick), validated the same way
//  C) for id = 0..N: reload the title save state, fire the trigger at the tick (hijack the
//     CPU into S with the id, or write the mailbox), sample the APU -> kind, length, fingerprint
//
//Build: `make spike-sound-driver` (or, from repo root after `make core`):
//  c++ -std=c++17 -O2 -I . -I Core -Wl,-headerpad_max_install_names scripts/spike_sound_driver.cpp InteropDLL/obj.osx-arm64/MesenCore.dylib -o scripts/spike_sound_driver
//  install_name_tool -change MesenCore.dylib $PWD/InteropDLL/obj.osx-arm64/MesenCore.dylib scripts/spike_sound_driver
//Usage: scripts/spike_sound_driver <rom.nes> <workdir> <output-folder> [maxIds=40] [secondsPerId=4] [startAt=3.0] [wallClockBudget=300]
//  Productised tool (ADR-0135): runs on a private copy of the ROM with the MEP bootstrap on; the
//  F5.3 recorder writes <workdir>/rom/<Game>/auto/audio/ for every enumerated track, then the run
//  relocates fingerprints.json + midi/ into <output-folder>/auto/audio/ and writes enumeration.log
//  beside it. SIGINT aborts at a frame boundary (partial result kept); when no trigger validates,
//  only the log is written (guaranteed no-op on unsupported ROMs).
//  startAt = seconds of emulated time (frames/60) before the title save state is taken
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
#include <csignal>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
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

	void SleepMs(int ms)
	{
		std::this_thread::sleep_for(std::chrono::milliseconds(ms));
	}

	double Seconds(Clock::time_point t0)
	{
		return std::chrono::duration<double>(Clock::now() - t0).count();
	}

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

	std::atomic<uint32_t> g_breaks { 0 };
	uint32_t g_seen = 0;
	BreakEvent g_lastBreak = {};

	//ADR-0135 runtime contract: the whole-run wall-clock budget and the SIGINT
	//abort flag are honoured at frame boundaries; per-id sampling is bounded by
	//emulated frames (Ppu.FrameCount), not wall-clock.
	std::atomic<bool> g_abort { false };
	Clock::time_point g_wallStart = Clock::now();
	double g_wallBudgetSecs = 300.0;

	//ADR-0135 points 2 and 3: true once the SIGINT abort fires or the whole-run
	//wall-clock budget is exhausted. Checked at frame boundaries and loop turns so
	//the run stops with a partial result instead of grinding on.
	bool OutOfBudget()
	{
		return g_abort || Seconds(g_wallStart) > g_wallBudgetSecs;
	}

	void OnNotification(int type, void* param)
	{
		if(type == (int)ConsoleNotificationType::CodeBreak) {
			if(param) {
				g_lastBreak = *(BreakEvent*)param;
			}
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
		while(!IsExecutionStopped()) {
			SleepMs(1);
		}
		return true;
	}

	//Per-frame note snapshot (same audibility rules as NesAudioFingerprint::FromApu)
	struct Note
	{
		int8_t Sq1 = -1, Sq2 = -1, Tri = -1;
		bool Noise = false;
		bool Silent() const { return Sq1 < 0 && Sq2 < 0 && Tri < 0 && !Noise; }
	};

	int8_t FreqToNote(double f)
	{
		if(f <= 0) {
			return -1;
		}
		int n = (int)std::lround(69.0 + 12.0 * std::log2(f / 440.0));
		return (n < 0 || n > 127) ? -1 : (int8_t)n;
	}

	double EnvVolume(const ApuEnvelopeState& env)
	{
		return (env.ConstantVolume ? env.Volume : env.Counter) / 15.0;
	}

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
		uint32_t Frames = 0; //samples taken (~4 per emulated frame)
		uint32_t Audible = 0;
		uint32_t LastAudible = 0;
		std::vector<int16_t> Onsets; //(voice<<8 | note) at note changes
		uint32_t Hash() const
		{
			uint32_t h = 2166136261u;
			for(int16_t o : Onsets) {
				h = (h ^ (uint16_t)o) * 16777619u;
			}
			return h;
		}
		//Only the onsets whose (voice,note) never occurs in the background tune: what the trigger added
		std::vector<int16_t> Novel(const std::set<int16_t>& background) const
		{
			std::vector<int16_t> v;
			for(int16_t o : Onsets) {
				if(!background.count(o)) {
					v.push_back(o);
				}
			}
			return v;
		}
		uint32_t NovelHash(const std::set<int16_t>& background) const
		{
			uint32_t h = 2166136261u;
			for(int16_t o : Novel(background)) {
				h = (h ^ (uint16_t)o) * 16777619u;
			}
			return h;
		}
	};

	uint32_t FrameCount()
	{
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		return st.Ppu.FrameCount;
	}

	//Sample ~4x per frame so no note change of >= 1 frame is missed (a 60 Hz poll
	//drifts against the emu). Bounded by EMULATED frames (Ppu.FrameCount), not
	//wall-clock: the debugger makes wall-clock meaningless (ADR-0135 point 2).
	//A wall-clock backstop still guards a stalled frame counter (e.g. a JMP-self
	//stub the driver waits on); the whole-run wall-clock budget and the SIGINT
	//abort flag are checked at each frame boundary (ADR-0135 points 2 and 3).
	Sample SampleApu(double seconds, size_t maxOnsets = 64)
	{
		uint32_t frames = (uint32_t)std::lround(seconds * 60.0);
		uint32_t startFrame = FrameCount();
		Sample s;
		Note prev;
		Clock::time_point t0 = Clock::now();
		while(!g_abort && FrameCount() - startFrame < frames) {
			if(Seconds(g_wallStart) > g_wallBudgetSecs) {
				printf("   wall-clock budget exceeded\n");
				break;
			}
			if(Seconds(t0) > seconds * 1.5 + 3.0) {
				printf("   no frames advancing - stopping sample\n");
				break;
			}
			Note n = Snapshot();
			s.Frames++;
			if(!n.Silent()) {
				s.Audible++;
				s.LastAudible = s.Frames;
			}
			if(s.Onsets.size() < maxOnsets) {
				if(n.Sq1 >= 0 && n.Sq1 != prev.Sq1) {
					s.Onsets.push_back((int16_t)(0x000 | n.Sq1));
				}
				if(n.Sq2 >= 0 && n.Sq2 != prev.Sq2) {
					s.Onsets.push_back((int16_t)(0x100 | n.Sq2));
				}
				if(n.Tri >= 0 && n.Tri != prev.Tri) {
					s.Onsets.push_back((int16_t)(0x200 | n.Tri));
				}
			}
			prev = n;
			SleepMs(4);
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
	if(argc < 4) {
		fprintf(stderr, "usage: %s <rom.nes> <workdir> <output-folder> [maxIds=40] [secondsPerId=4] [startAt=3.0] [wallClockBudget=300]\n", argv[0]);
		fprintf(stderr, "  Extract-audio tool (ADR-0135): drives the game's NES sound driver via the\n");
		fprintf(stderr, "  debugger to enumerate music/SFX ids without gameplay. Writes\n");
		fprintf(stderr, "  <output-folder>/auto/audio/ (F5.3 recorder fingerprints.json + midi/) plus\n");
		fprintf(stderr, "  enumeration.log beside it. SIGINT aborts at a frame boundary, keeping what was\n");
		fprintf(stderr, "  already written. When no trigger validates, ONLY enumeration.log is written\n");
		fprintf(stderr, "  (guaranteed no-op on unsupported ROMs, ADR-0135 point 4).\n");
		return 1;
	}
	//Line-buffer stdout so the progress output is visible in real time when a
	//GUI launcher tails the tool's log (block-buffered stdout would only flush
	//at exit). The debugger's own "[CPU] Uninitialized memory read" warnings go
	//to stderr and are expected noise from the hijacked CPU.
	setvbuf(stdout, nullptr, _IOLBF, 0);
	signal(SIGINT, [](int) { g_abort = true; });
	g_wallStart = Clock::now();
	std::string rom = argv[1];
	std::string originalRom = rom; //the user-facing path, kept for the enumeration log (rom is later swapped for the private copy)
	std::filesystem::path work = argv[2];
	std::filesystem::path outputFolder = argv[3];
	int maxIds = argc > 4 ? atoi(argv[4]) : 40;
	double secondsPerId = argc > 5 ? atof(argv[5]) : 4.0;
	double startAt = argc > 6 ? atof(argv[6]) : 3.0;
	g_wallBudgetSecs = argc > 7 ? atof(argv[7]) : 300.0;
	std::filesystem::create_directories(work);
	std::filesystem::path home = work / "mesen-home";
	std::filesystem::create_directories(home);

	//ADR-0135 point 6: run the MEP audio/texture bootstrap on a private copy of the ROM so the
	//F5.3 recorder captures every track we enumerate (fingerprints.json + midi/). Always on for
	//this tool - the recorder writes into <workdir>/rom/<Game>/auto/audio/ (never beside the user's
	//ROM; BootstrapEnhancementFolder would otherwise write to the real sibling), and the run
	//relocates that output into the explicit <output-folder>/auto/audio/ at the end.
	bool bootstrap = true;
	{
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
		for(int i = 0; i < 11; i++) {
			nes.ChannelVolumes[i] = 100;
		}
		nes.Port1.Type = ControllerType::NesController; //debugger input overrides need a controller to write into
		SetNesConfig(nes);
	}
	if(!LoadRom((char*)rom.c_str(), (char*)"")) {
		fprintf(stderr, "FAILED to load ROM\n");
		return 2;
	}
	RegisterNotificationCallback(OnNotification);
	if(!getenv("SPIKE_NODEBUG")) {
		InitializeDebugger();
	}
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
		if(st.Ppu.FrameCount >= startFrame) {
			break;
		}
		if(OutOfBudget()) {
			fprintf(stderr, "wall-clock budget exceeded before the title state\n");
			Stop();
			return 5;
		}
		SleepMs(20);
	}
	{
		Sample probe = SampleApu(1.0);
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		printf("   frame %u: %u/%u audible frames on the title screen (hash %08X)\n", st.Ppu.FrameCount, probe.Audible, probe.Frames, probe.Hash());
	}
	SaveStateFile((char*)titleState.c_str());
	SleepMs(100);
	//a second title state 45 frames later: a real "play id" gives the same track from either
	//state, corrupting a driver variable gives phase-dependent garbage
	std::string titleState2 = (work / "title2.mss").string();
	for(;;) {
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		if(st.Ppu.FrameCount >= startFrame + 45 + 60) {
			break;
		}
		if(OutOfBudget()) {
			fprintf(stderr, "wall-clock budget exceeded before the second title state\n");
			Stop();
			return 5;
		}
		SleepMs(20);
	}
	SaveStateFile((char*)titleState2.c_str());
	SleepMs(100);
	if(getenv("SPIKE_NODEBUG")) {
		Stop();
		return 0;
	}

	//---------------------------------------------------------------- helpers over the title state
	//A "trigger" is how the game asks its driver for a sound: a routine called with the id in a
	//register, or a RAM mailbox the per-frame tick polls.
	struct Trigger
	{
		bool Mailbox = false;
		uint32_t Addr = 0;
		char Reg = 'A';
	};
	uint32_t P = 0;
	const int gapMs = bootstrap ? 1300 : 80; //the F5.3 segmenter closes a track after 60 silent frames

	//Reload the title, stop at the tick and fire the trigger with `id`, then sample the APU
	auto playFrom = [&](const std::string& state, const Trigger& t, int id, double seconds, bool* ok) -> Sample {
		LoadStateFile((char*)state.c_str());
		SleepMs(gapMs);
		BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Execute, P, P, 500);
		SetBreakpoints(&bp, 1);
		if(!WaitForBreak(2.0)) {
			SetBreakpoints(nullptr, 0);
			*ok = false;
			return Sample();
		}
		SetBreakpoints(nullptr, 0);
		if(t.Mailbox) {
			SetMemoryValue(MemoryType::NesMemory, t.Addr, (uint8_t)id);
		} else {
			//We are stopped at the first instruction of the tick, inside the NMI handler, with the
			//driver's bank mapped. Redirect the CPU into S with the id in the convention register and
			//make S return into a JMP-self stub in RAM: the game logic never runs again, but NMIs keep
			//firing and ticking the driver, so whatever S started keeps playing.
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
			cpu.PC = (uint16_t)t.Addr;
			if(t.Reg == 'A') {
				cpu.A = (uint8_t)id;
			} else if(t.Reg == 'X') {
				cpu.X = (uint8_t)id;
			} else {
				cpu.Y = (uint8_t)id;
			}
			SetCpuState(cpu, CpuType::Nes);
		}
		ResumeExecution();
		SleepMs(120);
		*ok = true;
		return SampleApu(seconds);
	};
	auto playId = [&](const Trigger& t, int id, double seconds, bool* ok) -> Sample { return playFrom(titleState, t, id, seconds, ok); };

	//---------------------------------------------------------------- A) driver tick
	printf("== A) who writes to the APU sound registers?\n");
	{
		//$4014 (OAM DMA) and $4016/$4017 (controllers) are not sound: they would drag the NMI/input code in
		BreakpointAbi bps[2] = { MakeBp(BreakpointTypeFlags::Write, 0x4000, 0x4013, 1), MakeBp(BreakpointTypeFlags::Write, 0x4015, 0x4015, 2) };
		SetBreakpoints(bps, 2);
	}
	std::map<uint32_t, uint32_t> writerPcs;
	std::vector<std::vector<uint32_t>> stacks;
	Clock::time_point tA = Clock::now();
	int hits = 0;
	std::thread presserA;
	bool pressedA = false;
	while(hits < 600 && Seconds(tA) < 12.0 && !OutOfBudget()) {
		if(!WaitForBreak(1.5)) {
			if(!pressedA) {
				//silent title with no SFX (Castlevania): provoke sound by leaving the title
				pressedA = true;
				presserA = std::thread([]() { PulseStart(4.0); });
				printf("   silent title: pulsing Start to provoke sound\n");
				continue;
			}
			if(Seconds(tA) > 8.0) {
				break;
			}
			continue;
		}
		uint32_t pc = GetProgramCounter(CpuType::Nes, true);
		writerPcs[pc]++;
		StackFrameInfo frames[64];
		uint32_t count = 0;
		GetCallstack(CpuType::Nes, frames, count);
		std::vector<uint32_t> targets;
		for(uint32_t i = 0; i < count && i < 64; i++) {
			targets.push_back(frames[i].Target);
		}
		stacks.push_back(targets);
		hits++;
		ResumeExecution();
	}
	if(presserA.joinable()) {
		presserA.join();
	}
	SetBreakpoints(nullptr, 0);
	SleepMs(50);
	if(hits == 0) {
		fprintf(stderr, "no APU sound write observed (silent title with no SFX?)\n");
		Stop();
		return 3;
	}
	auto nearWriter = [&](uint32_t addr) {
		for(auto& kv : writerPcs) {
			if((addr > kv.first ? addr - kv.first : kv.first - addr) <= 0x1000) {
				return true;
			}
		}
		return false;
	};
	//P = the outermost callstack frame (closest to the interrupt) within 4 KB of a writer, majority vote
	std::map<uint32_t, uint32_t> pVotes;
	for(auto& st : stacks) {
		for(uint32_t t : st) {
			if(t >= 0x8000 && nearWriter(t)) {
				pVotes[t]++;
				break;
			}
		}
	}
	uint32_t pBest = 0;
	for(auto& kv : pVotes) {
		if(kv.second > pBest) {
			P = kv.first;
			pBest = kv.second;
		}
	}
	if(P == 0) {
		fprintf(stderr, "could not find the driver's tick routine\n");
		Stop();
		return 3;
	}
	uint32_t driverLo = P, driverHi = P;
	for(auto& kv : writerPcs) {
		if(nearWriter(P) && (kv.first > P ? kv.first - P : P - kv.first) <= 0x1000) {
			driverLo = std::min(driverLo, kv.first);
			driverHi = std::max(driverHi, kv.first);
		}
	}
	driverLo = std::max<int32_t>(0x8000, (int32_t)driverLo - 0x400);
	driverHi = std::min<uint32_t>(0xFFFF, driverHi + 0x400);
	printf("   %d writes, %zu distinct PCs; tick P = $%04X (%u/%d stacks); driver region ~ $%04X-$%04X\n", hits, writerPcs.size(), P, pBest, hits, driverLo, driverHi);
	{
		printf("   writer PCs:");
		for(auto& kv : writerPcs) {
			printf(" $%04X(x%u)", kv.first, kv.second);
		}
		printf("\n   typical callstack:");
		for(uint32_t t : stacks[stacks.size() / 2]) {
			printf(" $%04X", t);
		}
		printf("\n");
	}

	//Baseline: what the title state sounds like when we do nothing
	LoadStateFile((char*)titleState.c_str());
	SleepMs(gapMs + 120);
	Sample baseline = SampleApu(3.0, 400);
	LoadStateFile((char*)titleState2.c_str());
	SleepMs(gapMs + 120);
	Sample baseline2 = SampleApu(3.0, 400);
	std::set<int16_t> background(baseline.Onsets.begin(), baseline.Onsets.end());
	background.insert(baseline2.Onsets.begin(), baseline2.Onsets.end());
	printf("   title baseline: audible=%u/%u, %zu background (voice,note) pairs\n", baseline.Audible, baseline.Frames, background.size());

	//Try a trigger on a few ids: how many distinct, audible results that differ from the baseline?
	//tickClears: the tick itself writes the address (a request slot it consumes) - then a
	//background tune at a different phase may legitimately break the determinism check (SFX masks)
	auto validate = [&](const Trigger& t, const std::vector<int>& ids, const char* label, bool tickClears) -> int {
		std::set<uint32_t> distinct;
		int deterministic = 0, checked = 0;
		printf("   testing %s:", label);
		for(int id : ids) {
			bool ok = false;
			Sample s = playId(t, id, 1.5, &ok);
			if(!ok) {
				printf(" id%d=no-tick", id);
				continue;
			}
			size_t novel = s.Novel(background).size();
			bool sounds = s.Audible >= 8 && novel >= 2;
			printf(" id%d=%s(%u,%zu novel,%08X)", id, sounds ? "sound" : "-", s.Audible, novel, s.NovelHash(background));
			if(sounds) {
				distinct.insert(s.NovelHash(background));
				if(checked < 2) {
					checked++;
					bool ok2 = false;
					Sample s2 = playFrom(titleState2, t, id, 1.5, &ok2);
					bool same = ok2 && s2.NovelHash(background) == s.NovelHash(background);
					printf("%s", same ? "=" : "≠");
					if(same) {
						deterministic++;
					}
				}
			}
		}
		//tickClears is informative only: the novelty-based hashes already make SFX masks (Zelda $0600)
		//reproducible, and the exemption let driver state variables through (Bomberman $00BE/$00C0)
		bool accepted = distinct.size() >= 3 && deterministic >= 1;
		printf(" -> %zu distinct, %d/%d reproducible%s -> %s\n", distinct.size(), deterministic, checked, tickClears ? ", cleared by the tick" : "", accepted ? "ACCEPTED" : "rejected");
		return accepted ? (int)distinct.size() : 0;
	};

	//---------------------------------------------------------------- B) call-style trigger
	printf("== B) who calls the driver when the music changes?\n");
	AddressInfo absP = GetAbsoluteAddress({ (int32_t)P, MemoryType::NesMemory });
	int32_t absDriverLo = absP.Address - (int32_t)(P - driverLo);
	int32_t absDriverHi = absP.Address + (int32_t)(driverHi - P);
	printf("   P=$%04X is at PRG $%05X; driver (abs) ~ $%05X-$%05X\n", P, absP.Address, absDriverLo, absDriverHi);
	std::vector<uint8_t> prg;
	{
		FILE* f = fopen(rom.c_str(), "rb");
		std::vector<uint8_t> file;
		if(f) {
			uint8_t buf[65536];
			size_t n;
			while((n = fread(buf, 1, sizeof(buf), f)) > 0) {
				file.insert(file.end(), buf, buf + n);
			}
			fclose(f);
		}
		size_t off = 16 + ((file.size() > 6 && (file[6] & 4)) ? 512 : 0);
		size_t prgSize = file.size() > 4 ? file[4] * 16384 : 0;
		if(off + prgSize <= file.size()) {
			prg.assign(file.begin() + off, file.begin() + off + prgSize);
		}
	}
	struct JsrSite
	{
		uint32_t Abs;
		uint32_t Target;
	};
	vector<JsrSite> sites;
	for(size_t a = 0; a + 2 < prg.size(); a++) {
		if(prg[a] != 0x20) {
			continue;
		}
		uint32_t target = prg[a + 1] | (prg[a + 2] << 8);
		bool inDriverBank = (int32_t)a >= absDriverLo && (int32_t)a <= absDriverHi;
		if(!inDriverBank && target >= driverLo && target <= driverHi) {
			sites.push_back({ (uint32_t)a, target });
		}
	}
	std::map<uint32_t, int> targetSites;
	for(JsrSite& j : sites) {
		targetSites[j.Target]++;
	}
	printf("   %zu JSRs (outside the driver's bank) into it, %zu targets\n", sites.size(), targetSites.size());
	std::vector<BreakpointAbi> bps;
	for(size_t i = 0; i < sites.size() && i < 400; i++) {
		BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Execute, sites[i].Abs, sites[i].Abs, (uint32_t)(10 + i));
		bp.Memory = MemoryType::NesPrgRom;
		bps.push_back(bp);
	}
	LoadStateFile((char*)titleState.c_str());
	SleepMs(100);
	uint32_t frame0 = 0;
	{
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		frame0 = st.Ppu.FrameCount;
	}
	SetBreakpoints(bps.data(), (uint32_t)bps.size());

	struct Candidate
	{
		uint32_t Target;
		uint32_t Hits = 0;
		std::set<uint32_t> Sites;
		std::set<uint8_t> As, Xs, Ys;
		bool AfterStart = false;
		double FirstAfterStart = -1;
		bool Pruned = false;
		bool PerFrame = false;
		size_t Variance() const { return std::max(As.size(), std::max(Xs.size(), Ys.size())); }
	};
	std::map<uint32_t, Candidate> candidates; //keyed by target
	Clock::time_point tB = Clock::now();
	std::thread presser;
	bool pressed = false;
	int stops = 0;
	while(Seconds(tB) < 6.0 && !OutOfBudget()) {
		if(!pressed && Seconds(tB) > 1.0) {
			pressed = true;
			presser = std::thread([]() { PulseStart(3.0); });
			printf("   Start pulsed starting at t=%.1fs\n", Seconds(tB));
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
		if(target < driverLo || target > driverHi || target == P) {
			ResumeExecution();
			continue;
		}
		NesCpuState cpu = {};
		GetCpuState(cpu, CpuType::Nes);
		Candidate& c = candidates[target];
		c.Target = target;
		c.Hits++;
		c.Sites.insert(pc);
		c.As.insert(cpu.A);
		c.Xs.insert(cpu.X);
		c.Ys.insert(cpu.Y);
		if(pressed && !c.AfterStart) {
			c.AfterStart = true;
			c.FirstAfterStart = Seconds(tB);
		}
		if(c.Hits == 60) {
			//hot routine (called several times per frame): we know enough, stop paying for its breaks
			std::vector<BreakpointAbi> keep;
			for(BreakpointAbi& b : bps) {
				uint32_t i = b.Id - 10;
				if(i < sites.size() && sites[i].Target == target) {
					continue;
				}
				keep.push_back(b);
			}
			bps = keep;
			SetBreakpoints(bps.data(), (uint32_t)bps.size());
			c.Pruned = true;
		}
		ResumeExecution();
	}
	if(presser.joinable()) {
		presser.join();
	}
	SetBreakpoints(nullptr, 0);
	SleepMs(50);
	uint32_t framesB = 0;
	{
		NesState st = {};
		GetConsoleState(*(BaseState*)&st, ConsoleType::Nes);
		framesB = st.Ppu.FrameCount - frame0;
	}
	printf("   %d stops in %u frames; targets called from outside the driver:\n", stops, framesB);
	std::vector<Candidate*> ranked;
	for(auto& kv : candidates) {
		Candidate& c = kv.second;
		//called (almost) every frame: usually an update routine - but Konami-style drivers take the
		//request register every NMI, so per-frame callers with a varying register stay in the race
		c.PerFrame = c.Pruned || c.Hits * 4 >= framesB;
		printf("     $%04X  hits=%u sites=%zu A∈%zu X∈%zu Y∈%zu %s%s\n", c.Target, c.Hits, c.Sites.size(), c.As.size(), c.Xs.size(), c.Ys.size(), c.AfterStart ? "(after Start) " : "", c.PerFrame ? "[per frame]" : "");
		if(!c.PerFrame || c.Variance() > 1) {
			ranked.push_back(&c);
		}
	}
	std::sort(ranked.begin(), ranked.end(), [](Candidate* a, Candidate* b) {
		if(a->PerFrame != b->PerFrame) {
			return !a->PerFrame;
		}
		if(a->PerFrame) {
			return a->Variance() > b->Variance();
		}
		if(a->AfterStart != b->AfterStart) {
			return a->AfterStart;
		}
		if(a->Sites.size() != b->Sites.size()) {
			return a->Sites.size() > b->Sites.size();
		}
		return a->Hits < b->Hits;
	});

	Trigger best;
	int bestScore = 0;
	std::vector<Trigger> triggers; //every validated way to request a sound (music and SFX often differ)
	auto idsFor = [](const std::set<uint8_t>& seen) {
		std::vector<int> ids;
		for(uint8_t v : seen) {
			if(v < 0x80 && ids.size() < 2) {
				ids.push_back(v);
			}
		}
		for(int v : { 1, 2, 3, 4, 5 }) {
			if(ids.size() >= 5) {
				break;
			}
			if(std::find(ids.begin(), ids.end(), v) == ids.end()) {
				ids.push_back(v);
			}
		}
		return ids;
	};
	for(size_t i = 0; i < ranked.size() && i < 10 && bestScore < 3 && !OutOfBudget(); i++) {
		Candidate& c = *ranked[i];
		//register order: the one that varies most first, ties A, X, Y
		std::vector<std::pair<char, const std::set<uint8_t>*>> regs = { { 'A', &c.As }, { 'X', &c.Xs }, { 'Y', &c.Ys } };
		std::stable_sort(regs.begin(), regs.end(), [](auto& a, auto& b) { return a.second->size() > b.second->size(); });
		for(size_t r = 0; r < 2 && bestScore < 3; r++) {
			Trigger t;
			t.Addr = c.Target;
			t.Reg = regs[r].first;
			char label[64];
			snprintf(label, sizeof(label), "JSR $%04X with %c=id", t.Addr, t.Reg);
			int score = validate(t, idsFor(*regs[r].second), label, false);
			if(score > bestScore) {
				bestScore = score;
				best = t;
			}
		}
	}

	//---------------------------------------------------------------- B') mailbox fallback
	if(bestScore < 3) {
		printf("== B') no convincing call found: looking for a RAM mailbox (trace)\n");
		//Trace ~3 s around a pulsed Start and cross "RAM written outside the tick" with "RAM read
		//inside the tick". The tick region is delimited by the JSR site that calls P and its return.
		uint32_t tickSite = 0;
		for(JsrSite& j : sites) {
			if(j.Target == P) {
				tickSite = prg[j.Abs] == 0x20 ? 0 : 0;
			}
		}
		//CPU address of the tick call site: from the callstack seen in phase A (frame whose Target == P)
		{
			BreakpointAbi bp = MakeBp(BreakpointTypeFlags::Execute, P, P, 501);
			LoadStateFile((char*)titleState.c_str());
			SleepMs(gapMs);
			SetBreakpoints(&bp, 1);
			if(WaitForBreak(2.0)) {
				StackFrameInfo frames[64];
				uint32_t count = 0;
				GetCallstack(CpuType::Nes, frames, count);
				for(uint32_t i = 0; i < count && i < 64; i++) {
					if(frames[i].Target == P) {
						tickSite = frames[i].Source;
					}
				}
				SetBreakpoints(nullptr, 0);
				ResumeExecution();
			}
			SetBreakpoints(nullptr, 0);
		}
		printf("   tick called at $%04X\n", tickSite);
		std::string tracePath = (work / "trace.txt").string();
		LoadStateFile((char*)titleState.c_str());
		SleepMs(100);
		TraceLoggerOptions opt = {};
		opt.Enabled = true;
		snprintf(opt.Format, sizeof(opt.Format), "%s", "[ByteCode,11] [EffectiveAddress] A:[A,2h] X:[X,2h] Y:[Y,2h] F:[FrameCount]");
		SetTraceOptions(CpuType::Nes, opt);
		StartLogTraceToFile(tracePath.c_str());
		SleepMs(200);
		PulseStart(2.5);
		SleepMs(500);
		StopLogTraceToFile();
		opt.Enabled = false;
		SetTraceOptions(CpuType::Nes, opt);
		SleepMs(100);

		struct WriteEv
		{
			uint32_t Frame;
			uint8_t Value;
			uint32_t Pc;
		};
		std::map<uint32_t, std::vector<WriteEv>> writesOutside;
		std::map<uint32_t, uint32_t> readsInTick, writesInTick;
		uint32_t lines = 0;
		{
			FILE* f = fopen(tracePath.c_str(), "r");
			char line[600];
			bool inTick = false;
			while(f && fgets(line, sizeof(line), f)) {
				lines++;
				uint32_t pc = (uint32_t)strtoul(line, nullptr, 16);
				unsigned b0 = 0, b1 = 0, b2 = 0;
				int nb = sscanf(line + 6, "%2x %2x %2x", &b0, &b1, &b2);
				const char* eff = strstr(line, "[$");
				const char* fa = strstr(line, "F:");
				const char* aa = strstr(line, "A:");
				uint32_t frame = fa ? (uint32_t)atoi(fa + 2) : 0;
				uint8_t regA = aa ? (uint8_t)strtoul(aa + 2, nullptr, 16) : 0;
				if(tickSite && pc == tickSite) {
					inTick = true;
				} else if(tickSite && pc == tickSite + 3) {
					inTick = false;
				} else if(!tickSite) {
					inTick = pc >= driverLo && pc <= driverHi;
				}
				int32_t addr = -1;
				if(eff) {
					addr = (int32_t)strtoul(eff + 2, nullptr, 16);
				} else if(nb == 3) {
					addr = b1 | (b2 << 8);
				} else if(nb == 2) {
					addr = b1;
				}
				if(addr < 0 || addr >= 0x800) {
					continue;
				}
				bool isStore = false, isLoad = false;
				switch(b0) {
					case 0x85:
					case 0x95:
					case 0x8D:
					case 0x9D:
					case 0x99:
					case 0x81:
					case 0x91:
					case 0x86:
					case 0x96:
					case 0x8E:
					case 0x84:
					case 0x94:
					case 0x8C:
						isStore = true;
						break;
					case 0xE6:
					case 0xF6:
					case 0xEE:
					case 0xFE:
					case 0xC6:
					case 0xD6:
					case 0xCE:
					case 0xDE:
						isStore = true;
						isLoad = true;
						break;
					case 0xA5:
					case 0xB5:
					case 0xAD:
					case 0xBD:
					case 0xB9:
					case 0xA1:
					case 0xB1:
					case 0xA6:
					case 0xB6:
					case 0xAE:
					case 0xBE:
					case 0xA4:
					case 0xB4:
					case 0xAC:
					case 0xBC:
					case 0xC5:
					case 0xD5:
					case 0xCD:
					case 0xDD:
					case 0xD9:
					case 0xC1:
					case 0xD1:
					case 0x24:
					case 0x2C:
					case 0xE4:
					case 0xEC:
					case 0xC4:
					case 0xCC:
					case 0x05:
					case 0x15:
					case 0x0D:
					case 0x1D:
					case 0x19:
					case 0x01:
					case 0x11:
					case 0x25:
					case 0x35:
					case 0x2D:
					case 0x3D:
					case 0x39:
					case 0x21:
					case 0x31:
					case 0x45:
					case 0x55:
					case 0x4D:
					case 0x5D:
					case 0x59:
					case 0x41:
					case 0x51:
					case 0x65:
					case 0x75:
					case 0x6D:
					case 0x7D:
					case 0x79:
					case 0x61:
					case 0x71:
					case 0xE5:
					case 0xF5:
					case 0xED:
					case 0xFD:
					case 0xF9:
					case 0xE1:
					case 0xF1:
						isLoad = true;
						break;
					default: break;
				}
				if(inTick) {
					if(isLoad) {
						readsInTick[addr]++;
					}
					if(isStore) {
						writesInTick[addr]++;
					}
				} else if(isStore) {
					uint8_t v = regA;
					if(b0 == 0x86 || b0 == 0x96 || b0 == 0x8E) {
						const char* xx = strstr(line, "X:");
						v = xx ? (uint8_t)strtoul(xx + 2, nullptr, 16) : 0;
					}
					if(b0 == 0x84 || b0 == 0x94 || b0 == 0x8C) {
						const char* yy = strstr(line, "Y:");
						v = yy ? (uint8_t)strtoul(yy + 2, nullptr, 16) : 0;
					}
					writesOutside[addr].push_back({ frame, v, pc });
				}
			}
			if(f) {
				fclose(f);
			}
		}
		struct Mailbox
		{
			uint32_t Addr;
			size_t OutsideWrites;
			uint32_t TickReads;
			uint32_t TickWrites;
			std::vector<WriteEv> Events;
		};
		std::vector<Mailbox> mailboxes;
		for(auto& kv : readsInTick) {
			auto o = writesOutside.find(kv.first);
			size_t outside = o == writesOutside.end() ? 0 : o->second.size();
			if(outside > 60) {
				continue; //written every frame by the game: state, not a request
			}
			auto w = writesInTick.find(kv.first);
			mailboxes.push_back({ kv.first, outside, kv.second, w == writesInTick.end() ? 0u : w->second, o == writesOutside.end() ? std::vector<WriteEv>() : o->second });
		}
		//a request slot is read by the tick every frame, written by the game rarely (maybe not in our
		//window at all) and usually cleared by the tick - every address the tick reads is a candidate
		std::sort(mailboxes.begin(), mailboxes.end(), [](const Mailbox& a, const Mailbox& b) {
			int sa = (a.OutsideWrites > 0 ? 2 : 0) + (a.TickWrites > 0 ? 1 : 0);
			int sb = (b.OutsideWrites > 0 ? 2 : 0) + (b.TickWrites > 0 ? 1 : 0);
			if(sa != sb) {
				return sa > sb;
			}
			if(a.TickReads != b.TickReads) {
				return a.TickReads > b.TickReads;
			}
			return a.Addr < b.Addr;
		});
		printf("   trace: %u lines; %zu addresses read in the tick, %zu written outside; candidates:\n", lines, readsInTick.size(), writesOutside.size());
		for(size_t i = 0; i < mailboxes.size() && i < 40; i++) {
			Mailbox& m = mailboxes[i];
			printf("     $%04X  outside writes=%zu  tick reads=%u  tick writes=%u  events:", m.Addr, m.OutsideWrites, m.TickReads, m.TickWrites);
			for(size_t j = 0; j < m.Events.size() && j < 6; j++) {
				printf(" f%u:%02X@$%04X", m.Events[j].Frame, m.Events[j].Value, m.Events[j].Pc);
			}
			printf("\n");
		}
		for(size_t i = 0; i < mailboxes.size() && i < 40 && triggers.size() < 3 && !OutOfBudget(); i++) {
			Trigger t;
			t.Mailbox = true;
			t.Addr = mailboxes[i].Addr;
			std::set<uint8_t> seen;
			for(WriteEv& e : mailboxes[i].Events) {
				if(e.Value) {
					seen.insert(e.Value);
				}
			}
			char label[64];
			snprintf(label, sizeof(label), "mailbox $%04X", t.Addr);
			int score = validate(t, idsFor(seen), label, mailboxes[i].TickWrites > 0 && mailboxes[i].TickWrites * 2 < mailboxes[i].TickReads);
			if(score > bestScore) {
				bestScore = score;
				best = t;
			}
			if(score >= 3) {
				triggers.push_back(t);
			}
		}
	} else {
		triggers.push_back(best);
	}
	if(bestScore < 3) {
		fprintf(stderr, "no validated trigger (best score %d)\n", bestScore);
		//ADR-0135 points 4 and 6: guaranteed no-op - nothing reaches
		//<output-folder>/auto/audio/ (no fingerprints), only the enumeration log,
		//and the game state is untouched (private instance).
		std::filesystem::path logPath = outputFolder / "auto" / "audio" / "enumeration.log";
		std::error_code ec;
		std::filesystem::create_directories(logPath.parent_path(), ec);
		std::ofstream log(logPath);
		log << "# Extract-audio probe (ADR-0135). ROM: " << originalRom << "\n";
		log << "status: no validated trigger (best score " << bestScore << ") - no audio written\n";
		log.close();
		Stop();
		return 4;
	}
	for(Trigger& t : triggers) {
		if(t.Mailbox) {
			printf("   trigger: write id to $%04X on tick entry\n", t.Addr);
		} else {
			printf("   trigger: JSR $%04X with %c=id\n", t.Addr, t.Reg);
		}
	}

	//---------------------------------------------------------------- C) enumerate
	struct Result
	{
		int Id;
		std::string Kind;
		uint32_t Audible, LastAudible, Frames;
		uint32_t Hash;
		std::string FirstNotes;
		bool Repeat = false;
	};
	std::vector<Result> results;
	std::set<uint32_t> seenHashes;
	for(Trigger& trig : triggers) {
		if(trig.Mailbox) {
			printf("== C) enumerating id 0..%d at $%04X (%.0fs each)\n", maxIds - 1, trig.Addr, secondsPerId);
		} else {
			printf("== C) enumerating id 0..%d via JSR $%04X %c=id (%.0fs each)\n", maxIds - 1, trig.Addr, trig.Reg, secondsPerId);
		}
		for(int id = 0; id < maxIds; id++) {
			if(OutOfBudget()) {
				printf("   wall-clock budget exceeded - stopping enumeration (partial result)\n");
				break;
			}
			bool ok = false;
			Sample s = playId(trig, id, secondsPerId, &ok);
			if(!ok) {
				printf("   id %2d: no tick - aborted\n", id);
				continue;
			}
			Result r;
			r.Id = id;
			r.Frames = s.Frames;
			r.Audible = s.Audible;
			r.LastAudible = s.LastAudible;
			r.Hash = s.Hash();
			size_t novel = s.Novel(background).size();
			bool sameAsTitle = baseline.Audible >= 8 && novel < 2;
			r.Hash = s.NovelHash(background);
			if(s.Audible < 24 || sameAsTitle) {
				r.Kind = sameAsTitle ? "title" : "short";
			} else if(s.LastAudible < s.Frames - 120 && s.LastAudible < 720) {
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
			bool dup = (r.Kind == "bgm" || r.Kind == "sfx") && seenHashes.count(r.Hash) > 0;
			seenHashes.insert(r.Hash);
			r.Repeat = dup;
			printf("   id %2d: %-5s audible=%3u/%3u last=%3u hash=%08X %s%s\n", id, r.Kind.c_str(), r.Audible, r.Frames, r.LastAudible, r.Hash, r.FirstNotes.c_str(), dup ? " (repeat)" : "");
			results.push_back(r);
		}
	}
	int bgm = 0, sfx = 0, shortN = 0, title = 0;
	std::set<uint32_t> uniq;
	for(Result& r : results) {
		if(r.Kind == "bgm") {
			bgm++;
		} else if(r.Kind == "sfx") {
			sfx++;
		} else if(r.Kind == "title") {
			title++;
		} else {
			shortN++;
		}
		if(r.Kind == "bgm" || r.Kind == "sfx") {
			uniq.insert(r.Hash);
		}
	}
	printf("== summary: %d bgm, %d sfx, %d short, %d = title, %zu distinct signatures across %d ids x %zu trigger(s)\n", bgm, sfx, shortN, title, uniq.size(), maxIds, triggers.size());
	//The F5.3 recorder flushes fingerprints.json + midi/ only in its destructor
	//(NesAudioBootstrap::~NesAudioBootstrap -> TrackSegmenter::Save), which runs
	//when the Emulator is destroyed. The interop Release() performs that teardown
	//(_emu.reset() in EmuApiWrapper), so it must run BEFORE the output is
	//relocated - a plain Stop() leaves the fingerprints unflushed.
	Release();
	//ADR-0135 point 6: relocate the recorder's output (written under the private
	//<workdir>/rom/<Game>/auto/audio/) into the explicit output folder and keep
	//the enumeration log beside the fingerprints. On abort this keeps the partial
	//audio already recorded (point 3).
	{
		std::filesystem::path recRoot = work / "rom";
		std::error_code ec;
		std::filesystem::path found;
		for(auto& entry : std::filesystem::directory_iterator(recRoot, ec)) {
			if(entry.is_directory(ec)) {
				std::filesystem::path candidate = entry.path() / "auto" / "audio";
				if(std::filesystem::exists(candidate / "fingerprints.json", ec)) {
					found = candidate;
					break;
				}
			}
		}
		if(found.empty()) {
			fprintf(stderr, "WARNING: recorder output not found under %s - pack audio not written\n", recRoot.c_str());
		} else {
			std::filesystem::path dest = outputFolder / "auto" / "audio";
			std::filesystem::create_directories(dest, ec);
			ec.clear();
			for(auto& entry : std::filesystem::directory_iterator(found, ec)) {
				std::filesystem::copy(entry.path(), dest / entry.path().filename(), std::filesystem::copy_options::recursive | std::filesystem::copy_options::overwrite_existing, ec);
				if(ec) {
					fprintf(stderr, "WARNING: copying recorder output failed: %s\n", ec.message().c_str());
					ec.clear();
				}
			}
			printf("   audio written to %s\n", dest.c_str());
		}
		std::filesystem::path logPath = outputFolder / "auto" / "audio" / "enumeration.log";
		std::filesystem::create_directories(logPath.parent_path(), ec);
		std::ofstream log(logPath);
		log << "# Extract-audio probe (ADR-0135). ROM: " << originalRom << "\n";
		log << "status: " << (g_abort ? "aborted (SIGINT) - partial result" : "ok") << "\n";
		log << "tick: $" << std::hex << std::uppercase << P << std::dec << "\n";
		for(Trigger& t : triggers) {
			if(t.Mailbox) {
				log << "trigger: mailbox $" << std::hex << std::uppercase << t.Addr << std::dec << "\n";
			} else {
				log << "trigger: JSR $" << std::hex << std::uppercase << t.Addr << std::dec << " with " << t.Reg << "=id\n";
			}
		}
		log << "budget: " << maxIds << " ids x " << (int)secondsPerId << "s emulated each, wall-clock cap " << (int)g_wallBudgetSecs << "s\n";
		log << "id,kind,audible,frames,last,hash,first-notes,repeat\n";
		for(Result& r : results) {
			log << r.Id << "," << r.Kind << "," << r.Audible << "," << r.Frames << "," << r.LastAudible << ","
			    << std::hex << std::uppercase << r.Hash << std::dec << ",\"" << r.FirstNotes << "\"," << (r.Repeat ? "yes" : "no") << "\n";
		}
		log << "summary: " << bgm << " bgm, " << sfx << " sfx, " << shortN << " short, " << title << " title, " << uniq.size() << " distinct signatures\n";
		log << "rejected candidates: any candidate below the >= 3 validation bar (see best score above)\n";
		log.close();
		printf("   wrote %s\n", logPath.c_str());
	}
	return 0;
}
