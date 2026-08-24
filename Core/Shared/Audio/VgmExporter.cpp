#include "pch.h"
#include "Shared/Audio/VgmExporter.h"
#include "Shared/Emulator.h"

namespace
{
	void PutU32(vector<uint8_t>& buffer, uint32_t offset, uint32_t value)
	{
		memcpy(buffer.data() + offset, &value, sizeof(value));
	}

	void PutU16(vector<uint8_t>& buffer, uint32_t offset, uint16_t value)
	{
		memcpy(buffer.data() + offset, &value, sizeof(value));
	}
}

VgmExporter::VgmExporter(string outputFile, Emulator* emu) : _stream(outputFile, ios::out | ios::binary)
{
	_outputFile = outputFile;
	_emu = emu;
	_lastEventTime = std::chrono::steady_clock::now();
	if(_stream) {
		WriteHeader();
	}
}

VgmExporter::~VgmExporter()
{
	if(_stream && _stream.is_open()) {
		FlushCommandBuffer();
		_stream.put((char)0x66); //VGM "end of sound data" command

		uint32_t gd3Offset = (uint32_t)_stream.tellp();
		WriteGd3Tag();
		PatchHeader(gd3Offset);

		_stream.close();
	}
}

void VgmExporter::AddSamples(uint32_t sampleCount, uint32_t sampleRate)
{
	if(sampleRate == 0) {
		return;
	}
	_sampleClock += (double)sampleCount * VgmSampleRate / sampleRate;
	_clockFed = true;
	FlushCommandBuffer();
}

void VgmExporter::FlushCommandBuffer()
{
	if(!_cmdBuffer.empty()) {
		_stream.write((char*)_cmdBuffer.data(), _cmdBuffer.size());
		_cmdBuffer.clear();
	}
}

void VgmExporter::LogWrite(VgmChip chip, uint8_t addrOrPort, uint8_t value)
{
	//Run-ahead frames replay emulated time that will run again for real -
	//logging their writes would duplicate every command (with zero-length
	//waits, since AddSamples already excludes these frames).
	if(_emu->IsRunAheadFrame()) {
		return;
	}
	_chipUsed[(int)chip] = true;
	EmitWait();
	WriteChipCommand(chip, addrOrPort, value);
}

void VgmExporter::WriteHeader()
{
	//Fixed-size header covering every field up to the v1.71 SCSP clock/extra
	//header offset fields; zero-filled first so every unused chip clock
	//(anything beyond the 4 consoles this writer targets) reads as "absent"
	//per spec, and VgmDataOffset (0x34) always resolves to HeaderSize since
	//the data block starts right where this buffer ends. The 4 supported
	//clocks written here are provisional NTSC values - PatchHeader rewrites
	//them at teardown (real console clock, or 0 for chips never written).
	vector<uint8_t> header(HeaderSize, 0);
	memcpy(header.data(), "Vgm ", 4);
	PutU32(header, 0x08, VgmVersion);
	PutU32(header, 0x0C, SmsPsgClockHz);
	PutU32(header, 0x10, SmsYm2413ClockHz);
	PutU32(header, 0x24, 60); //Rate (Hz), NTSC framerate reference only - the
									  //VGM command stream's own timebase is always a
									  //fixed 44100Hz regardless of this field
	PutU16(header, 0x28, 0x0009); //SN76489 feedback pattern (Sega PSG clone)
	header[0x2A] = 16; //SN76489 shift register width
	header[0x2B] = 0; //SN76489 flags - no quirks to signal
	PutU32(header, 0x34, HeaderSize - 0x34); //VGM data offset, relative to 0x34
	PutU32(header, 0x80, GameBoyClockHz);
	PutU32(header, 0x84, NesApuClockHz);

	_stream.write((char*)header.data(), header.size());
}

void VgmExporter::PatchHeader(uint32_t gd3Offset)
{
	uint32_t eofOffset = (uint32_t)_stream.tellp() - 0x04;
	uint32_t gd3RelativeOffset = gd3Offset - 0x14;
	uint32_t totalSamples = (uint32_t)_totalSamples;

	_stream.seekp(0x04);
	_stream.write((char*)&eofOffset, sizeof(eofOffset));

	_stream.seekp(0x14);
	_stream.write((char*)&gd3RelativeOffset, sizeof(gd3RelativeOffset));

	_stream.seekp(0x18);
	_stream.write((char*)&totalSamples, sizeof(totalSamples));

	//Final chip-clock values: a chip that received no commands gets clock 0
	//("absent" per spec - players won't allocate it, validators won't flag
	//it); a used chip gets the console's real clock when SetChipClock was
	//called (e.g. PAL SMS), else the NTSC fallback the header started with.
	auto patchClock = [this](uint32_t offset, VgmChip chip, uint32_t fallbackHz) {
		uint32_t clock = 0;
		if(_chipUsed[(int)chip]) {
			clock = _chipClock[(int)chip] ? _chipClock[(int)chip] : fallbackHz;
		}
		_stream.seekp(offset);
		_stream.write((char*)&clock, sizeof(clock));
	};
	patchClock(0x0C, VgmChip::SmsPsg, SmsPsgClockHz);
	patchClock(0x10, VgmChip::SmsYm2413, SmsYm2413ClockHz);
	patchClock(0x80, VgmChip::GameBoyDmg, GameBoyClockHz);
	patchClock(0x84, VgmChip::NesApu, NesApuClockHz);
	//The Game Gear stereo command (0x4F) belongs to the SN76489 stream - a
	//capture that only panned still needs the PSG clock present.
	if(_chipUsed[(int)VgmChip::SmsPsgStereo] && !_chipUsed[(int)VgmChip::SmsPsg]) {
		uint32_t clock = _chipClock[(int)VgmChip::SmsPsg] ? _chipClock[(int)VgmChip::SmsPsg] : SmsPsgClockHz;
		_stream.seekp(0x0C);
		_stream.write((char*)&clock, sizeof(clock));
	}
}

void VgmExporter::WriteGd3Tag()
{
	//GD3 tag block (https://vgmrips.net/wiki/GD3_Specification): a fixed
	//"Gd3 " magic + version, then 11 null-terminated UTF-16LE strings in a
	//fixed order. Most fields are left empty (unknown track/game/author
	//metadata for a live capture); only the system and creator/tool fields
	//are filled in.
	_stream.write("Gd3 ", 4);
	uint32_t version = 0x00000100;
	_stream.write((char*)&version, sizeof(version));

	uint32_t lengthPos = (uint32_t)_stream.tellp();
	uint32_t placeholderLength = 0;
	_stream.write((char*)&placeholderLength, sizeof(placeholderLength));

	uint32_t fieldsStart = (uint32_t)_stream.tellp();
	WriteUtf16String(_stream, ""); //Track name (EN)
	WriteUtf16String(_stream, ""); //Track name (JP)
	WriteUtf16String(_stream, ""); //Game name (EN)
	WriteUtf16String(_stream, ""); //Game name (JP)
	WriteUtf16String(_stream, "Mesen (Enhanced Audio)"); //System name (EN)
	WriteUtf16String(_stream, ""); //System name (JP)
	WriteUtf16String(_stream, ""); //Author name (EN)
	WriteUtf16String(_stream, ""); //Author name (JP)
	WriteUtf16String(_stream, ""); //Release date
	WriteUtf16String(_stream, "MesenCE VgmExporter"); //Creator/ripper tool
	WriteUtf16String(_stream, ""); //Notes

	uint32_t fieldsEnd = (uint32_t)_stream.tellp();
	uint32_t length = fieldsEnd - fieldsStart;

	_stream.seekp(lengthPos);
	_stream.write((char*)&length, sizeof(length));
	_stream.seekp(fieldsEnd);
}

void VgmExporter::WriteUtf16String(ofstream& stream, const string& value)
{
	for(char c : value) {
		uint16_t code = (uint16_t)(unsigned char)c;
		stream.write((char*)&code, sizeof(code));
	}
	uint16_t terminator = 0;
	stream.write((char*)&terminator, sizeof(terminator));
}

void VgmExporter::EmitWait()
{
	if(_clockFed) {
		//Emulated sample clock (ADR-0013): emit exactly the samples that have
		//elapsed on the 44100Hz counter and not yet been written as waits.
		//The fractional part stays in _sampleClock so rounding can't drift
		//the capture over a long session.
		uint64_t target = (uint64_t)_sampleClock;
		if(target > _emittedSamples) {
			EmitWaitSamples(target - _emittedSamples);
			_emittedSamples = target;
		}
	} else {
		//Real-time fallback - no flush has fed the sample clock yet (writes
		//arriving before the console's first PlayAudioBuffer of the capture).
		auto now = std::chrono::steady_clock::now();
		std::chrono::duration<double> elapsed = now - _lastEventTime;
		_lastEventTime = now;

		double exactSamples = elapsed.count() * VgmSampleRate + _pendingSampleFraction;
		uint64_t wholeSamples = (uint64_t)exactSamples;
		_pendingSampleFraction = exactSamples - (double)wholeSamples;

		EmitWaitSamples(wholeSamples);
		//Keep the emulated clock's baseline aligned with what was emitted, so
		//the switch to clock-fed waits doesn't double-count the ramp-up.
		_sampleClock += (double)wholeSamples;
		_emittedSamples += wholeSamples;
	}
}

void VgmExporter::EmitWaitSamples(uint64_t wholeSamples)
{
	while(wholeSamples > 0) {
		uint16_t chunk = (uint16_t)((wholeSamples > 0xFFFF) ? 0xFFFF : wholeSamples);
		_cmdBuffer.push_back(0x61);
		_cmdBuffer.push_back((uint8_t)chunk);
		_cmdBuffer.push_back((uint8_t)(chunk >> 8));
		wholeSamples -= chunk;
		_totalSamples += chunk;
	}
}

void VgmExporter::WriteChipCommand(VgmChip chip, uint8_t addrOrPort, uint8_t value)
{
	switch(chip) {
		case VgmChip::NesApu:
			_cmdBuffer.push_back(0xB4);
			_cmdBuffer.push_back(addrOrPort);
			_cmdBuffer.push_back(value);
			break;

		case VgmChip::GameBoyDmg:
			_cmdBuffer.push_back(0xB3);
			_cmdBuffer.push_back(addrOrPort);
			_cmdBuffer.push_back(value);
			break;

		case VgmChip::SmsPsg:
			_cmdBuffer.push_back(0x50);
			_cmdBuffer.push_back(value);
			break;

		case VgmChip::SmsPsgStereo:
			_cmdBuffer.push_back(0x4F);
			_cmdBuffer.push_back(value);
			break;

		case VgmChip::SmsYm2413:
			if(addrOrPort == 0) {
				//Register-select latch (port 0) - remember it, the combined
				//0x51 command is only emitted on the matching data write
				_pendingYm2413Register = value;
			} else {
				_cmdBuffer.push_back(0x51);
				_cmdBuffer.push_back(_pendingYm2413Register);
				_cmdBuffer.push_back(value);
			}
			break;
	}
}
