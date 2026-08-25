#pragma once
#include "pch.h"

//Instrument definition for an "enhanced audio" synth. Built-in defaults are
//defined per-console (e.g. Core/NES/EnhancedSynth.cpp, Core/SMS/SmsEnhancedSynth.cpp);
//any field can be overridden per-preset, with no rebuild, via a
//"EnhancedAudioPresets.cfg" text file in the Mesen home folder (see
//EnhancedSynthPresetLoader::Load for the format). Shared verbatim across
//consoles: the bass/drums/echo/reverb/compressor DSP that consumes these
//fields only cares about frequency/volume, never about the source chip's
//waveform shape, so one struct (and one loader) covers every engine.
struct EnhancedSynthPreset
{
	//Pulse voices
	double LeadDetune;
	double HarmDetune;
	bool FollowDuty; //pulse width follows the game's duty setting (no effect on chips with no duty register)
	double FixedWidth; //used when FollowDuty is false
	bool LeadAlwaysSaw; //true: lead is a fixed detuned-saw stack, duty ignored entirely
	double LeadOctaveUpMix;
	double LeadLpHz;
	double HarmLpHz;
	double LeadDrive;

	//Bass (triangle)
	double BassSine;
	double BassSaw;
	double BassSub;
	double BassLpHz;
	double BassDrive;

	//Drums (noise)
	double DrumBodyLoHz;
	double DrumBodyHiHz;
	double DrumTopHz;
	double DrumBodyGain;
	double ThumpGain;
	double ThumpDecayS;
	double ThumpFreqHz;

	//Envelope smoothing
	double AttackMs;
	double ReleaseMs;

	//FX
	double EchoDelayS;
	double EchoGainL;
	double EchoGainR;
	double ReverbWet;

	//Mix
	double LeadGain;
	double HarmGain;
	double BassGain;
	double DrumGain;

	//Master bus soft-compressor (approximates the offline normalize+tanh
	//master); CompThreshold == 0 disables it entirely (zero extra cost).
	double CompThreshold;
	double CompRatio;
	double CompAttackMs;
	double CompReleaseMs;
	double CompMakeup;
};

//Loads EnhancedAudioPresets.cfg overrides (shared file, all engines) on top of
//a set of built-in presets.
class EnhancedSynthPresetLoader
{
public:
	//Copies "defaults" into "outPresets" (5 entries each), then applies any
	//matching "[<PresetName><sectionSuffix>]" section from, in order, the
	//MEP pack's synth file (packPresetPath, ESP v1 - empty when no pack is
	//active) and EnhancedAudioPresets.cfg on top - the user's file always
	//wins, field by field (MEP-v1 §5.3, ADR-0042). sectionSuffix lets each
	//engine keep its own tuning in the same file without colliding - e.g. the
	//NES engine uses "" (section "[Studio]"), the SMS engine uses ".Sms"
	//(section "[Studio.Sms]").
	static void Load(EnhancedSynthPreset outPresets[5], const EnhancedSynthPreset defaults[5], const char* sectionSuffix, const vector<string>& packPresetPaths = {});

private:
	static void ApplyFile(const string& path, EnhancedSynthPreset outPresets[5], const string& suffix);
};
