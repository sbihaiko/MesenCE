#pragma once
#include "pch.h"
#include <chrono>
#include "Utilities/safe_ptr.h"

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

//Live logger for the VGM (Video Game Music) v1.71 file format, see
//https://vgmrips.net/wiki/VGM_Specification . Writes raw per-chip register
//writes as VGM stream commands as they happen and appends a GD3 tag block
//(see WriteGd3Tag) when recording stops.
//
//Self-contained by design: chip write-sites (NesApu::WriteRam, GbApu::Write,
//SmsPsg::Write/WritePanningReg, SmsFmAudio::Write, ...) only need to add one
//call - VgmExporter::LogWrite(chip, addrOrPort, value) - guarded by
//IsRecording() so it's a no-op otherwise. No sample count, cycle counter or
//other timing value needs to be threaded through SoundMixer/Emulator to get
//there: the class owns a single static instance (StartRecording/StopRecording
//create and destroy it) and times events itself.
//
//Command timing: VGM streams are sample-accurate at a fixed 44100Hz timebase
//(see EmitWait). Since LogWrite() only receives the raw register write - not
//the emulated master clock - elapsed time between successive writes is
//measured on a real-time (std::chrono::steady_clock) basis and quantized to
//44100Hz "wait" samples, with the leftover fraction carried forward so
//rounding never accumulates into audible drift over a long capture. This
//keeps every call site a plain one-liner at the cost of drifting from
//perfect cycle accuracy only while the host itself isn't running the
//emulation in real time (e.g. paused at a breakpoint, fast-forward, a
//save-state load) - normal gameplay capture is unaffected.
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

	//Standard clock rates for the 4 chips this writer supports; always
	//written into the header (whether or not that chip receives any writes
	//in a given capture) so a single header shape covers every console.
	static constexpr uint32_t NesApuClockHz = 1789773;
	static constexpr uint32_t GameBoyClockHz = 4194304;
	static constexpr uint32_t SmsPsgClockHz = 3579545;
	static constexpr uint32_t SmsYm2413ClockHz = 3579545;

	static safe_ptr<VgmExporter> _instance;

	ofstream _stream;
	string _outputFile;
	std::chrono::steady_clock::time_point _lastEventTime;
	double _pendingSampleFraction = 0;
	uint64_t _totalSamples = 0;
	uint8_t _pendingYm2413Register = 0;

	explicit VgmExporter(string outputFile);

	void WriteHeader();
	void WriteGd3Tag();
	void PatchHeader(uint32_t gd3Offset);
	void EmitWait();
	void WriteChipCommand(VgmChip chip, uint8_t addrOrPort, uint8_t value);
	static void WriteUtf16String(ofstream& stream, const string& value);

public:
	~VgmExporter();

	static void StartRecording(string outputFile);
	static void StopRecording();
	static bool IsRecording();
	static void LogWrite(VgmChip chip, uint8_t addrOrPort, uint8_t value);
};
