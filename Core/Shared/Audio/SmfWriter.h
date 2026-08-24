#pragma once
#include "pch.h"

//Standard MIDI File (SMF) byte-writer: multi-track event buffers with running
//delta-time encoding, and the final MThd/MTrk chunk serialization. Split out
//of MidiExporter (ADR-0034) so the note-segmentation state machine and the
//byte-level file format live in separate files.
//
//Tracks are in-memory vectors by design: SMF stores each track as a length-
//prefixed chunk whose event delta-times are back-patched as events arrive,
//so the track bodies can only be sized and written once the capture ends
//(ADR-0033 keeps this and validates the output stream up front instead).
class SmfWriter
{
private:
	uint16_t _ticksPerQuarterNote;
	uint32_t _currentTick = 0;
	vector<vector<uint8_t>> _trackData;
	vector<uint32_t> _trackLastTick;

	//Prefixes the next event with its variable-length delta-time: the gap
	//between the track's last event tick and the current tick.
	void AppendDelta(uint32_t track);

public:
	SmfWriter(uint32_t trackCount, uint16_t ticksPerQuarterNote);

	//Absolute tick used for the next emitted event's delta-time.
	void SetCurrentTick(uint32_t tick) { _currentTick = tick; }

	//Appends one channel-voice MIDI event (Note-On/Off = 0x9n/0x8n, Program
	//Change = 0xCn), preceded by its delta-time. "data2" is the event's 3rd
	//byte (velocity, or 0 for a Note-Off); left at -1 for the 2-byte Program
	//Change event, which has no 3rd byte.
	void EmitEvent(uint32_t track, uint8_t status, uint8_t data1, int data2 = -1);

	//Appends one meta event (FF <type> <varlen length> <payload>), preceded
	//by its delta-time.
	void EmitMeta(uint32_t track, uint8_t type, const vector<uint8_t>& payload);

	//Appends End-Of-Track to every track, then writes the MThd header and one
	//MTrk chunk per track. Returns false if the stream reports failure.
	bool Write(ofstream& stream);

	static void WriteVarLen(vector<uint8_t>& buf, uint32_t value);
};
