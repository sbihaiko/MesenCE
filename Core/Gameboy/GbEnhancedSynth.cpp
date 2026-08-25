#include "pch.h"
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "Gameboy/GbEnhancedSynth.h"
#include "Gameboy/Gameboy.h"
#include "Gameboy/APU/GbApu.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Audio/SoundMixer.h"
#include "Shared/Audio/MidiExporter.h"

//Built-in instrument presets. Order must match the EnhancedAudioPreset enum
//on the UI side (Synthwave = 0, ChipDeluxe = 1, OrchestralLite = 2, Dry = 3,
//Studio = 4). Values start as a copy of the NES engine's tuning
//(Core/NES/EnhancedSynth.cpp) - the GB APU is the closest sibling of the 2A03
//(duty squares + noise; the wave channel stands in for the triangle), so the
//NES tuning is the natural starting point. Expect to retune by ear.
// clang-format off
static constexpr EnhancedSynthPreset _presets[5] = {
	//Synthwave: detuned pulse-width leads, saw+sub bass, tight drums
	{
		0.004, 0.002, true, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.16,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Chip deluxe: stays close to the APU character - pure-ish pulses,
	//round bass, crisp drums, just a touch of space
	{
		0.0015, 0.001, true, 0.5, false, 0.10, 8000, 6000, 1.1,
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
		0.004, 0.002, true, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		3, 4,
		0.05, 0.0, 0.0, 0.0,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Studio: always-saw fat lead (duty ignored), same tuned pan/bass/drum
	//balance as Synthwave, plus a gentle bus compressor.
	{
		0.003, 0.002, true, 0.5, true, 0.25, 5200, 3200, 1.4,
		0.70, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.18,
		1.0, 0.56, 0.85, 0.75,
		0.55, 3.0, 8, 140, 1.18
	},
};
// clang-format on

GbEnhancedSynth::GbEnhancedSynth(Emulator* emu, Gameboy* console)
{
	_emu = emu;
	_console = console;
	//This engine reads EnhancedAudioPresets.cfg sections suffixed ".Gb"
	//(e.g. "[Studio.Gb]") so its tuning can live in the same file as the
	//other engines' - see EnhancedSynthPresetLoader::Load.
	//MEP synth section (ADR-0042): the manager already resolved the packs
	//for this ROM in Emulator::InternalLoadRom
	_engine.InitPresets(_presets, ".Gb", _emu->GetEnhancementPackManager()->GetSynthPresetPaths());
	_emu->GetSoundMixer()->RegisterAudioProvider(this);
}

GbEnhancedSynth::~GbEnhancedSynth()
{
	_emu->GetSoundMixer()->UnregisterAudioProvider(this);
}

void GbEnhancedSynth::MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate)
{
	//Enhanced audio settings are shared across every console (AudioConfig),
	//not GB-specific - see Core/NES/EnhancedSynth.cpp for the NES equivalent.
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

	//The synth state is polled once per audio flush, same cadence as the
	//other engines.
	GbApuDebugState apu = _console->GetApu()->GetState();
	GameboyConfig& gbCfg = _emu->GetSettings()->GetGameboyConfig();

	//11-bit period registers: a square's waveform advances one duty step per
	//(2048 - freq) * 4 CPU clocks, so a full 8-step cycle is 131072 / (2048 -
	//freq) Hz; the wave channel's 32-sample cycle runs twice as fast per
	//step, giving 65536 / (2048 - freq) Hz.
	auto squareFreq = [](uint16_t freq) { return 131072.0 / (2048 - (freq & 0x7FF)); };
	auto waveFreq = [](uint16_t freq) { return 65536.0 / (2048 - (freq & 0x7FF)); };

	EnhancedSynthEngine::Input in;

	//Square volumes are the live envelope output (0-15); Enabled covers
	//length-counter expiry and DAC power. Per-channel volume settings
	//(Settings > Game Boy > Audio) apply to the synth voices too, so muting a
	//chip channel also mutes its enhanced voice.
	in.LeadFreq = squareFreq(apu.Square1.Frequency);
	if(apu.Common.ApuEnabled && apu.Square1.Enabled) {
		in.LeadVol = apu.Square1.Volume / 15.0 * gbCfg.Square1Vol / 100.0;
	}
	in.HarmFreq = squareFreq(apu.Square2.Frequency);
	if(apu.Common.ApuEnabled && apu.Square2.Enabled) {
		in.HarmVol = apu.Square2.Volume / 15.0 * gbCfg.Square2Vol / 100.0;
	}
	//Wave: usually the bass line; its 2-bit volume code shifts samples right
	//by (code - 1), i.e. 100% / 50% / 25%, 0 = mute
	in.BassFreq = waveFreq(apu.Wave.Frequency);
	if(apu.Common.ApuEnabled && apu.Wave.Enabled && apu.Wave.DacEnabled && apu.Wave.Volume > 0) {
		in.BassVol = (1.0 / (1 << (apu.Wave.Volume - 1))) * gbCfg.WaveVol / 100.0;
	}
	if(apu.Common.ApuEnabled && apu.Noise.Enabled) {
		in.NoiseVol = apu.Noise.Volume / 15.0 * gbCfg.NoiseVol / 100.0;
	}

	//The duty cycle is part of the arrangement (12.5% leads vs 50% pads);
	//map it to the synth's pulse width so that character survives.
	//Duty 3 (75%) sounds identical to 25%, so it maps back to 0.25.
	static constexpr double dutyWidth[4] = { 0.125, 0.25, 0.5, 0.25 };
	in.LeadWidth = p.FollowDuty ? dutyWidth[apu.Square1.Duty & 0x03] : p.FixedWidth;
	in.HarmWidth = p.FollowDuty ? dutyWidth[apu.Square2.Duty & 0x03] : p.FixedWidth;

	//Noise LFSR shift rate (see GbNoiseChannel::GetPeriod: the LFSR clocks
	//every (divisor==0 ? 8 : 16*divisor) << shift CPU clocks at 4MHz), mapped
	//to drum timbre with the same normalizer/ceiling as the NES engine - the
	//two chips cover a similar rate range.
	uint32_t noisePeriod = (apu.Noise.Divisor == 0 ? 8 : 16 * apu.Noise.Divisor) << apu.Noise.PeriodShift;
	double noiseFreq = 4194304.0 / noisePeriod;
	in.NoiseBrightness = std::min(1.0, noiseFreq / 200000.0);
	in.ThumpEligible = noiseFreq <= 15000.0;

	//Live MIDI capture tap: no-ops unless a MIDI recording is active - see
	//MidiExporter.h for the Enhanced-Audio-gating limitation this implies.
	//The flush's sampleCount/sampleRate feed the emulated tick clock (ADR-0013).
	if(MidiExporter* midi = _emu->GetSoundMixer()->GetMidiExporter()) {
		midi->LogFrame("GB", cfg.EnhancedAudioPreset, in, sampleCount, sampleRate);
	}

	_engine.Render(out, sampleCount, sampleRate, in, p, cfg.EnhancedAudioVolume);
}
