#include "pch.h"
#include "Shared/Audio/EnhancedSynthEngine.h"
#include "Shared/MessageManager.h"
#include "Utilities/FolderUtilities.h"

//TinySoundFont (MIT, Utilities/Audio/tsf.h) - the single implementation unit
#define TSF_IMPLEMENTATION
#define TSF_NO_STDIO
#include "Utilities/Audio/tsf.h"

EnhancedSynthEngine::~EnhancedSynthEngine()
{
	if(_sf) {
		tsf_close(_sf);
		_sf = nullptr;
	}
}

int EnhancedSynthEngine::SfChannelVoices(int channel) const
{
	if(!_sf) {
		return 0;
	}
	int n = 0;
	for(int i = 0; i < _sf->voiceNum; i++) {
		if(_sf->voices[i].playingPreset != -1 && _sf->voices[i].playingChannel == channel) {
			n++;
		}
	}
	return n;
}

int EnhancedSynthEngine::SfPresetIndex(int channel) const
{
	return _sf ? tsf_channel_get_preset_index(_sf, channel) : -1;
}

double EnhancedSynthEngine::SfChannelGainDb(int channel) const
{
	if(!_sf || !_sf->channels || channel >= _sf->channels->channelNum) {
		return 0;
	}
	return _sf->channels->channels[channel].gainDB;
}

int EnhancedSynthEngine::SfVoiceCount() const
{
	return _sf ? tsf_active_voice_count(_sf) : 0;
}

bool EnhancedSynthEngine::LoadSoundFont(const string& path)
{
	if(_sf && path == _sfPath) {
		return true;
	}
	if(_sf) {
		tsf_close(_sf);
		_sf = nullptr;
	}
	_sfPath = path;
	_sfRate = 0;
	for(SfNote& n : _sfNotes) {
		n = {};
	}
	for(uint32_t ch = 0; ch < 3; ch++) {
		for(SfNote& n : _sfChordNotes[ch]) {
			n = {};
		}
	}
	for(SfDrumHit& hit : _sfDrums) {
		hit = {};
	}
	for(int& prog : _sfPrograms) {
		prog = -1;
	}
	if(path.empty()) {
		return false;
	}

	//Read the whole file ourselves (TSF_NO_STDIO) so the path handling
	//matches the rest of the emulator; a SoundFont is a few MB to ~200 MB.
	std::ifstream file(path, std::ios::binary);
	if(!file) {
		MessageManager::Log("[EnhancedAudio] SoundFont not found: " + path);
		return false;
	}
	std::vector<char> data((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
	if(data.empty()) {
		MessageManager::Log("[EnhancedAudio] SoundFont is empty: " + path);
		return false;
	}
	_sf = tsf_load_memory(data.data(), (int)data.size());
	if(!_sf) {
		MessageManager::Log("[EnhancedAudio] SoundFont could not be parsed (not an .sf2?): " + path);
		return false;
	}
	//Headroom over the ~10 melodic voices in flight: percussion hits are held
	//for kSfDrumHoldS before their note-off, and TSF can only recycle voices
	//that are already in release
	tsf_set_max_voices(_sf, 96);
	MessageManager::Log("[EnhancedAudio] SoundFont loaded: " + path + " (" + std::to_string(tsf_get_presetcount(_sf)) + " presets)");
	return true;
}

string EnhancedSynthEngine::ResolveSoundFontPath(const char* configuredPath)
{
	if(configuredPath && configuredPath[0]) {
		return configuredPath;
	}
	string def = FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), "EnhancedAudio.sf2");
	return std::ifstream(def) ? def : "";
}

uint32_t EnhancedSynthEngine::FoldArpeggioToChord(const int* cycleKeys, uint32_t cycleCount, double outFreq[MaxChordNotes])
{
	//Convert the arpeggio's distinct notes (MIDI keys, e.g. from
	//ChannelRoleClassifier::ArpeggioKeys) into the frequencies of a sustained
	//chord, sorted ascending so the stack is voiced root-up.
	uint32_t count = std::min(cycleCount, (uint32_t)MaxChordNotes);
	for(uint32_t i = 0; i < count; i++) {
		outFreq[i] = 440.0 * std::pow(2.0, (cycleKeys[i] - 69.0) / 12.0);
	}
	//insertion sort (tiny, and the cycle notes are distinct)
	for(uint32_t i = 1; i < count; i++) {
		double f = outFreq[i];
		uint32_t j = i;
		while(j > 0 && outFreq[j - 1] > f) {
			outFreq[j] = outFreq[j - 1];
			j--;
		}
		outFreq[j] = f;
	}
	return count;
}

EnhancedSynthEngine::ExpressionEnvelope EnhancedSynthEngine::EvaluateExpression(double decayRate, double vibratoDepth, double portamentoRate)
{
	ExpressionEnvelope env;
	env.DecayRate = decayRate;
	env.VibratoDepth = vibratoDepth;
	env.PortamentoRate = portamentoRate;
	//A note that falls fast after its onset and barely oscillates is
	//percussive (pluck); a pitch that oscillates while held or slides between
	//notes reads as a bowed/pad instrument (strings); otherwise the tone
	//sustains as-is. Calibration constants - see the classifier's decay/
	//vibrato/portamento getters for the units.
	if(decayRate >= 1.5 && vibratoDepth < 1.0) {
		env.Family = ExpressionEnvelope::FamilyPluck;
	} else if(vibratoDepth >= 1.0 || portamentoRate >= 3.0) {
		env.Family = ExpressionEnvelope::FamilyStrings;
	} else {
		env.Family = ExpressionEnvelope::FamilySustained;
	}
	return env;
}

void EnhancedSynthEngine::Route(Input& in, ChannelRoleClassifier& roles, const RawChannel* raw, uint32_t count, double dt)
{
	ChannelRoleClassifier::Channel ch[ChannelRoleClassifier::MaxChannels];
	count = std::min(count, ChannelRoleClassifier::MaxChannels);
	for(uint32_t i = 0; i < count; i++) {
		ch[i].Freq = raw[i].Freq;
		ch[i].Vol = raw[i].Vol;
		ch[i].HwSweep = raw[i].HwSweep;
	}
	roles.Update(ch, dt);

	in.LeadVol = in.HarmVol = in.BassVol = 0;
	in.SfxCount = 0;
	in.LeadChordCount = in.HarmChordCount = in.BassChordCount = 0;
	in.Family[0] = in.Family[1] = in.Family[2] = ExpressionEnvelope::FamilySustained;
	in.FamilyLocked[0] = in.FamilyLocked[1] = in.FamilyLocked[2] = false;
	bool slotUsed[3] = {};
	for(uint32_t i = 0; i < count; i++) {
		if(raw[i].Vol <= 0.0 && !roles.IsSfx(i)) {
			//silent channel: keep its frequency in its slot only if the
			//slot stays free, so a released note does not zero the pitch
			//while the voice's release tail is still fading
			int slot = (int)roles.Role(i);
			if(!slotUsed[slot]) {
				if(slot == 0) {
					in.LeadFreq = raw[i].Freq;
					in.LeadWidth = raw[i].Width;
				} else if(slot == 1) {
					in.HarmFreq = raw[i].Freq;
					in.HarmWidth = raw[i].Width;
				} else {
					in.BassFreq = raw[i].Freq;
				}
			}
			continue;
		}
		if(roles.IsSfx(i)) {
			if(in.SfxCount < MaxSfxVoices) {
				Input::SfxVoice& v = in.Sfx[in.SfxCount++];
				v.Freq = raw[i].Freq;
				v.Vol = raw[i].Vol;
				v.Width = raw[i].Width;
			}
			continue;
		}
		int slot = (int)roles.Role(i);
		if(slotUsed[slot]) {
			//two channels with the same role (only with >3 melodic channels):
			//the extra one takes the first free slot
			slot = !slotUsed[1] ? 1 : !slotUsed[0] ? 0 :
				!slotUsed[2]								? 2 :
																  -1;
			if(slot < 0) {
				continue;
			}
		}
		slotUsed[slot] = true;
		if(slot == 0) {
			in.LeadFreq = raw[i].Freq;
			in.LeadVol = raw[i].Vol;
			in.LeadWidth = raw[i].Width;
		} else if(slot == 1) {
			in.HarmFreq = raw[i].Freq;
			in.HarmVol = raw[i].Vol;
			in.HarmWidth = raw[i].Width;
		} else {
			in.BassFreq = raw[i].Freq;
			in.BassVol = raw[i].Vol;
		}
		//F5.4g Bloco B: expression family (item 4) and arpeggio fold (item 3)
		//for this slot's channel - the family drives the patch choice, a fast
		//arpeggio becomes a sustained chord.
		ExpressionEnvelope env = EvaluateExpression(roles.DecayRate(i), roles.VibratoDepth(i), roles.PortamentoRate(i));
		in.Family[slot] = env.Family;
		in.FamilyLocked[slot] = roles.HasFixedRole(i);
		int arp[4];
		uint32_t arpCount = roles.ArpeggioKeys(i, arp);
		if(arpCount >= 2) {
			double chord[MaxChordNotes];
			arpCount = FoldArpeggioToChord(arp, arpCount, chord);
			if(slot == 0) {
				in.LeadChordCount = arpCount;
				for(uint32_t k = 0; k < arpCount; k++) in.LeadChord[k] = chord[k];
			} else if(slot == 1) {
				in.HarmChordCount = arpCount;
				for(uint32_t k = 0; k < arpCount; k++) in.HarmChord[k] = chord[k];
			} else {
				in.BassChordCount = arpCount;
				for(uint32_t k = 0; k < arpCount; k++) in.BassChord[k] = chord[k];
			}
		}
	}
}

void EnhancedSynthEngine::SfAgeDrums(double dt)
{
	for(SfDrumHit& hit : _sfDrums) {
		if(hit.Key < 0) {
			continue;
		}
		hit.LeftS -= dt;
		if(hit.LeftS <= 0) {
			tsf_channel_note_off(_sf, 9, hit.Key);
			hit.Key = -1;
		}
	}
}

void EnhancedSynthEngine::SfTriggerDrum(int key, double vel, double gain)
{
	//Re-hitting the same drum, a free slot, or (last resort) the oldest hit
	SfDrumHit* slot = nullptr;
	for(SfDrumHit& hit : _sfDrums) {
		if(hit.Key == key) {
			slot = &hit;
			break;
		}
		if(!slot && hit.Key < 0) {
			slot = &hit;
		}
	}
	if(!slot) {
		slot = &_sfDrums[0];
		for(SfDrumHit& hit : _sfDrums) {
			if(hit.LeftS < slot->LeftS) {
				slot = &hit;
			}
		}
	}
	if(slot->Key >= 0) {
		tsf_channel_note_off(_sf, 9, slot->Key);
	}
	tsf_channel_set_volume(_sf, 9, (float)std::clamp(gain, 0.0, 2.0));
	tsf_channel_note_on(_sf, 9, key, (float)std::clamp(vel, 0.2, 1.0));
	slot->Key = key;
	slot->LeftS = kSfDrumHoldS;
}

void EnhancedSynthEngine::SfUpdateVoice(int channel, SfNote& note, double freq, double vol, double gain)
{
	double n = freq > 1.0 ? 69.0 + 12.0 * std::log2(freq / 440.0) : -1.0;
	if(vol <= 0.001 || n < 0.0 || n > 127.0) {
		if(note.Key >= 0) {
			tsf_channel_note_off(_sf, channel, note.Key);
			note.Key = -1;
		}
		return;
	}
	int key = (int)std::lround(n);
	if(note.Key < 0 || std::abs(n - note.Key) > 0.6) {
		//New note (attack out of silence, or a pitch move too large for a
		//bend - same rule as MidiExporter's onset detection)
		if(note.Key >= 0) {
			tsf_channel_note_off(_sf, channel, note.Key);
		}
		note.Key = key;
		note.OnVol = std::max(vol, 0.05);
		tsf_channel_set_volume(_sf, channel, (float)std::clamp(gain, 0.0, 2.0));
		tsf_channel_set_pitchwheel(_sf, channel, 8192);
		if(!tsf_channel_note_on(_sf, channel, key, (float)std::clamp(std::sqrt(vol), 0.1, 1.0))) {
			_sfNoteOnFails++;
		}
		_sfNoteOns++;
	}
	//Pitch inside the note follows the chip exactly (vibrato, small slides)
	//through the wheel, range +/-24 semitones set at load time
	double bend = (n - note.Key) / 24.0;
	tsf_channel_set_pitchwheel(_sf, channel, (int)std::clamp(8192.0 + bend * 8192.0, 0.0, 16383.0));
	//Envelope shape (decays, tremolo) follows the chip through the channel
	//volume relative to the level the note was struck at
	double chVol = std::clamp(gain * vol / note.OnVol, 0.0, 2.0);
	if(channel >= 0 && channel < 3) {
		_sfChannelVol[channel] = chVol;
	}
	tsf_channel_set_volume(_sf, channel, (float)chVol);
}

//F5.4g Bloco B item 3 (ADR-0052): the SoundFont side of arpeggio folding -
//holds up to count simultaneous notes on one channel as the sustained chord.
//Each note is struck at its fixed key; per-channel pitch bend is NOT applied
//while the chord is held (the chip's current pitch is the arpeggio's active
//note, which would detune the stack). Notes that leave the chord are released
//so the stack cannot leak voices.
void EnhancedSynthEngine::SfUpdateChord(int channel, SfNote* notes, uint32_t count, const double* freqs, double vol, double gain)
{
	if(vol <= 0.001) {
		for(uint32_t k = 0; k < MaxChordNotes; k++) {
			if(notes[k].Key >= 0) {
				tsf_channel_note_off(_sf, channel, notes[k].Key);
				notes[k].Key = -1;
			}
		}
		if(channel >= 0 && channel < 3) {
			_sfChannelVol[channel] = 0;
		}
		return;
	}
	uint32_t noteCount = std::min(count, (uint32_t)MaxChordNotes);
	for(uint32_t k = 0; k < MaxChordNotes; k++) {
		int key = -1;
		if(k < noteCount) {
			double n = freqs[k] > 1.0 ? 69.0 + 12.0 * std::log2(freqs[k] / 440.0) : -1.0;
			if(n >= 0.0 && n <= 127.0) {
				key = (int)std::lround(n);
			}
		}
		if(key >= 0) {
			if(notes[k].Key != key) {
				if(notes[k].Key >= 0) {
					tsf_channel_note_off(_sf, channel, notes[k].Key);
				}
				notes[k].Key = key;
				notes[k].OnVol = std::max(vol, 0.05);
				tsf_channel_set_volume(_sf, channel, (float)std::clamp(gain, 0.0, 2.0));
				if(!tsf_channel_note_on(_sf, channel, key, (float)std::clamp(std::sqrt(vol), 0.1, 1.0))) {
					_sfNoteOnFails++;
				}
				_sfNoteOns++;
			}
		} else if(notes[k].Key >= 0) {
			tsf_channel_note_off(_sf, channel, notes[k].Key);
			notes[k].Key = -1;
		}
	}
	if(channel >= 0 && channel < 3) {
		_sfChannelVol[channel] = std::clamp(gain, 0.0, 2.0);
	}
}

void EnhancedSynthEngine::InitPresets(const EnhancedSynthPreset builtInPresets[5], const char* sectionSuffix, const vector<string>& packPresetPaths)
{
	_builtInPresets = builtInPresets;
	_sectionSuffix = sectionSuffix;
	_packPresetPaths = packPresetPaths;
	ReloadUserPresets();
}

void EnhancedSynthEngine::ReloadUserPresets()
{
	EnhancedSynthPresetLoader::Load(_userPresets, _builtInPresets, _sectionSuffix, _packPresetPaths);
}

const EnhancedSynthPreset& EnhancedSynthEngine::GetPreset(uint32_t presetId) const
{
	return _userPresets[presetId < 5 ? presetId : 0];
}

void EnhancedSynthEngine::Reset()
{
	std::fill(_echoBuf.begin(), _echoBuf.end(), 0.0f);
	std::fill(_revBufL.begin(), _revBufL.end(), 0.0f);
	std::fill(_revBufR.begin(), _revBufR.end(), 0.0f);
	_lead = {};
	_harmony = {};
	_bass = {};
	for(Voice& v : _leadChord) {
		v = {};
	}
	for(Voice& v : _harmChord) {
		v = {};
	}
	for(Voice& v : _bassChord) {
		v = {};
	}
	for(Voice& v : _fmVoices) {
		v = {};
	}
	_fmLp = 0;
	for(Voice& v : _sfx) {
		v = {};
	}
	if(_sf) {
		tsf_reset(_sf);
		for(SfNote& n : _sfNotes) {
			n = {};
		}
		for(uint32_t ch = 0; ch < 3; ch++) {
			for(SfNote& n : _sfChordNotes[ch]) {
				n = {};
			}
		}
		_sfRate = 0;
	}
	_noiseVol = 0;
	_drumLpLow = _drumLpHigh = _drumLpTop = 0;
	_thumpGate = 0;
	_thumpPhase = 0;
	_lastNoisePollVol = 0;
	_compEnv = 0;
}

double EnhancedSynthEngine::PolyBlep(double t, double dt)
{
	//Removes most of the aliasing from naive saw/pulse edges
	if(t < dt) {
		t /= dt;
		return t + t - t * t - 1.0;
	} else if(t > 1.0 - dt) {
		t = (t - 1.0) / dt;
		return t * t + t + t + 1.0;
	}
	return 0.0;
}

double EnhancedSynthEngine::BlepSaw(double phase, double inc)
{
	return (2.0 * phase - 1.0) - PolyBlep(phase, inc);
}

void EnhancedSynthEngine::Retrigger(Voice& voice, double vol)
{
	//Reset oscillator phases only on an attack out of silence - the voice is
	//near-silent there, so the reset is inaudible. Legato pitch changes keep
	//the phase continuous: resetting mid-note produces a waveform
	//discontinuity (a click per note), which on fast melodic lines turns
	//into rhythmic crackle.
	bool volAttack = vol > 0.001 && voice.LastVol <= 0.001;
	if(volAttack) {
		voice.Phase = 0;
		voice.PhaseB = 0;
		voice.SubPhase = 0;
	}
	voice.LastVol = vol;
}

double EnhancedSynthEngine::NextNoise()
{
	//xorshift32, mapped to -1..1
	_noiseRng ^= _noiseRng << 13;
	_noiseRng ^= _noiseRng >> 17;
	_noiseRng ^= _noiseRng << 5;
	return (int32_t)_noiseRng / 2147483648.0;
}

void EnhancedSynthEngine::Render(int16_t* out, uint32_t sampleCount, uint32_t sampleRate, const Input& in, const EnhancedSynthPreset& p, double volumePct)
{
	constexpr double pi2 = 2.0 * 3.14159265358979;

	Retrigger(_lead, in.LeadVol);
	Retrigger(_harmony, in.HarmVol);
	Retrigger(_bass, in.BassVol);
	//F5.4g Bloco B item 3: retrigger the folded-chord oscillators once per
	//flush (same attack-out-of-silence rule as the single voices)
	for(uint32_t c = 0; c < MaxChordNotes; c++) {
		Retrigger(_leadChord[c], in.LeadVol);
		Retrigger(_harmChord[c], in.HarmVol);
		Retrigger(_bassChord[c], in.BassVol);
	}

	//A low thump is triggered only on attacks (volume rising into a slow+loud
	//noise), so sustained noise (wind, engines) does not turn into a hum - the
	//thump then decays on its own. The wrapper decides what "slow enough"
	//means for its chip (ThumpEligible).
	double prevNoisePollVol = _lastNoisePollVol;
	if(in.ThumpEligible && in.NoiseVol >= 0.65 && in.NoiseVol > prevNoisePollVol + 0.08) {
		_thumpGate = 1.0;
		_thumpPhase = 0;
	}
	_lastNoisePollVol = in.NoiseVol;
	//Time constants are clamped so a user-edited preset (EnhancedAudioPresets.cfg)
	//can't produce division by zero or denormal-slow smoothing
	double thumpDecay = std::exp(-1.0 / (sampleRate * std::max(0.005, p.ThumpDecayS)));

	//Separate attack/release smoothing (orchestral preset uses slow attacks)
	double attackCoeff = 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.AttackMs) / 1000.0));
	double releaseCoeff = 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.ReleaseMs) / 1000.0));
	//F5.4g Bloco B item 4: the expression family shapes each music slot's
	//envelope - pluck = fast attack and release (percussive), strings = slower
	//attack (soft onset); sustained keeps the preset's smoothing.
	auto familySmoothing = [&](uint32_t family, double& attack, double& release) {
		if(family == ExpressionEnvelope::FamilyPluck) {
			attack = 1.0 - std::exp(-1.0 / (sampleRate * 0.002));
			release = 1.0 - std::exp(-1.0 / (sampleRate * 0.03));
		} else if(family == ExpressionEnvelope::FamilyStrings) {
			attack = 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.AttackMs * 2.5) / 1000.0));
			release = releaseCoeff;
		}
	};
	double leadAttack = attackCoeff, leadRelease = releaseCoeff;
	double harmAttack = attackCoeff, harmRelease = releaseCoeff;
	double bassAttack = attackCoeff, bassRelease = releaseCoeff;
	familySmoothing(in.Family[0], leadAttack, leadRelease);
	familySmoothing(in.Family[1], harmAttack, harmRelease);
	familySmoothing(in.Family[2], bassAttack, bassRelease);
	double masterGain = (volumePct / 100.0) * 5000.0;

	double leadInc = in.LeadFreq / sampleRate;
	double harmInc = in.HarmFreq / sampleRate;
	double bassInc = in.BassFreq / sampleRate;
	double leadLpCoeff = 1.0 - std::exp(-pi2 * p.LeadLpHz / sampleRate);
	double harmLpCoeff = 1.0 - std::exp(-pi2 * p.HarmLpHz / sampleRate);
	double bassLpCoeff = 1.0 - std::exp(-pi2 * p.BassLpHz / sampleRate);
	double drumLowCoeff = 1.0 - std::exp(-pi2 * p.DrumBodyLoHz / sampleRate);
	double drumHighCoeff = 1.0 - std::exp(-pi2 * p.DrumBodyHiHz / sampleRate);
	double drumTopCoeff = 1.0 - std::exp(-pi2 * p.DrumTopHz / sampleRate);
	double thumpInc = p.ThumpFreqHz / sampleRate;

	//FM bus: one plain saw oscillator per active FM melodic channel, summed
	//and post-filtered as a single bus (no per-voice detune/filter - with up
	//to 9 notes at once, that would just be muddy CPU cost). Reuses the lead
	//voice's lowpass tuning rather than adding FM-only preset fields.
	uint32_t fmVoiceCount = std::min(in.FmVoiceCount, MaxFmVoices);
	double fmInc[MaxFmVoices];
	for(uint32_t ch = 0; ch < fmVoiceCount; ch++) {
		Retrigger(_fmVoices[ch], in.FmVol[ch]);
		fmInc[ch] = in.FmFreq[ch] / sampleRate;
	}
	double fmLpCoeff = 1.0 - std::exp(-pi2 * p.LeadLpHz / sampleRate);
	constexpr double kFmVoiceGain = 0.6;

	//Dry SFX voices: fast envelopes so hits stay percussive
	uint32_t sfxCount = std::min(in.SfxCount, MaxSfxVoices);
	double sfxInc[MaxSfxVoices];
	for(uint32_t ch = 0; ch < sfxCount; ch++) {
		Retrigger(_sfx[ch], in.Sfx[ch].Vol);
		sfxInc[ch] = in.Sfx[ch].Freq / sampleRate;
	}
	double sfxAttackCoeff = 1.0 - std::exp(-1.0 / (sampleRate * 0.0005));
	double sfxReleaseCoeff = 1.0 - std::exp(-1.0 / (sampleRate * 0.002));

	//SoundFont block: drive the GM channels from the slot state, render the
	//flush into _sfBuf; the DSP music voices are skipped below when it ran
	bool useSf = _sf != nullptr;
	bool sfDrums = useSf && p.GmDrums;
	constexpr double kSfGain = 1.6;
	if(useSf) {
		if(_sfRate != sampleRate) {
			tsf_set_output(_sf, TSF_STEREO_INTERLEAVED, (int)sampleRate, 0.0f);
			_sfRate = sampleRate;
			for(int ch = 0; ch < 3; ch++) {
				tsf_channel_set_pitchrange(_sf, ch, 24.0f);
			}
			tsf_channel_set_pan(_sf, 0, 0.5f);
			tsf_channel_set_pan(_sf, 1, 0.38f);
			tsf_channel_set_pan(_sf, 2, 0.5f);
			tsf_channel_set_pan(_sf, 9, 0.5f);
			tsf_channel_set_presetnumber(_sf, 9, 0, 1);
		}
		int programs[3] = { (int)p.GmLeadProgram, (int)p.GmHarmProgram, (int)p.GmBassProgram };
		//F5.4g Bloco B item 4: the expression family replaces the preset's GM
		//program for a slot when it is confidently pluck/strings (sustained
		//keeps the preset choice; a FixedRole channel is exempt - item 6's
		//human override always wins).
		for(int ch = 0; ch < 3; ch++) {
			if(!in.FamilyLocked[ch] && in.Family[ch] != ExpressionEnvelope::FamilySustained) {
				int fp = kFamilyPrograms[in.Family[ch]][ch];
				if(fp >= 0) {
					programs[ch] = fp;
				}
			}
		}
		for(int ch = 0; ch < 3; ch++) {
			if(_sfPrograms[ch] != programs[ch]) {
				if(_sfNotes[ch].Key >= 0) {
					tsf_channel_note_off(_sf, ch, _sfNotes[ch].Key);
					_sfNotes[ch].Key = -1;
				}
				if(!tsf_channel_set_presetnumber(_sf, ch, std::clamp(programs[ch], 0, 127), 0)) {
					tsf_channel_set_presetindex(_sf, ch, 0);
				}
				_sfPrograms[ch] = programs[ch];
			}
		}
		//F5.4g Bloco B item 3: a folded chord on the slot sends a held note
		//stack to the SoundFont; a plain note uses the single-voice path.
		//Switching paths releases the other side's held notes so no voice
		//leaks across a fold/unfold transition.
		auto sfSlot = [&](int channel, SfNote& single, SfNote* chordNotes, uint32_t chordCount, const double* chordFreqs, double freq, double vol, double gain) {
			if(chordCount >= 2) {
				if(single.Key >= 0) {
					tsf_channel_note_off(_sf, channel, single.Key);
					single.Key = -1;
				}
				SfUpdateChord(channel, chordNotes, chordCount, chordFreqs, vol, gain);
			} else {
				for(uint32_t c = 0; c < MaxChordNotes; c++) {
					if(chordNotes[c].Key >= 0) {
						tsf_channel_note_off(_sf, channel, chordNotes[c].Key);
						chordNotes[c].Key = -1;
					}
				}
				SfUpdateVoice(channel, single, freq, vol, gain);
			}
		};
		sfSlot(0, _sfNotes[0], _sfChordNotes[0], in.LeadChordCount, in.LeadChord, in.LeadFreq, in.LeadVol, p.LeadGain);
		sfSlot(1, _sfNotes[1], _sfChordNotes[1], in.HarmChordCount, in.HarmChord, in.HarmFreq, in.HarmVol, p.HarmGain);
		sfSlot(2, _sfNotes[2], _sfChordNotes[2], in.BassChordCount, in.BassChord, in.BassFreq, in.BassVol, p.BassGain);
		SfAgeDrums((double)sampleCount / sampleRate);
		if(sfDrums) {
			//One percussion hit per noise attack: bright LFSR = closed hi-hat,
			//slow + loud = kick, slow = low tom (same mapping as MidiExporter)
			if(in.NoiseVol >= 0.2 && in.NoiseVol > prevNoisePollVol + 0.08) {
				int key = in.NoiseBrightness >= 0.5 ? 42 : (in.ThumpEligible && in.NoiseVol >= 0.65 ? 36 : 45);
				SfTriggerDrum(key, in.NoiseVol, p.DrumGain);
			}
		}
		if(_sfBuf.size() < sampleCount * 2) {
			_sfBuf.resize(sampleCount * 2);
		}
		tsf_render_float(_sf, _sfBuf.data(), (int)sampleCount, 0);
		_sfLastPeak = 0;
		for(uint32_t i = 0; i < sampleCount * 2; i++) {
			_sfLastPeak = std::max(_sfLastPeak, (double)std::abs(_sfBuf[i]));
		}
	}

	//Delay lines: lead echo + 83/127/173ms feedforward reverb taps
	uint32_t echoSize = (uint32_t)_echoBuf.size();
	uint32_t revSize = (uint32_t)_revBufL.size();
	uint32_t echoDelay = std::clamp((uint32_t)(p.EchoDelayS * sampleRate), 1u, echoSize - 1);
	uint32_t revTap1 = std::min(revSize - 1, (uint32_t)(0.083 * sampleRate));
	uint32_t revTap2 = std::min(revSize - 1, (uint32_t)(0.127 * sampleRate));
	uint32_t revTap3 = std::min(revSize - 1, (uint32_t)(0.173 * sampleRate));

	auto step = [](double& phase, double inc) {
		phase += inc;
		if(phase >= 1.0) {
			phase -= 1.0;
		}
		return phase;
	};
	//Pulse with variable width out of two anti-aliased saws (saw(t) - saw(t+width))
	auto pulse = [&](double phase, double inc, double width) {
		double shifted = phase + width;
		if(shifted >= 1.0) {
			shifted -= 1.0;
		}
		return BlepSaw(phase, inc) - BlepSaw(shifted, inc);
	};
	auto softClip = [](double x) {
		return x / (1.0 + std::abs(x) * 0.35);
	};
	auto smooth = [&](double& state, double target) {
		state += (target - state) * (target > state ? attackCoeff : releaseCoeff);
	};
	//F5.4g Bloco B item 4: per-slot smoothing so the expression family can
	//shape each music voice's envelope independently of the preset's global
	//attack/release (pluck snaps, strings bloom)
	auto smoothTo = [](double& state, double target, double attack, double release) {
		state += (target - state) * (target > state ? attack : release);
	};

	//Master bus soft-compressor (Studio preset): approximates an offline
	//normalize+tanh master. CompThreshold <= 0 disables it (the other presets
	//ship with it at 0, so this costs them nothing extra). The ratio is
	//clamped to >= 1 so a user-edited Ratio=0 can't divide by zero.
	bool compEnabled = p.CompThreshold > 0;
	double compRatio = std::max(1.0, p.CompRatio);
	double compAttackCoeff = compEnabled ? 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.CompAttackMs) / 1000.0)) : 0;
	double compReleaseCoeff = compEnabled ? 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.CompReleaseMs) / 1000.0)) : 0;

	for(uint32_t i = 0; i < sampleCount; i++) {
		smoothTo(_lead.SmoothedVol, in.LeadVol, leadAttack, leadRelease);
		smoothTo(_harmony.SmoothedVol, in.HarmVol, harmAttack, harmRelease);
		smoothTo(_bass.SmoothedVol, in.BassVol, bassAttack, bassRelease);
		smooth(_noiseVol, in.NoiseVol);
		_thumpGate *= thumpDecay;

		double lead = 0, harm = 0, bass = 0;
		double sfL = 0, sfR = 0;
		if(useSf) {
			sfL = _sfBuf[i * 2] * kSfGain;
			sfR = _sfBuf[i * 2 + 1] * kSfGain;
		} else {
			//Lead: detuned pulse pair + octave-up saw shimmer, or (Studio) a fixed
			//detuned-saw stack that ignores the pulse width entirely. A folded
			//arpeggio chord (F5.4g Bloco B item 3) stacks a detuned pulse pair
			//per chord note instead.
			if(in.LeadChordCount >= 2) {
				lead = 0;
				for(uint32_t c = 0; c < in.LeadChordCount && c < MaxChordNotes; c++) {
					double cInc = in.LeadChord[c] / sampleRate;
					lead += 0.45 * pulse(step(_leadChord[c].Phase, cInc * (1.0 + p.LeadDetune)), cInc * (1.0 + p.LeadDetune), in.LeadWidth)
						+ 0.45 * pulse(step(_leadChord[c].PhaseB, cInc * (1.0 - p.LeadDetune)), cInc * (1.0 - p.LeadDetune), in.LeadWidth);
				}
				lead *= 0.55; //stacked notes sum louder; scale back
			} else if(p.LeadAlwaysSaw) {
				lead = 0.55 * BlepSaw(step(_lead.Phase, leadInc * (1.0 + p.LeadDetune)), leadInc * (1.0 + p.LeadDetune)) + 0.55 * BlepSaw(step(_lead.PhaseB, leadInc * (1.0 - p.LeadDetune)), leadInc * (1.0 - p.LeadDetune)) + p.LeadOctaveUpMix * BlepSaw(step(_lead.SubPhase, leadInc * 2.0), leadInc * 2.0);
			} else {
				lead = 0.45 * pulse(step(_lead.Phase, leadInc * (1.0 + p.LeadDetune)), leadInc * (1.0 + p.LeadDetune), in.LeadWidth) + 0.45 * pulse(step(_lead.PhaseB, leadInc * (1.0 - p.LeadDetune)), leadInc * (1.0 - p.LeadDetune), in.LeadWidth) + p.LeadOctaveUpMix * BlepSaw(step(_lead.SubPhase, leadInc * 2.0), leadInc * 2.0);
			}
			lead = softClip(lead * p.LeadDrive);
			_lead.Lp += (lead - _lead.Lp) * leadLpCoeff;
			lead = _lead.Lp * _lead.SmoothedVol;

			//Harmony: softer detuned pulse pair (a folded chord stacks one per
			//note - F5.4g Bloco B item 3)
			if(in.HarmChordCount >= 2) {
				harm = 0;
				for(uint32_t c = 0; c < in.HarmChordCount && c < MaxChordNotes; c++) {
					double cInc = in.HarmChord[c] / sampleRate;
					harm += 0.45 * pulse(step(_harmChord[c].Phase, cInc * (1.0 + p.HarmDetune)), cInc * (1.0 + p.HarmDetune), in.HarmWidth)
						+ 0.45 * pulse(step(_harmChord[c].PhaseB, cInc * (1.0 - p.HarmDetune)), cInc * (1.0 - p.HarmDetune), in.HarmWidth);
				}
				harm *= 0.55;
			} else {
				harm = 0.45 * pulse(step(_harmony.Phase, harmInc * (1.0 + p.HarmDetune)), harmInc * (1.0 + p.HarmDetune), in.HarmWidth) + 0.45 * pulse(step(_harmony.PhaseB, harmInc * (1.0 - p.HarmDetune)), harmInc * (1.0 - p.HarmDetune), in.HarmWidth);
			}
			_harmony.Lp += (harm - _harmony.Lp) * harmLpCoeff;
			harm = _harmony.Lp * _harmony.SmoothedVol;

			//Bass: sine + saw + half-frequency sub sine, mildly driven. A folded
			//chord stacks the sine (the saw/sub of a chord stack is muddy).
			if(in.BassChordCount >= 2) {
				bass = 0;
				for(uint32_t c = 0; c < in.BassChordCount && c < MaxChordNotes; c++) {
					double cInc = in.BassChord[c] / sampleRate;
					step(_bassChord[c].Phase, cInc);
					bass += p.BassSine * std::sin(pi2 * _bassChord[c].Phase);
				}
				bass *= 0.7;
			} else {
				step(_bass.Phase, bassInc);
				step(_bass.SubPhase, bassInc * 0.5);
				bass = p.BassSine * std::sin(pi2 * _bass.Phase) + p.BassSaw * BlepSaw(step(_bass.PhaseB, bassInc), bassInc) + p.BassSub * std::sin(pi2 * _bass.SubPhase);
			}
			bass = softClip(bass * p.BassDrive);
			_bass.Lp += (bass - _bass.Lp) * bassLpCoeff;
			bass = _bass.Lp * _bass.SmoothedVol;
		}

		//Drums: bandpassed body vs highpassed top blended by LFSR rate + thump
		//(skipped when the SoundFont's percussion kit plays them)
		double n = NextNoise();
		_drumLpLow += (n - _drumLpLow) * drumLowCoeff;
		_drumLpHigh += (n - _drumLpHigh) * drumHighCoeff;
		_drumLpTop += (n - _drumLpTop) * drumTopCoeff;
		double body = (_drumLpHigh - _drumLpLow) * p.DrumBodyGain;
		double top = n - _drumLpTop;
		step(_thumpPhase, thumpInc);
		double drum = sfDrums ? 0.0 : (in.NoiseBrightness * top + (1.0 - in.NoiseBrightness) * body) * _noiseVol + p.ThumpGain * std::sin(pi2 * _thumpPhase) * _thumpGate * _noiseVol;

		//Dry SFX: plain pulses at the chip's duty, no filter, no sends
		double sfx = 0;
		for(uint32_t ch = 0; ch < sfxCount; ch++) {
			Voice& v = _sfx[ch];
			double target = in.Sfx[ch].Vol;
			v.SmoothedVol += (target - v.SmoothedVol) * (target > v.SmoothedVol ? sfxAttackCoeff : sfxReleaseCoeff);
			if(v.SmoothedVol > 0.0005) {
				sfx += 0.5 * pulse(step(v.Phase, sfxInc[ch]), sfxInc[ch], in.Sfx[ch].Width) * v.SmoothedVol;
			}
		}
		sfx *= p.LeadGain;

		//FM bus (skipped entirely on consoles with no FM voices)
		double fmBus = 0;
		if(fmVoiceCount > 0) {
			for(uint32_t ch = 0; ch < fmVoiceCount; ch++) {
				Voice& v = _fmVoices[ch];
				smooth(v.SmoothedVol, in.FmVol[ch]);
				if(v.SmoothedVol > 0.0005) {
					fmBus += BlepSaw(step(v.Phase, fmInc[ch]), fmInc[ch]) * v.SmoothedVol;
				}
			}
			fmBus = softClip(fmBus * p.LeadDrive * kFmVoiceGain);
			_fmLp += (fmBus - _fmLp) * fmLpCoeff;
			fmBus = _fmLp;
		}

		//Lead echo (single tap)
		uint32_t echoRead = (_echoPos + echoSize - echoDelay) % echoSize;
		double echo = _echoBuf[echoRead];
		_echoBuf[_echoPos] = (float)(useSf ? 0.5 * (sfL + sfR) * 0.6 : lead);
		_echoPos = (_echoPos + 1) % echoSize;

		//Stereo image: harmony left, lead echo right, FM centered
		double left = p.LeadGain * lead + p.EchoGainL * echo + 1.25 * p.HarmGain * harm + p.BassGain * bass + p.DrumGain * drum + p.LeadGain * fmBus + sfL;
		double right = p.LeadGain * lead + p.EchoGainR * echo + 0.80 * p.HarmGain * harm + p.BassGain * bass + p.DrumGain * drum + p.LeadGain * fmBus + sfR;

		//Light feedforward reverb (3 taps)
		_revBufL[_revPos] = (float)left;
		_revBufR[_revPos] = (float)right;
		uint32_t t1 = (_revPos + revSize - revTap1) % revSize;
		uint32_t t2 = (_revPos + revSize - revTap2) % revSize;
		uint32_t t3 = (_revPos + revSize - revTap3) % revSize;
		left += p.ReverbWet * (0.35 * _revBufL[t1] + 0.28 * _revBufL[t2] + 0.22 * _revBufL[t3]);
		right += p.ReverbWet * (0.35 * _revBufR[t1] + 0.28 * _revBufR[t2] + 0.22 * _revBufR[t3]);
		_revPos = (_revPos + 1) % revSize;

		//SFX join after the sends: dry, centered
		left += sfx;
		right += sfx;

		if(compEnabled) {
			//Feedforward soft-knee compressor: linked stereo (one envelope
			//detects the louder of the two channels), gentle ratio + makeup
			//gain standing in for an offline normalize+tanh master.
			double peak = std::max(std::abs(left), std::abs(right));
			_compEnv += (peak - _compEnv) * (peak > _compEnv ? compAttackCoeff : compReleaseCoeff);
			double gain = p.CompMakeup;
			if(_compEnv > p.CompThreshold) {
				double compressed = p.CompThreshold + (_compEnv - p.CompThreshold) / compRatio;
				gain *= compressed / _compEnv;
			}
			left *= gain;
			right *= gain;
		}

		int32_t outL = (int32_t)out[i * 2] + (int32_t)(softClip(left) * masterGain);
		int32_t outR = (int32_t)out[i * 2 + 1] + (int32_t)(softClip(right) * masterGain);
		out[i * 2] = (int16_t)std::clamp(outL, -32768, 32767);
		out[i * 2 + 1] = (int16_t)std::clamp(outR, -32768, 32767);
	}
}
