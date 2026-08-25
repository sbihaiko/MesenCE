#include "pch.h"
#include "NES/HdPacks/NesAudioFingerprint.h"
#include "NES/HdPacks/HdData.h"
#include "NES/HdPacks/HdAudioDevice.h"
#include "NES/NesConsole.h"
#include "NES/NesSoundMixer.h"
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
		info.LoopPosition = 0;
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
	int result = _matcher.Feed(NesAudioFingerprint::FromApu(apu));
	if(result == -1) {
		return;
	}
	HdAudioDevice* device = _console->GetHdAudioDevice();
	if(result == -2) {
		if(device) {
			device->StopReplacementBgm();
		}
		_console->GetSoundMixer()->SetReplacementMute(false);
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
		_console->GetSoundMixer()->SetReplacementMute(true);
		MessageManager::Log("[MEP] audio: fingerprint match '" + track.Id + "' at frame " + std::to_string(_matcher.GetFrame()) + " - playing replacement, APU muted");
	} else {
		_matcher.SetPlaying(-1);
	}
}
