#include "pch.h"
#include "NES/HdPacks/NesAudioFingerprint.h"
#include "NES/HdPacks/HdData.h"
#include "NES/HdPacks/HdAudioDevice.h"
#include "NES/EnhancedSynth.h"
#include "NES/NesConsole.h"
#include "NES/NesSoundMixer.h"
#include "Shared/Audio/ReplacementMuteMask.h"
#include "Shared/MessageManager.h"
#include "Utilities/FolderUtilities.h"

namespace
{
	int8_t FreqToNote(double freq)
	{
		if(freq <= 0) {
			return NoteFrame::Rest;
		}
		double n = 69.0 + 12.0 * std::log2(freq / 440.0);
		int note = (int)std::lround(n);
		if(note < 0 || note > 127) {
			return NoteFrame::Rest;
		}
		return (int8_t)note;
	}

	double EnvVolume(const ApuEnvelopeState& env)
	{
		return (env.ConstantVolume ? env.Volume : env.Counter) / 15.0;
	}
}

NoteFrame NesAudioFingerprint::FromApu(const ApuState& apu)
{
	NoteFrame f;
	if(apu.Square1.Enabled && apu.Square1.LengthCounter.Counter > 0 && apu.Square1.Period >= 8 && EnvVolume(apu.Square1.Envelope) > 0.001) {
		f.Note[0] = FreqToNote(apu.Square1.Frequency);
	}
	if(apu.Square2.Enabled && apu.Square2.LengthCounter.Counter > 0 && apu.Square2.Period >= 8 && EnvVolume(apu.Square2.Envelope) > 0.001) {
		f.Note[1] = FreqToNote(apu.Square2.Frequency);
	}
	if(apu.Triangle.Enabled && apu.Triangle.LengthCounter.Counter > 0 && apu.Triangle.LinearCounter > 0 && apu.Triangle.Period >= 2) {
		f.Note[2] = FreqToNote(apu.Triangle.Frequency);
	}
	if(apu.Noise.Enabled && apu.Noise.LengthCounter.Counter > 0 && EnvVolume(apu.Noise.Envelope) > 0.001) {
		//GM percussion: bright/fast LFSR = closed hi-hat, slow = low tom
		f.Note[3] = apu.Noise.Frequency / 200000.0 >= 0.5 ? 42 : 45;
	}
	return f;
}

NesAudioBootstrap::~NesAudioBootstrap()
{
	uint32_t written = _segmenter.Save(_audioFolder);
	{
		ofstream stats(FolderUtilities::CombinePath(_audioFolder, ".recorder"), std::ios::out | std::ios::binary);
		stats << "frames=" << _frames << "\naudible=" << _audible << "\nsegments=" << _segmenter.GetSegments().size() << "\nwritten=" << written << "\n";
	}
	MessageManager::Log("[MEP] bootstrap: audio recorder saw " + std::to_string(_frames) + " frames (" + std::to_string(_audible) + " audible), " + std::to_string(_segmenter.GetSegments().size()) + " segment(s)");
	if(written > 0) {
		MessageManager::Log("[MEP] bootstrap: " + std::to_string(written) + " audio track(s) written to '" + _audioFolder + "' (fingerprints.json + midi/); run scripts/mep_render_audio.py to render bgm/*.ogg");
	}
}

uint32_t NesAudioReplacer::Load(const vector<string>& audioLayers, HdPackData& hdData)
{
	//Later layers (human) override earlier ones (auto) by id
	vector<AudioFingerprint> merged;
	unordered_map<string, string> oggById;
	for(const string& layer : audioLayers) {
		vector<AudioFingerprint> tracks;
		string error;
		string jsonPath = FolderUtilities::CombinePath(layer, "fingerprints.json");
		if(!ifstream(jsonPath)) {
			continue;
		}
		if(!FingerprintStore::Load(jsonPath, tracks, error)) {
			MessageManager::Log("[MEP] audio: " + error);
			continue;
		}
		for(AudioFingerprint& t : tracks) {
			bool replaced = false;
			for(AudioFingerprint& m : merged) {
				if(m.Id == t.Id) {
					m = t;
					replaced = true;
					break;
				}
			}
			if(!replaced) {
				merged.push_back(t);
			}
		}
		//OGG files: any layer may provide the audio for any id; later wins
		for(const AudioFingerprint& t : merged) {
			string ogg = FolderUtilities::CombinePath(FolderUtilities::CombinePath(layer, t.Kind), t.Id + ".ogg");
			if(ifstream(ogg)) {
				oggById[t.Id] = ogg;
			}
		}
	}

	_matcher.SetTracks(merged);
	_trackIds.assign(merged.size(), -1);
	uint32_t playable = 0;
	for(size_t i = 0; i < merged.size(); i++) {
		auto it = oggById.find(merged[i].Id);
		if(it == oggById.end() || merged[i].Kind != "bgm") {
			continue;
		}
		int id = TrackIdBase + (int)i;
		BgmTrackInfo info;
		info.Filename = it->second;
		//F5.4g Block C item 8 (ADR-0134 Option A): the track's optional loop
		//point (PCM samples at the OGG's rate) from fingerprints.json; 0 loops
		//the whole file (OggReader clamps an out-of-range value back to 0).
		info.LoopPosition = merged[i].Loop;
		hdData.BgmFilesById[id] = info;
		_trackIds[i] = id;
		playable++;
	}
	if(!merged.empty()) {
		MessageManager::Log("[MEP] audio: " + std::to_string(merged.size()) + " fingerprint(s) loaded, " + std::to_string(playable) + " with an OGG to play");
	}
	return playable;
}

void NesAudioReplacer::OnFrame(const ApuState& apu)
{
	HdAudioDevice* device = _console->GetHdAudioDevice();
	if(device && !device->IsPackAudioEnabled()) {
		//Pack audio turned off (Tools > Enhancement Packs > Audio (OGG)): the
		//device stops its OGG; give the APU back and forget the match
		if(_matcher.GetPlaying() >= 0) {
			_console->GetSoundMixer()->SetReplacementMuteMask(0);
			_lastMuteMask = 0;
			_matcher.SetPlaying(-1);
			MessageManager::Log("[MEP] audio: pack audio disabled - APU restored");
		}
		return;
	}
	int result = _matcher.Feed(NesAudioFingerprint::FromApu(apu));
	if(result == -1) {
		return;
	}
	if(result == -2) {
		if(device) {
			device->StopReplacementBgm();
		}
		_console->GetSoundMixer()->SetReplacementMuteMask(0);
		_lastMuteMask = 0;
		MessageManager::Log("[MEP] audio: music stopped - APU restored");
		return;
	}
	const AudioFingerprint& track = _matcher.GetTracks()[result];
	if(_trackIds[result] < 0 || !device) {
		MessageManager::Log("[MEP] audio: fingerprint match '" + track.Id + "' at frame " + std::to_string(_matcher.GetFrame()) + " (no OGG - nothing played)");
		_matcher.SetPlaying(-1);
		return;
	}
	if(device->PlayReplacementBgm(_trackIds[result], true)) {
		//F5.4g Block C item 9 (ADR-0133): the APU is not muted wholesale - the
		//mask lets SFX-flagged melodic channels pass dry while the OGG replaces
		//the music. Falls back to 0x0F (full tonal mute) when classification is
		//unavailable, matching pre-Block-C output exactly.
		UpdateReplacementMuteMask();
		char maskHex[8];
		snprintf(maskHex, sizeof(maskHex), "%02X", _lastMuteMask);
		MessageManager::Log("[MEP] audio: fingerprint match '" + track.Id + "' at frame " + std::to_string(_matcher.GetFrame()) + " - playing replacement, APU muted (mask 0x" + maskHex + ")");
	} else {
		_matcher.SetPlaying(-1);
	}
}

//F5.4g Block C item 9 (ADR-0133): compute the per-channel replacement mute
//mask from the ChannelRoleClassifier. Default 0x0F mutes Square1..Noise
//(today's behaviour); a melodic channel flagged SFX (stable, hysteresis-held
//by the classifier) has its bit cleared so it passes dry. DMC and expansion
//channels have no bit and always play. Degraded modes leave 0x0F untouched:
//with EnhancedAudio or SFX separation off the classifier never flags anything,
//and before warm-up no channel is SFX yet - never "unmute all", which would
//double the music. Pushed only when the mask changes (ADR-0133 point 3).
void NesAudioReplacer::UpdateReplacementMuteMask()
{
	EnhancedSynth* synth = _console->GetEnhancedSynth();
	uint8_t mask = ReplacementMuteMask::Compute(synth ? &synth->GetClassifier() : nullptr);
	if(mask != _lastMuteMask) {
		_lastMuteMask = mask;
		_console->GetSoundMixer()->SetReplacementMuteMask(mask);
	}
}
