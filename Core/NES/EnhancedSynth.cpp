#include "pch.h"
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "NES/EnhancedSynth.h"
#include "NES/NesConsole.h"
#include "NES/APU/NesApu.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Audio/SoundMixer.h"
#include "Shared/Audio/MidiExporter.h"

//Built-in instrument presets. Order must match the EnhancedAudioPreset enum
//on the UI side (Synthwave = 0, ChipDeluxe = 1, OrchestralLite = 2, Dry = 3,
//Studio = 4).
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
	//Chip deluxe: stays close to the 2A03 character - pure-ish pulses,
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
	//Studio: verbatim port of the offline remaster mix - always-saw fat lead
	//(duty ignored), same tuned pan/bass/drum values as Synthwave (already
	//matched the offline mix), plus a gentle bus compressor standing in for
	//the offline normalize+tanh master.
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

EnhancedSynth::EnhancedSynth(Emulator* emu, NesConsole* console)
{
	_emu = emu;
	_console = console;
	//NES uses an empty EnhancedAudioPresets.cfg section suffix ("[Studio]",
	//etc), matching the file format that predates the loader being shared
	//with other consoles - see EnhancedSynthPresetLoader::Load.
	//MEP synth section (ADR-0042): the manager already resolved the packs
	//for this ROM in Emulator::InternalLoadRom
	_engine.InitPresets(_presets, "", _emu->GetEnhancementPackManager()->GetSynthPresetPaths());
	_emu->GetSoundMixer()->RegisterAudioProvider(this);
}

EnhancedSynth::~EnhancedSynth()
{
	_emu->GetSoundMixer()->UnregisterAudioProvider(this);
}

void EnhancedSynth::Reset()
{
	_engine.Reset();
	_engine.ReloadUserPresets();
	_wasActive = false;
}

void EnhancedSynth::MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate)
{
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

	//The synth state is polled once per audio flush (~5.6ms / ~179Hz), which is
	//~3x the 60Hz rate NES sound drivers update their registers at - so control
	//changes land with at most one flush (~5.6ms) of latency, no stair-stepping
	//beyond what the driver itself produces.
	ApuState apu = _console->GetApu()->GetState();

	auto envVolume = [](ApuEnvelopeState& env) {
		return (env.ConstantVolume ? env.Volume : env.Counter) / 15.0;
	};

	EnhancedSynthEngine::Input in;
	in.LeadFreq = apu.Square1.Frequency;
	if(apu.Square1.Enabled && apu.Square1.LengthCounter.Counter > 0 && apu.Square1.Period >= 8) {
		in.LeadVol = envVolume(apu.Square1.Envelope);
	}
	in.HarmFreq = apu.Square2.Frequency;
	if(apu.Square2.Enabled && apu.Square2.LengthCounter.Counter > 0 && apu.Square2.Period >= 8) {
		in.HarmVol = envVolume(apu.Square2.Envelope);
	}
	in.BassFreq = apu.Triangle.Frequency;
	if(apu.Triangle.Enabled && apu.Triangle.LengthCounter.Counter > 0 && apu.Triangle.LinearCounter > 0 && apu.Triangle.Period >= 2) {
		in.BassVol = 1.0;
	}
	if(apu.Noise.Enabled && apu.Noise.LengthCounter.Counter > 0) {
		in.NoiseVol = envVolume(apu.Noise.Envelope);
	}

	//Per-channel volume settings (Settings > NES > Audio) apply to the synth
	//voices too, so muting a chip channel also mutes its enhanced voice
	NesConfig& nesCfg = _console->GetNesConfig();
	in.LeadVol *= nesCfg.ChannelVolumes[(int)AudioChannel::Square1] / 100.0;
	in.HarmVol *= nesCfg.ChannelVolumes[(int)AudioChannel::Square2] / 100.0;
	in.BassVol *= nesCfg.ChannelVolumes[(int)AudioChannel::Triangle] / 100.0;
	in.NoiseVol *= nesCfg.ChannelVolumes[(int)AudioChannel::Noise] / 100.0;

	//The duty cycle is part of the arrangement (12.5% leads vs 50% pads);
	//map it to the synth's pulse width so that character survives.
	//Duty 3 (75%) sounds identical to 25% on the NES, so it maps back to 0.25.
	static constexpr double dutyWidth[4] = { 0.125, 0.25, 0.5, 0.25 };
	in.LeadWidth = p.FollowDuty ? dutyWidth[apu.Square1.Duty & 0x03] : p.FixedWidth;
	in.HarmWidth = p.FollowDuty ? dutyWidth[apu.Square2.Duty & 0x03] : p.FixedWidth;

	//Map the noise shift rate to drum timbre: fast LFSR = bright hi-hat top,
	//slow = snare/tom body; only a slow LFSR qualifies as a kick/tom attack
	//for the engine's low thump.
	in.NoiseBrightness = std::min(1.0, apu.Noise.Frequency / 200000.0);
	in.ThumpEligible = apu.Noise.Frequency <= 15000.0;

	//Live MIDI capture tap: no-ops unless a MIDI recording is active - see
	//MidiExporter.h for the Enhanced-Audio-gating limitation this implies.
	//The flush's sampleCount/sampleRate feed the emulated tick clock (ADR-0013).
	if(MidiExporter* midi = _emu->GetSoundMixer()->GetMidiExporter()) {
		midi->LogFrame("NES", cfg.EnhancedAudioPreset, in, sampleCount, sampleRate);
	}

	_engine.Render(out, sampleCount, sampleRate, in, p, cfg.EnhancedAudioVolume);
}
