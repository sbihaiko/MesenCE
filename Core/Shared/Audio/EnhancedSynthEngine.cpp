#include "pch.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

void EnhancedSynthEngine::InitPresets(const EnhancedSynthPreset builtInPresets[5], const char* sectionSuffix, const string& packPresetPath)
{
	_builtInPresets = builtInPresets;
	_sectionSuffix = sectionSuffix;
	_packPresetPath = packPresetPath;
	ReloadUserPresets();
}

void EnhancedSynthEngine::ReloadUserPresets()
{
	EnhancedSynthPresetLoader::Load(_userPresets, _builtInPresets, _sectionSuffix, _packPresetPath);
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
	for(Voice& v : _fmVoices) {
		v = {};
	}
	_fmLp = 0;
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

	//A low thump is triggered only on attacks (volume rising into a slow+loud
	//noise), so sustained noise (wind, engines) does not turn into a hum - the
	//thump then decays on its own. The wrapper decides what "slow enough"
	//means for its chip (ThumpEligible).
	if(in.ThumpEligible && in.NoiseVol >= 0.65 && in.NoiseVol > _lastNoisePollVol + 0.08) {
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

	//Master bus soft-compressor (Studio preset): approximates an offline
	//normalize+tanh master. CompThreshold <= 0 disables it (the other presets
	//ship with it at 0, so this costs them nothing extra). The ratio is
	//clamped to >= 1 so a user-edited Ratio=0 can't divide by zero.
	bool compEnabled = p.CompThreshold > 0;
	double compRatio = std::max(1.0, p.CompRatio);
	double compAttackCoeff = compEnabled ? 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.CompAttackMs) / 1000.0)) : 0;
	double compReleaseCoeff = compEnabled ? 1.0 - std::exp(-1.0 / (sampleRate * std::max(0.5, p.CompReleaseMs) / 1000.0)) : 0;

	for(uint32_t i = 0; i < sampleCount; i++) {
		smooth(_lead.SmoothedVol, in.LeadVol);
		smooth(_harmony.SmoothedVol, in.HarmVol);
		smooth(_bass.SmoothedVol, in.BassVol);
		smooth(_noiseVol, in.NoiseVol);
		_thumpGate *= thumpDecay;

		//Lead: detuned pulse pair + octave-up saw shimmer, or (Studio) a fixed
		//detuned-saw stack that ignores the pulse width entirely
		double lead;
		if(p.LeadAlwaysSaw) {
			lead = 0.55 * BlepSaw(step(_lead.Phase, leadInc * (1.0 + p.LeadDetune)), leadInc * (1.0 + p.LeadDetune)) + 0.55 * BlepSaw(step(_lead.PhaseB, leadInc * (1.0 - p.LeadDetune)), leadInc * (1.0 - p.LeadDetune)) + p.LeadOctaveUpMix * BlepSaw(step(_lead.SubPhase, leadInc * 2.0), leadInc * 2.0);
		} else {
			lead = 0.45 * pulse(step(_lead.Phase, leadInc * (1.0 + p.LeadDetune)), leadInc * (1.0 + p.LeadDetune), in.LeadWidth) + 0.45 * pulse(step(_lead.PhaseB, leadInc * (1.0 - p.LeadDetune)), leadInc * (1.0 - p.LeadDetune), in.LeadWidth) + p.LeadOctaveUpMix * BlepSaw(step(_lead.SubPhase, leadInc * 2.0), leadInc * 2.0);
		}
		lead = softClip(lead * p.LeadDrive);
		_lead.Lp += (lead - _lead.Lp) * leadLpCoeff;
		lead = _lead.Lp * _lead.SmoothedVol;

		//Harmony: softer detuned pulse pair
		double harm = 0.45 * pulse(step(_harmony.Phase, harmInc * (1.0 + p.HarmDetune)), harmInc * (1.0 + p.HarmDetune), in.HarmWidth) + 0.45 * pulse(step(_harmony.PhaseB, harmInc * (1.0 - p.HarmDetune)), harmInc * (1.0 - p.HarmDetune), in.HarmWidth);
		_harmony.Lp += (harm - _harmony.Lp) * harmLpCoeff;
		harm = _harmony.Lp * _harmony.SmoothedVol;

		//Bass: sine + saw + half-frequency sub sine, mildly driven
		step(_bass.Phase, bassInc);
		step(_bass.SubPhase, bassInc * 0.5);
		double bass = p.BassSine * std::sin(pi2 * _bass.Phase) + p.BassSaw * BlepSaw(step(_bass.PhaseB, bassInc), bassInc) + p.BassSub * std::sin(pi2 * _bass.SubPhase);
		bass = softClip(bass * p.BassDrive);
		_bass.Lp += (bass - _bass.Lp) * bassLpCoeff;
		bass = _bass.Lp * _bass.SmoothedVol;

		//Drums: bandpassed body vs highpassed top blended by LFSR rate + thump
		double n = NextNoise();
		_drumLpLow += (n - _drumLpLow) * drumLowCoeff;
		_drumLpHigh += (n - _drumLpHigh) * drumHighCoeff;
		_drumLpTop += (n - _drumLpTop) * drumTopCoeff;
		double body = (_drumLpHigh - _drumLpLow) * p.DrumBodyGain;
		double top = n - _drumLpTop;
		step(_thumpPhase, thumpInc);
		double drum = (in.NoiseBrightness * top + (1.0 - in.NoiseBrightness) * body) * _noiseVol + p.ThumpGain * std::sin(pi2 * _thumpPhase) * _thumpGate * _noiseVol;

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
		_echoBuf[_echoPos] = (float)lead;
		_echoPos = (_echoPos + 1) % echoSize;

		//Stereo image: harmony left, lead echo right, FM centered
		double left = p.LeadGain * lead + p.EchoGainL * echo + 1.25 * p.HarmGain * harm + p.BassGain * bass + p.DrumGain * drum + p.LeadGain * fmBus;
		double right = p.LeadGain * lead + p.EchoGainR * echo + 0.80 * p.HarmGain * harm + p.BassGain * bass + p.DrumGain * drum + p.LeadGain * fmBus;

		//Light feedforward reverb (3 taps)
		_revBufL[_revPos] = (float)left;
		_revBufR[_revPos] = (float)right;
		uint32_t t1 = (_revPos + revSize - revTap1) % revSize;
		uint32_t t2 = (_revPos + revSize - revTap2) % revSize;
		uint32_t t3 = (_revPos + revSize - revTap3) % revSize;
		left += p.ReverbWet * (0.35 * _revBufL[t1] + 0.28 * _revBufL[t2] + 0.22 * _revBufL[t3]);
		right += p.ReverbWet * (0.35 * _revBufR[t1] + 0.28 * _revBufR[t2] + 0.22 * _revBufR[t3]);
		_revPos = (_revPos + 1) % revSize;

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
