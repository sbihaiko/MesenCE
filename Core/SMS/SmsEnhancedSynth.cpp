#include "pch.h"
#include "SMS/SmsEnhancedSynth.h"
#include "SMS/SmsConsole.h"
#include "SMS/SmsPsg.h"
#include "SMS/SmsFmAudio.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Audio/SoundMixer.h"
#include "Shared/Audio/MidiExporter.h"

//Built-in instrument presets. Order must match the EnhancedAudioPreset enum
//on the UI side (Synthwave = 0, ChipDeluxe = 1, OrchestralLite = 2, Dry = 3,
//Studio = 4). Values start as a copy of the NES engine's tuning
//(Core/NES/EnhancedSynth.cpp) - the SN76489's plain 50%-duty square/noise
//character differs enough from the 2A03 that these will likely need ear
//tuning once heard in-game; until then they're a reasonable starting point
//since the DSP itself is shared (EnhancedSynthEngine).
static constexpr EnhancedSynthPreset _presets[5] = {
	//Synthwave: detuned pulse-width leads, saw+sub bass, tight drums
	{
		0.004, 0.002, false, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.16,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Chip deluxe: stays close to the PSG character - pure-ish pulses,
	//round bass, crisp drums, just a touch of space
	{
		0.0015, 0.001, false, 0.5, false, 0.10, 8000, 6000, 1.1,
		0.9, 0.1, 0.2, 1200, 1.0,
		1800, 7500, 7000, 1.0, 0.35, 0.045, 165,
		2, 3,
		0.12, 0.25, 0.35, 0.08,
		1.0, 0.6, 0.8, 0.85,
		0, 0, 0, 0, 0
	},
	//Orchestral lite: slow-attack string-like leads, low string bass,
	//timpani-weight drums, larger room
	{
		0.007, 0.005, false, 0.5, false, 0.35, 3800, 2600, 1.0,
		0.5, 0.6, 0.25, 700, 1.2,
		900, 4500, 6000, 1.0, 0.7, 0.12, 110,
		35, 80,
		0.30, 0.30, 0.45, 0.30,
		0.95, 0.65, 0.9, 0.6,
		0, 0, 0, 0, 0
	},
	//Dry: Synthwave voices with no echo/reverb tail - SFX stay tight
	{
		0.004, 0.002, false, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		3, 4,
		0.05, 0.0, 0.0, 0.0,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Studio: fixed detuned-saw stack lead (the SN76489 has no duty register to
	//ignore, but the always-saw lead still gives it a fuller, less "chip"
	//character), same tuned pan/bass/drum balance as Synthwave, plus a gentle
	//bus compressor.
	{
		0.003, 0.002, false, 0.5, true, 0.25, 5200, 3200, 1.4,
		0.70, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.18,
		1.0, 0.56, 0.85, 0.75,
		0.55, 3.0, 8, 140, 1.18
	},
};

SmsEnhancedSynth::SmsEnhancedSynth(Emulator* emu, SmsConsole* console)
{
	_emu = emu;
	_console = console;
	//This engine reads EnhancedAudioPresets.cfg sections suffixed ".Sms"
	//(e.g. "[Studio.Sms]") so its tuning can live in the same file as the NES
	//engine's ("[Studio]") without colliding.
	_engine.InitPresets(_presets, ".Sms");
	_emu->GetSoundMixer()->RegisterAudioProvider(this);
}

SmsEnhancedSynth::~SmsEnhancedSynth()
{
	_emu->GetSoundMixer()->UnregisterAudioProvider(this);
}

void SmsEnhancedSynth::MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate)
{
	//Enhanced audio settings are shared across every console (AudioConfig),
	//not SMS-specific - see Core/NES/EnhancedSynth.cpp for the NES equivalent.
	AudioConfig& cfg = _emu->GetSettings()->GetAudioConfig();
	if(!cfg.EnableEnhancedAudio || _emu->IsRunAheadFrame() || sampleRate == 0) {
		if(_wasActive && !cfg.EnableEnhancedAudio) {
			//Clear delay lines and voice state, otherwise re-enabling the synth
			//would replay stale audio frozen in the buffers. State-only (no
			//preset file re-read) - this runs inside the mix path.
			_engine.Reset();
			_wasActive = false;
		}
		return;
	}
	_wasActive = true;

	const EnhancedSynthPreset& p = _engine.GetPreset(cfg.EnhancedAudioPreset);

	//The synth state is polled once per audio flush (~5.6ms / ~179Hz), same
	//cadence as the NES engine.
	SmsPsgState& psg = _console->GetPsg()->GetState();
	uint32_t masterClockRate = _console->GetMasterClockRate();

	//SN76489 tone period is a 10-bit reload value; the chip toggles the
	//channel's output once per reload-countdown at clock/16, so a full period
	//is 2 reload-countdowns (matches SmsPsg::Run()'s _masterClock += 16 and
	//Tone[i].Output ^= 1 on timer underflow).
	auto toneFreq = [masterClockRate](uint16_t reload) {
		return masterClockRate / 16.0 / (2.0 * std::max<uint16_t>(reload, 1));
	};
	//4-bit attenuation, 0 = loudest, 15 = silent (no envelope/length-counter
	//concept on this chip, unlike the 2A03 - the volume register is the
	//volume).
	auto toneVol = [](uint8_t attenuation) {
		return (15 - attenuation) / 15.0;
	};

	EnhancedSynthEngine::Input in;

	//Games that switch to the YM2413 mute the PSG through the audio control
	//port ($F2) - when they do, don't re-interpret the (now-silent) PSG
	//registers either, or stale notes/noise would play under the FM voices.
	bool psgMuted = _console->IsPsgAudioMuted();
	if(!psgMuted) {
		//Per-channel volume settings (Settings > SMS/ColecoVision > Audio)
		//apply to the synth voices too, so muting a chip channel also mutes
		//its enhanced voice - same indexing as SmsPsg::Run()
		uint32_t* chVol = _console->GetModel() == SmsModel::ColecoVision
			? _emu->GetSettings()->GetCvConfig().ChannelVolumes
			: _emu->GetSettings()->GetSmsConfig().ChannelVolumes;
		in.LeadFreq = toneFreq(psg.Tone[0].ReloadValue);
		in.LeadVol = toneVol(psg.Tone[0].Volume) * chVol[0] / 100.0;
		in.HarmFreq = toneFreq(psg.Tone[1].ReloadValue);
		in.HarmVol = toneVol(psg.Tone[1].Volume) * chVol[1] / 100.0;
		in.BassFreq = toneFreq(psg.Tone[2].ReloadValue);
		in.BassVol = toneVol(psg.Tone[2].Volume) * chVol[2] / 100.0;
		in.NoiseVol = toneVol(psg.Noise.Volume) * chVol[3] / 100.0;
	}

	//The SN76489 has no duty register - the lead/harmony pulse width is
	//always the preset's FixedWidth (or ignored entirely when LeadAlwaysSaw).
	in.LeadWidth = p.FixedWidth;
	in.HarmWidth = p.FixedWidth;

	//Map the noise LFSR shift rate (same reload-based clocking as the tone
	//channels; mode 3 reuses Tone[2]'s reload) to drum timbre: fast = bright
	//hi-hat top, slow = snare/tom body; only a slow rate qualifies as a
	//kick/tom attack for the engine's low thump. The normalizer/ceiling below
	//are first-pass constants sized to this chip's much narrower rate range
	//than the NES's noise channel; expect to retune by ear.
	uint16_t noiseReload;
	switch(psg.Noise.Control & 0x03) {
		case 0: noiseReload = 0x10; break;
		case 1: noiseReload = 0x20; break;
		case 2: noiseReload = 0x40; break;
		default: noiseReload = psg.Tone[2].ReloadValue; break;
	}
	double noiseFreq = toneFreq(noiseReload);
	in.NoiseBrightness = std::min(1.0, noiseFreq / 8000.0);
	in.ThumpEligible = noiseFreq <= 4000.0;

	//YM2413 (SmsFmAudio) melodic channels 0-8: read the raw register file the
	//same way psg.GetState() is read above. Registers stay all-zero (and thus
	//every keyOn bit stays 0) on any game that never touches the FM add-on, so
	//no extra "is FM in use" gate is needed - this is safe to always poll.
	//$10-$18: F-Number low 8 bits per channel. $20-$28: bit0 = F-Number bit 8,
	//bits1-3 = octave (block), bit4 = key-on. $30-$38: bits4-7 = instrument
	//(unused here), bits0-3 = 4-bit attenuation (0 = loudest, 15 = silent,
	//same convention as the PSG). $0E bit5 = rhythm mode, which repurposes
	//channels 6-8 (BD/SD/TOM/CYM/HH) - those 3 channels are kept out of the
	//melodic bus (they'd be misread as notes) and mapped onto the engine's
	//drum path instead, below.
	uint8_t fmRegs[0x40];
	_console->GetFmAudio()->GetRegisters(fmRegs);
	bool fmRhythmMode = (fmRegs[0x0E] & 0x20) != 0;
	//The FM add-on's volume setting (Settings > SMS > Audio) applies to the
	//synth's FM voices too, like the PSG channel volumes above
	double fmVolume = _emu->GetSettings()->GetSmsConfig().FmAudioVolume / 100.0;
	in.FmVoiceCount = 9;
	for(uint32_t ch = 0; ch < 9; ch++) {
		uint8_t keyBlock = fmRegs[0x20 + ch];
		bool keyOn = !(fmRhythmMode && ch >= 6) && ((keyBlock >> 4) & 0x01) != 0;
		uint16_t fnum = fmRegs[0x10 + ch] | ((keyBlock & 0x01) << 8);
		uint8_t block = (keyBlock >> 1) & 0x07;
		in.FmFreq[ch] = fnum * (double)masterClockRate / (72.0 * (double)(1u << (19 - block)));
		uint8_t attenuation = fmRegs[0x30 + ch] & 0x0F;
		in.FmVol[ch] = keyOn ? (15 - attenuation) / 15.0 * fmVolume : 0.0;
	}

	//Rhythm mode: 5 percussion instruments keyed by $0E bits 0-4 (bit4 = BD,
	//bit3 = SD, bit2 = TOM, bit1 = CYM, bit0 = HH), leveled by the nibbles of
	//$36-$38 ($36 low = BD, $37 high/low = HH/SD, $38 high/low = TOM/CYM).
	//Rather than emulating the OPLL percussion, map it onto the engine's
	//existing drum path the same way the PSG noise channel is: dark hits
	//(BD/TOM) drive the noise "body", bright ones (SD/CYM/HH) the "top", and
	//a keyed bass drum qualifies for the attack-triggered low thump. The drum
	//bus is single, so when both the PSG noise and FM rhythm are active the
	//louder source wins.
	if(fmRhythmMode) {
		auto rhythmVol = [fmVolume](bool keyed, uint8_t attenuation) {
			return keyed ? (15 - (attenuation & 0x0F)) / 15.0 * fmVolume : 0.0;
		};
		uint8_t keys = fmRegs[0x0E];
		double bd = rhythmVol(keys & 0x10, fmRegs[0x36]);
		double sd = rhythmVol(keys & 0x08, fmRegs[0x37]);
		double tom = rhythmVol(keys & 0x04, fmRegs[0x38] >> 4);
		double cym = rhythmVol(keys & 0x02, fmRegs[0x38]);
		double hh = rhythmVol(keys & 0x01, fmRegs[0x37] >> 4);
		double body = std::max(bd, tom);
		double top = std::max({ sd, cym, hh });
		double vol = std::max(body, top);
		if(vol > in.NoiseVol) {
			in.NoiseVol = vol;
			in.NoiseBrightness = top / (top + body);
			in.ThumpEligible = bd > 0;
		}
	}

	//Live MIDI capture tap: no-ops unless a MIDI recording is active - see
	//MidiExporter.h for the Enhanced-Audio-gating limitation this implies.
	//The flush's sampleCount/sampleRate feed the emulated tick clock (ADR-0013).
	if(MidiExporter* midi = _emu->GetSoundMixer()->GetMidiExporter()) {
		midi->LogFrame("SMS", cfg.EnhancedAudioPreset, in, sampleCount, sampleRate);
	}

	_engine.Render(out, sampleCount, sampleRate, in, p, cfg.EnhancedAudioVolume);
}
