#include "pch.h"
#include "Shared/Audio/MidiExporter.h"

safe_ptr<MidiExporter> MidiExporter::_instance;

namespace {
	void PutBe16(ofstream& s, uint16_t v) { s.put((char)(v >> 8)); s.put((char)v); }
	void PutBe32(ofstream& s, uint32_t v) { s.put((char)(v >> 24)); s.put((char)(v >> 16)); s.put((char)(v >> 8)); s.put((char)v); }

	//GM program per (preset, voice category) - Lead/Harmony/Bass/Fm columns
	constexpr uint8_t kPrograms[5][4] = {
		{ 80, 91, 38, 85 }, { 81, 92, 39, 86 }, { 82, 93, 33, 87 }, { 83, 94, 35, 88 }, { 84, 95, 36, 89 },
	};
}

MidiExporter::MidiExporter(string outputFile) : _outputFile(outputFile) {}
MidiExporter::~MidiExporter() { FlushActiveVoices(); WriteFile(); }

void MidiExporter::StartRecording(string outputFile) { _instance.reset(new MidiExporter(outputFile)); }
void MidiExporter::StopRecording() { _instance.reset(); }
bool MidiExporter::IsRecording() { return _instance != nullptr; }

void MidiExporter::LogFrame(const char* consoleTag, uint32_t presetId, const EnhancedSynthEngine::Input& in)
{
	shared_ptr<MidiExporter> instance = _instance.lock();
	if(!instance) {
		return;
	}

	instance->EnsureProgramsSent(consoleTag, presetId);

	//Nominal-cadence tick, not real elapsed time - see the header's timing model
	double exactTicks = (kTicksPerQuarterNote * kDefaultTempoBpm / 60.0) / kFlushRateHz + instance->_tickFraction;
	uint32_t wholeTicks = (uint32_t)exactTicks;
	instance->_tickFraction = exactTicks - wholeTicks;
	instance->_currentTick += wholeTicks;

	instance->ProcessMelodicVoice(0, in.LeadFreq, in.LeadVol);
	instance->ProcessMelodicVoice(1, in.HarmFreq, in.HarmVol);
	instance->ProcessMelodicVoice(2, in.BassFreq, in.BassVol);
	for(uint32_t i = 0; i < in.FmVoiceCount && i < EnhancedSynthEngine::MaxFmVoices; i++) {
		instance->ProcessMelodicVoice(3 + i, in.FmFreq[i], in.FmVol[i]);
	}
	instance->ProcessDrumVoice(in);
}

void MidiExporter::EnsureProgramsSent(const char* consoleTag, uint32_t presetId)
{
	if(_programsSent) {
		return;
	}
	_programsSent = true;
	uint32_t p = presetId < 5 ? presetId : 0;

	string name = string(consoleTag) + " preset " + std::to_string(p);
	AppendDelta(kTrackTempo);
	AppendBytes(kTrackTempo, { 0xFF, 0x03 }); //Track/sequence name meta
	WriteVarLen(_trackData[kTrackTempo], (uint32_t)name.size());
	for(char c : name) {
		_trackData[kTrackTempo].push_back((uint8_t)c);
	}

	uint32_t usPerQuarter = (uint32_t)(60000000.0 / kDefaultTempoBpm);
	AppendDelta(kTrackTempo);
	AppendBytes(kTrackTempo, { 0xFF, 0x51, 0x03, (uint8_t)(usPerQuarter >> 16), (uint8_t)(usPerQuarter >> 8), (uint8_t)usPerQuarter }); //Tempo meta

	for(uint32_t i = 0; i < kNumMelodicVoices; i++) {
		uint32_t category = i < 3 ? i : 3; //0=Lead, 1=Harmony, 2=Bass, 3=Fm (shared by every FM voice)
		EmitEvent(kTrackMelodic, (uint8_t)(0xC0 | MelodicChannel(i)), kPrograms[p][category]);
	}
}

void MidiExporter::ProcessMelodicVoice(uint32_t voiceIndex, double freq, double vol)
{
	VoiceState& v = _voices[voiceIndex];
	uint8_t channel = MelodicChannel(voiceIndex);
	bool volRelease = vol <= kOnsetVolThreshold && v.LastVol > kOnsetVolThreshold;
	v.LastVol = vol;

	if(volRelease) {
		if(v.Active) {
			EmitEvent(kTrackMelodic, (uint8_t)(0x80 | channel), v.Note, 0);
			v.Active = false;
		}
		return;
	}
	if(vol <= kOnsetVolThreshold) {
		return;
	}

	//New note: attack-from-silence, or a pitch jump past the header's
	//hysteresis threshold while already active - both close any old note first.
	double cents = 1200.0 * std::log2(std::max(freq, 1.0) / 440.0);
	if(v.Active && std::abs(cents - v.HeldCents) <= kPitchJumpCents + kPitchJumpHysteresisCents) {
		return;
	}
	if(v.Active) {
		EmitEvent(kTrackMelodic, (uint8_t)(0x80 | channel), v.Note, 0);
	}
	v.Note = FreqToMidiNote(freq);
	v.HeldCents = cents;
	EmitEvent(kTrackMelodic, (uint8_t)(0x90 | channel), v.Note, VelocityFromVol(vol));
	v.Active = true;
}

void MidiExporter::ProcessDrumVoice(const EnhancedSynthEngine::Input& in)
{
	bool volAttack = in.NoiseVol > kOnsetVolThreshold && _drumLastVol <= kOnsetVolThreshold;
	bool volRelease = in.NoiseVol <= kOnsetVolThreshold && _drumLastVol > kOnsetVolThreshold;
	_drumLastVol = in.NoiseVol;

	if(volRelease && _drumActive) {
		EmitEvent(kTrackDrum, (uint8_t)(0x80 | kDrumChannel), _drumNote, 0);
		_drumActive = false;
	}
	if(volAttack) {
		_drumNote = in.NoiseBrightness >= 0.5 ? kDrumHiHatNote : kDrumTomNote;
		EmitEvent(kTrackDrum, (uint8_t)(0x90 | kDrumChannel), _drumNote, VelocityFromVol(in.NoiseVol));
		_drumActive = true;
	}
}

void MidiExporter::AppendDelta(uint32_t track)
{
	WriteVarLen(_trackData[track], _currentTick - _trackLastTick[track]);
	_trackLastTick[track] = _currentTick;
}

void MidiExporter::AppendBytes(uint32_t track, std::initializer_list<uint8_t> bytes) { for(uint8_t b : bytes) { _trackData[track].push_back(b); } }

void MidiExporter::EmitEvent(uint32_t track, uint8_t status, uint8_t data1, int data2)
{
	AppendDelta(track);
	_trackData[track].push_back(status);
	_trackData[track].push_back(data1);
	if(data2 >= 0) {
		_trackData[track].push_back((uint8_t)data2);
	}
}

void MidiExporter::FlushActiveVoices()
{
	//Closes every voice still held before WriteFile() writes End-Of-Track.
	for(uint32_t i = 0; i < kNumMelodicVoices; i++) {
		if(_voices[i].Active) {
			EmitEvent(kTrackMelodic, (uint8_t)(0x80 | MelodicChannel(i)), _voices[i].Note, 0);
			_voices[i].Active = false;
		}
	}
	if(_drumActive) {
		EmitEvent(kTrackDrum, (uint8_t)(0x80 | kDrumChannel), _drumNote, 0);
		_drumActive = false;
	}
}

void MidiExporter::WriteFile()
{
	ofstream stream(_outputFile, ios::out | ios::binary);
	if(!stream) {
		return;
	}

	stream.write("MThd", 4);
	PutBe32(stream, 6);
	PutBe16(stream, 1); //SMF format 1: tempo/conductor track + parallel voice tracks
	PutBe16(stream, (uint16_t)kTrackCount);
	PutBe16(stream, (uint16_t)kTicksPerQuarterNote);

	for(uint32_t t = 0; t < kTrackCount; t++) {
		WriteVarLen(_trackData[t], 0);
		AppendBytes(t, { 0xFF, 0x2F, 0x00 }); //End Of Track meta - safe: FlushActiveVoices() already ran

		stream.write("MTrk", 4);
		PutBe32(stream, (uint32_t)_trackData[t].size());
		stream.write((char*)_trackData[t].data(), _trackData[t].size());
	}
}

void MidiExporter::WriteVarLen(vector<uint8_t>& buf, uint32_t value)
{
	uint8_t bytes[4] = { (uint8_t)(value & 0x7F) };
	int count = 1;
	while((value >>= 7) > 0) {
		bytes[count++] = (uint8_t)((value & 0x7F) | 0x80);
	}
	while(count > 0) {
		buf.push_back(bytes[--count]);
	}
}

uint8_t MidiExporter::FreqToMidiNote(double freqHz)
{
	double note = freqHz <= 0 ? 60.0 : 69.0 + 12.0 * std::log2(freqHz / 440.0);
	return (uint8_t)std::clamp((int)std::lround(note), 0, 127);
}

uint8_t MidiExporter::MelodicChannel(uint32_t voiceIndex) { return (uint8_t)(voiceIndex < kDrumChannel ? voiceIndex : voiceIndex + 1); }
uint8_t MidiExporter::VelocityFromVol(double vol) { return (uint8_t)std::clamp((int)std::lround(vol * 127.0), 1, 127); }
