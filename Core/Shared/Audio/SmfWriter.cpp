#include "pch.h"
#include "Shared/Audio/SmfWriter.h"

namespace
{
	void PutBe16(ofstream& s, uint16_t v)
	{
		s.put((char)(v >> 8));
		s.put((char)v);
	}
	void PutBe32(ofstream& s, uint32_t v)
	{
		s.put((char)(v >> 24));
		s.put((char)(v >> 16));
		s.put((char)(v >> 8));
		s.put((char)v);
	}
}

SmfWriter::SmfWriter(uint32_t trackCount, uint16_t ticksPerQuarterNote)
{
	_ticksPerQuarterNote = ticksPerQuarterNote;
	_trackData.resize(trackCount);
	_trackLastTick.resize(trackCount, 0);
}

void SmfWriter::AppendDelta(uint32_t track)
{
	WriteVarLen(_trackData[track], _currentTick - _trackLastTick[track]);
	_trackLastTick[track] = _currentTick;
}

void SmfWriter::EmitEvent(uint32_t track, uint8_t status, uint8_t data1, int data2)
{
	AppendDelta(track);
	_trackData[track].push_back(status);
	_trackData[track].push_back(data1);
	if(data2 >= 0) {
		_trackData[track].push_back((uint8_t)data2);
	}
}

void SmfWriter::EmitMeta(uint32_t track, uint8_t type, const vector<uint8_t>& payload)
{
	AppendDelta(track);
	_trackData[track].push_back(0xFF);
	_trackData[track].push_back(type);
	WriteVarLen(_trackData[track], (uint32_t)payload.size());
	_trackData[track].insert(_trackData[track].end(), payload.begin(), payload.end());
}

bool SmfWriter::Write(ofstream& stream)
{
	if(!stream) {
		return false;
	}

	stream.write("MThd", 4);
	PutBe32(stream, 6);
	PutBe16(stream, 1); //SMF format 1: tempo/conductor track + parallel voice tracks
	PutBe16(stream, (uint16_t)_trackData.size());
	PutBe16(stream, _ticksPerQuarterNote);

	for(uint32_t t = 0; t < (uint32_t)_trackData.size(); t++) {
		WriteVarLen(_trackData[t], 0);
		_trackData[t].push_back(0xFF);
		_trackData[t].push_back(0x2F);
		_trackData[t].push_back(0x00); //End Of Track meta

		stream.write("MTrk", 4);
		PutBe32(stream, (uint32_t)_trackData[t].size());
		stream.write((char*)_trackData[t].data(), _trackData[t].size());
	}

	return (bool)stream;
}

void SmfWriter::WriteVarLen(vector<uint8_t>& buf, uint32_t value)
{
	uint8_t bytes[5] = { (uint8_t)(value & 0x7F) };
	int count = 1;
	while((value >>= 7) > 0) {
		bytes[count++] = (uint8_t)((value & 0x7F) | 0x80);
	}
	while(count > 0) {
		buf.push_back(bytes[--count]);
	}
}
