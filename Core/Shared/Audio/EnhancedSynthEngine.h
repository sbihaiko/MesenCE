#pragma once
#include "pch.h"
#include "Shared/Audio/EnhancedSynthPreset.h"

//Console-agnostic DSP core for the "enhanced audio" synths (voices, drums,
//echo/reverb, bus compressor, final mix). The console-specific wrappers
//(Core/NES/EnhancedSynth, Core/SMS/SmsEnhancedSynth) only map their chip's
//live channel state to the Input snapshot below and hand it to Render() -
//nothing in here depends on the source chip's waveform shapes, only on
//frequency/volume, so a new console core just needs a new (thin) wrapper.
class EnhancedSynthEngine
{
public:
	static constexpr uint32_t MaxFmVoices = 9;

	//Per-flush channel snapshot filled in by the console-specific wrapper.
	//Volumes are 0..1, frequencies in Hz.
	struct Input
	{
		double LeadFreq = 0, LeadVol = 0;
		double HarmFreq = 0, HarmVol = 0;
		double BassFreq = 0, BassVol = 0;
		double NoiseVol = 0;
		double NoiseBrightness = 0; //0 = slow LFSR (snare/tom body), 1 = fast (bright hi-hat top)
		bool ThumpEligible = false; //noise rate low enough for the attack-triggered low thump
		double LeadWidth = 0.5; //pulse width; consoles with a duty register map it here
		double HarmWidth = 0.5;
		uint32_t FmVoiceCount = 0; //0 on consoles with no FM add-on
		double FmFreq[MaxFmVoices] = {};
		double FmVol[MaxFmVoices] = {};
	};

private:
	struct Voice
	{
		double Phase = 0;
		double PhaseB = 0;
		double SubPhase = 0;
		double SmoothedVol = 0;
		double Lp = 0;
		double LastVol = 0;
	};

	Voice _lead;
	Voice _harmony;
	Voice _bass;
	double _noiseVol = 0;
	uint32_t _noiseRng = 0x1D872B41;

	//One voice per FM melodic channel, summed into a single bus (post-filtered
	//by _fmLp) - see Render()
	Voice _fmVoices[MaxFmVoices];
	double _fmLp = 0;

	//Drum tone shaping (one-pole states) + low thump oscillator
	double _drumLpLow = 0;
	double _drumLpHigh = 0;
	double _drumLpTop = 0;
	double _thumpPhase = 0;
	double _thumpGate = 0;
	double _lastNoisePollVol = 0;

	//Lead echo + light feedforward reverb (sized for the 96kHz max rate)
	std::vector<float> _echoBuf = std::vector<float>(32768);
	std::vector<float> _revBufL = std::vector<float>(18432);
	std::vector<float> _revBufR = std::vector<float>(18432);
	uint32_t _echoPos = 0;
	uint32_t _revPos = 0;

	//Master bus compressor envelope (linked stereo: one detector for L+R)
	double _compEnv = 0;

	//Built-in presets (per-console, given to InitPresets) with any overrides
	//from EnhancedAudioPresets.cfg applied on top
	EnhancedSynthPreset _userPresets[5] = {};
	const EnhancedSynthPreset* _builtInPresets = nullptr;
	const char* _sectionSuffix = "";

	static double PolyBlep(double t, double dt);
	static double BlepSaw(double phase, double inc);
	static void Retrigger(Voice& voice, double vol);
	double NextNoise();

public:
	//Stores the wrapper's built-in preset table + its EnhancedAudioPresets.cfg
	//section suffix (see EnhancedSynthPresetLoader::Load) and loads the user
	//overrides once. Call from the wrapper's constructor.
	void InitPresets(const EnhancedSynthPreset builtInPresets[5], const char* sectionSuffix);

	//Re-reads EnhancedAudioPresets.cfg (file I/O + parsing). Must only be
	//called from outside the audio mix path - e.g. on console reset, on the
	//emulation thread - never from MixAudio/Render.
	void ReloadUserPresets();

	const EnhancedSynthPreset& GetPreset(uint32_t presetId) const;

	//Clears delay lines, voice phases and the compressor envelope. No file
	//I/O - safe to call from the mix path (used when the synth is disabled,
	//so re-enabling it does not replay stale audio frozen in the buffers).
	void Reset();

	//Synthesizes sampleCount stereo samples from the Input snapshot and adds
	//them onto "out" (interleaved L/R). "p" comes from GetPreset();
	//volumePct is the user's synth volume (0-100).
	void Render(int16_t* out, uint32_t sampleCount, uint32_t sampleRate, const Input& in, const EnhancedSynthPreset& p, double volumePct);
};
