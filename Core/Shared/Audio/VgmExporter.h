#pragma once
#include "pch.h"
#include <chrono>

//Which chip a LogWrite() call targets. The VGM command opcode (and whether
//"addrOrPort" is even meaningful) depends entirely on this - see
//VgmExporter::WriteChipCommand in the .cpp for the exact mapping:
//  NesApu       -> 0xB4 aa dd (aa = APU register offset from $4000)
//  GameBoyDmg   -> 0xB3 aa dd (aa = GB APU register offset from $FF10)
//  SmsPsg       -> 0x50 dd    (SN76489 data byte; addrOrPort is ignored -
//                              the register is encoded in the byte itself)
//  SmsPsgStereo -> 0x4F dd    (Game Gear PSG stereo panning byte; ditto)
//  SmsYm2413    -> 0x51 aa dd (YM2413 register write; the chip is written as
//                              two bus cycles - a port-0 "latch" of the
//                              register number, then a port-1 data write -
//                              so VgmExporter itself remembers the latched
//                              register from the port-0 call and only emits
//                              the combined command on the matching port-1
//                              call. Pass addrOrPort=0 for the latch write
//                              and addrOrPort=1 for the data write, exactly
//                              as SmsFmAudio::Write's own port parameter.)
enum class VgmChip : uint8_t
{
	NesApu,
	GameBoyDmg,
	SmsPsg,
	SmsPsgStereo,
	SmsYm2413
};

class Emulator;

//Live logger for the VGM (Video Game Music) v1.71 file format, see
//https://vgmrips.net/wiki/VGM_Specification . Writes raw per-chip register
//writes as VGM stream commands as they happen and appends a GD3 tag block
//(see WriteGd3Tag) when recording stops.
//
//Ownership (ADR-0012): owned per-Emulator by SoundMixer (safe_ptr member,
//mirroring _waveRecorder). Chip write-sites (SquareChannel::WriteRam,
//GbApu::Write, SmsPsg::Write/WritePanningReg, SmsFmAudio::Write, ...) guard
//with a single cached-pointer load - `if(VgmExporter* vgm =
//soundMixer->GetVgmExporter())` - so the no-recording steady state costs a
//couple of dependent loads and one branch, with no lock, refcount traffic or
//virtual dispatch on the hottest emulation paths (ADR-0011). Start/stop go
//through SoundMixer and must run while the emulation thread is paused (the
//interop layer wraps them in Emulator::AcquireLock()); captures stop on ROM
//load/unload and power-off and survive a soft reset.
//
//Command timing (ADR-0013): VGM streams are sample-accurate at a fixed
//44100Hz timebase. SoundMixer::PlayAudioBuffer feeds AddSamples() with every
//flush's emulated sampleCount/sourceRate (run-ahead frames excluded), and
//EmitWait() derives waits from that emulated 44100Hz counter - so captures
//are region-correct and immune to fast-forward, pause-at-breakpoint and
//save-state loads. If no sample clock has been fed yet (no flush since
//recording started), EmitWait falls back to real-time std::chrono deltas so
//a capture never stalls; the fraction carry in both paths keeps rounding
//from accumulating into audible drift over a long capture.
class VgmExporter
{
public:
	//VGM header "Version number" field (see WriteHeader): 0x00000171 = v1.71,
	//the newest revision whose GD3/chip-clock layout this writer targets.
	static constexpr uint32_t VgmVersion = 0x00000171;
	static constexpr uint32_t VgmSampleRate = 44100;

private:
	//Header size in bytes, up to and including the (v1.71) SCSP clock field
	//and the (v1.70) extra-header-offset field; VgmDataOffset (header field
	//at 0x34) always points to HeaderSize, so the data block starts right
	//after the fixed header with no gap.
	static constexpr uint32_t HeaderSize = 0xC0;

	//NTSC fallback clock rates for the 4 chips this writer supports. Used
	//only when SetChipClock() was never called for a chip that did receive
	//writes; PatchHeader zeroes the clock of any chip with no writes at all,
	//so players don't allocate (or validators flag) chips absent from the
	//capture.
	static constexpr uint32_t NesApuClockHz = 1789773;
	static constexpr uint32_t GameBoyClockHz = 4194304;
	static constexpr uint32_t SmsPsgClockHz = 3579545;
	static constexpr uint32_t SmsYm2413ClockHz = 3579545;

	Emulator* _emu = nullptr;
	ofstream _stream;
	string _outputFile;

	//Per-chip state for the final header patch: which chips actually got
	//commands, and the console's real clock for them (0 = use the NTSC
	//fallback above). Indexed by (int)VgmChip.
	bool _chipUsed[5] = {};
	uint32_t _chipClock[5] = {};

	//Command-stream bytes are appended here on the emulation thread and only
	//reach the ofstream in FlushCommandBuffer(), called at the audio flush
	//cadence from AddSamples() and at teardown - so a register write never
	//does stream I/O on the hot path (ADR-0011).
	vector<uint8_t> _cmdBuffer;

	//Emulated 44100Hz sample clock (see the class comment): total emulated
	//samples elapsed since recording started, and how many of them have
	//already been emitted as wait commands.
	double _sampleClock = 0;
	uint64_t _emittedSamples = 0;
	bool _clockFed = false;

	//Real-time fallback state, used only until the first AddSamples() call.
	std::chrono::steady_clock::time_point _lastEventTime;
	double _pendingSampleFraction = 0;

	uint64_t _totalSamples = 0;
	uint8_t _pendingYm2413Register = 0;

	void WriteHeader();
	void WriteGd3Tag();
	void PatchHeader(uint32_t gd3Offset);
	void EmitWait();
	void EmitWaitSamples(uint64_t wholeSamples);
	void WriteChipCommand(VgmChip chip, uint8_t addrOrPort, uint8_t value);
	void FlushCommandBuffer();
	static void WriteUtf16String(ofstream& stream, const string& value);

public:
	//Opens and validates the output stream immediately, so a bad path fails
	//at StartVgmRecording time. Check IsValid() after construction.
	VgmExporter(string outputFile, Emulator* emu);
	~VgmExporter();

	//Records the console's real clock for a chip (e.g. the PAL SMS master
	//clock), written into the header at teardown instead of the NTSC
	//fallback. Call right after construction - SoundMixer::StartVgmRecording
	//does this from Emulator::GetMasterClockRate().
	void SetChipClock(VgmChip chip, uint32_t clockHz) { _chipClock[(int)chip] = clockHz; }

	bool IsValid() { return (bool)_stream; }

	//Advances the emulated sample clock by one audio flush's worth of time
	//(sampleCount samples at sampleRate Hz, rescaled to the 44100Hz VGM
	//timebase). Called by SoundMixer::PlayAudioBuffer with the pre-resample
	//sample count/rate; run-ahead frames must not be fed.
	void AddSamples(uint32_t sampleCount, uint32_t sampleRate);

	//Logs one raw chip register write, preceded by the waits accumulated on
	//the sample clock since the previous command.
	void LogWrite(VgmChip chip, uint8_t addrOrPort, uint8_t value);
};
