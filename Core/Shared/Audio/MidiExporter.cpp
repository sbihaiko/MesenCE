#include "pch.h"
#include "Shared/Audio/MidiExporter.h"
#include "Shared/MessageManager.h"

namespace
{
	//GM program per (preset, voice category) - Lead/Harmony/Bass/Fm columns
	constexpr uint8_t kPrograms[5][4] = {
		{ 80, 91, 38, 85 },
		{ 81, 92, 39, 86 },
		{ 82, 93, 33, 87 },
		{ 83, 94, 35, 88 },
		{ 84, 95, 36, 89 },
	};
}

MidiExporter::MidiExporter(string outputFile) :
	_outputFile(outputFile),
	_stream(outputFile, ios::out | ios::binary),
	_smf(kTrackCount, (uint16_t)kTicksPerQuarterNote)
{
}

MidiExporter::~MidiExporter()
{
	//An invalid-at-start exporter was already reported by StartMidiRecording
	//and never recorded anything - only a stream that opened fine and failed
	//later (e.g. disk full) needs a report here.
	if(_stream.is_open()) {
		FlushActiveVoices();
		if(!_smf.Write(_stream)) {
			MessageManager::DisplayMessage("MusicRecorder", "CouldNotWriteToFile", _outputFile);
		}
	}
}

void MidiExporter::LogFrame(const char* consoleTag, uint32_t presetId, const EnhancedSynthEngine::Input& in, uint32_t sampleCount, uint32_t sampleRate)
{
	EnsureProgramsSent(consoleTag, presetId);
	AdvanceTick(sampleCount, sampleRate);

	ProcessMelodicVoice(0, in.LeadFreq, in.LeadVol);
	ProcessMelodicVoice(1, in.HarmFreq, in.HarmVol);
	ProcessMelodicVoice(2, in.BassFreq, in.BassVol);
	for(uint32_t i = 0; i < in.FmVoiceCount && i < EnhancedSynthEngine::MaxFmVoices; i++) {
		ProcessMelodicVoice(3 + i, in.FmFreq[i], in.FmVol[i]);
	}
	ProcessDrumVoice(in);
}

void MidiExporter::AdvanceTick(uint32_t sampleCount, uint32_t sampleRate)
{
	//Emulated-time tick source (ADR-0013): the flush's own sample count is
	//the elapsed emulated time, so region/console cadence and host conditions
	//(fast-forward, pause, save-state load) can't distort note lengths.
	double seconds = sampleRate > 0 ? (double)sampleCount / sampleRate : 1.0 / kFlushRateHz;
	double exactTicks = seconds * (kTicksPerQuarterNote * kDefaultTempoBpm / 60.0) + _tickFraction;
	uint32_t wholeTicks = (uint32_t)exactTicks;
	_tickFraction = exactTicks - wholeTicks;
	_currentTick += wholeTicks;
	_smf.SetCurrentTick(_currentTick);
}

void MidiExporter::EnsureProgramsSent(const char* consoleTag, uint32_t presetId)
{
	if(_programsSent) {
		return;
	}
	_programsSent = true;
	uint32_t p = presetId < 5 ? presetId : 0;

	string name = string(consoleTag) + " preset " + std::to_string(p);
	_smf.EmitMeta(kTrackTempo, 0x03, vector<uint8_t>(name.begin(), name.end())); //Track/sequence name meta

	uint32_t usPerQuarter = (uint32_t)(60000000.0 / kDefaultTempoBpm);
	_smf.EmitMeta(kTrackTempo, 0x51, { (uint8_t)(usPerQuarter >> 16), (uint8_t)(usPerQuarter >> 8), (uint8_t)usPerQuarter }); //Tempo meta

	for(uint32_t i = 0; i < kNumMelodicVoices; i++) {
		uint32_t category = i < 3 ? i : 3; //0=Lead, 1=Harmony, 2=Bass, 3=Fm (shared by every FM voice)
		_smf.EmitEvent(kTrackMelodic, (uint8_t)(0xC0 | MelodicChannel(i)), kPrograms[p][category]);
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
			_smf.EmitEvent(kTrackMelodic, (uint8_t)(0x80 | channel), v.Note, 0);
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
		_smf.EmitEvent(kTrackMelodic, (uint8_t)(0x80 | channel), v.Note, 0);
	}
	v.Note = FreqToMidiNote(freq);
	v.HeldCents = cents;
	_smf.EmitEvent(kTrackMelodic, (uint8_t)(0x90 | channel), v.Note, VelocityFromVol(vol));
	v.Active = true;
}

void MidiExporter::ProcessDrumVoice(const EnhancedSynthEngine::Input& in)
{
	bool volAttack = in.NoiseVol > kOnsetVolThreshold && _drumLastVol <= kOnsetVolThreshold;
	bool volRelease = in.NoiseVol <= kOnsetVolThreshold && _drumLastVol > kOnsetVolThreshold;
	_drumLastVol = in.NoiseVol;

	if(volRelease && _drumActive) {
		_smf.EmitEvent(kTrackDrum, (uint8_t)(0x80 | kDrumChannel), _drumNote, 0);
		_drumActive = false;
	}
	if(volAttack) {
		_drumNote = in.NoiseBrightness >= 0.5 ? kDrumHiHatNote : kDrumTomNote;
		_smf.EmitEvent(kTrackDrum, (uint8_t)(0x90 | kDrumChannel), _drumNote, VelocityFromVol(in.NoiseVol));
		_drumActive = true;
	}
}

void MidiExporter::FlushActiveVoices()
{
	//Closes every voice still held before the End-Of-Track meta is written.
	for(uint32_t i = 0; i < kNumMelodicVoices; i++) {
		if(_voices[i].Active) {
			_smf.EmitEvent(kTrackMelodic, (uint8_t)(0x80 | MelodicChannel(i)), _voices[i].Note, 0);
			_voices[i].Active = false;
		}
	}
	if(_drumActive) {
		_smf.EmitEvent(kTrackDrum, (uint8_t)(0x80 | kDrumChannel), _drumNote, 0);
		_drumActive = false;
	}
}

uint8_t MidiExporter::FreqToMidiNote(double freqHz)
{
	double note = freqHz <= 0 ? 60.0 : 69.0 + 12.0 * std::log2(freqHz / 440.0);
	return (uint8_t)std::clamp((int)std::lround(note), 0, 127);
}

uint8_t MidiExporter::MelodicChannel(uint32_t voiceIndex)
{ return (uint8_t)(voiceIndex < kDrumChannel ? voiceIndex : voiceIndex + 1); }
uint8_t MidiExporter::VelocityFromVol(double vol)
{ return (uint8_t)std::clamp((int)std::lround(vol * 127.0), 1, 127); }
