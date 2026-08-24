#pragma once

#include "pch.h"
#include "Utilities/ISerializable.h"
#include "NES/INesMemoryHandler.h"
#include "NES/NesTypes.h"

class NesConsole;
class SquareChannel;
class TriangleChannel;
class NoiseChannel;
class DeltaModulationChannel;
class ApuFrameCounter;
class NesSoundMixer;
class EmuSettings;

enum class FrameType;
enum class ConsoleRegion;

//Live VGM capture note: NesApu::WriteRam only ever sees $4015 (enable/status) -
//the other APU registers ($4000-4013, $4017) are each memory-mapped directly
//to their owning channel class (SquareChannel, TriangleChannel, NoiseChannel,
//DeltaModulationChannel, ApuFrameCounter) by NesMemoryManager, so NesApu
//can't see those writes go by in its own WriteRam. Rather than adding a tap
//to each of those channel classes, NesApu registers each one with the memory
//manager through a thin NesApuRegisterTap decorator (below) instead of
//registering the channel directly - the decorator forwards every call
//through unchanged except WriteRam, which it logs via VgmExporter::LogWrite
//before forwarding. See VgmExporter.h for the log format.
class NesApuRegisterTap : public INesMemoryHandler
{
private:
	INesMemoryHandler* _handler;

public:
	explicit NesApuRegisterTap(INesMemoryHandler* handler) : _handler(handler) {}

	void GetMemoryRanges(MemoryRanges& ranges) override { _handler->GetMemoryRanges(ranges); }
	uint8_t ReadRam(uint16_t addr) override { return _handler->ReadRam(addr); }
	uint8_t PeekRam(uint16_t addr) override { return _handler->PeekRam(addr); }
	void WriteRam(uint16_t addr, uint8_t value) override;
};

class NesApu : public ISerializable, public INesMemoryHandler
{
	friend ApuFrameCounter;

private:
	bool _apuEnabled;
	bool _needToRun;

	uint32_t _previousCycle;
	uint32_t _currentCycle;

	unique_ptr<SquareChannel> _square1;
	unique_ptr<SquareChannel> _square2;
	unique_ptr<TriangleChannel> _triangle;
	unique_ptr<NoiseChannel> _noise;
	unique_ptr<DeltaModulationChannel> _dmc;
	unique_ptr<ApuFrameCounter> _frameCounter;

	//Registered with the memory manager in place of the channel objects
	//above - see the NesApuRegisterTap comment above for why.
	unique_ptr<NesApuRegisterTap> _square1Tap;
	unique_ptr<NesApuRegisterTap> _square2Tap;
	unique_ptr<NesApuRegisterTap> _triangleTap;
	unique_ptr<NesApuRegisterTap> _noiseTap;
	unique_ptr<NesApuRegisterTap> _dmcTap;
	unique_ptr<NesApuRegisterTap> _frameCounterTap;

	NesConsole* _console;
	NesSoundMixer* _mixer;
	EmuSettings* _settings;

	ConsoleRegion _region;

	uint64_t _apuDisabledStamp = 0;

private:
	__forceinline bool NeedToRun(uint32_t currentCycle);

	void FrameCounterTick(FrameType type);

	template<bool isPeek = false>
	uint8_t GetStatus();

public:
	NesApu(NesConsole* console);
	~NesApu();

	void Serialize(Serializer& s) override;

	void Reset(bool softReset);
	void SetRegion(ConsoleRegion region, bool forceInit = false);

	uint8_t ReadRam(uint16_t addr) override;
	uint8_t PeekRam(uint16_t addr) override;
	void WriteRam(uint16_t addr, uint8_t value) override;
	void GetMemoryRanges(MemoryRanges& ranges) override;

	ApuState GetState();

	void Exec();
	void ProcessCpuClock();
	void Run();
	void EndFrame();

	void AddExpansionAudioDelta(AudioChannel channel, int16_t delta);
	void SetApuStatus(bool enabled);
	bool IsApuEnabled();
	static ConsoleRegion GetApuRegion(NesConsole* console);
	uint16_t GetDmcReadAddress();
	void SetDmcReadBuffer(uint8_t value);
	void SetNeedToRun();
};