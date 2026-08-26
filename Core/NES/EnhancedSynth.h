#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

class Emulator;
class NesConsole;
struct AudioConfig;

//Experimental "enhanced audio" synth.
//Re-interprets the APU channel state (frequency/volume/duty) with modern
//instrument timbres, mixed on top of (or in place of) the original chip
//output. The APU remains the source of truth: this only *reads* its state.
//All the DSP lives in the shared EnhancedSynthEngine - this class only maps
//APU state to the engine's Input snapshot.
class EnhancedSynth final : public IAudioProvider
{
private:
	Emulator* _emu = nullptr;
	NesConsole* _console = nullptr;
	EnhancedSynthEngine _engine;
	ChannelRoleClassifier _roles;
	bool _wasActive = false;

	//Diagnostics: "is the synth actually producing sound?" written to mesen.log
	//when the answer changes (and at most every kDiagPeriodS), so a silent
	//game in the GUI can be told apart from a silent APU without a debugger.
	double _diagTimerS = 0;
	int _diagState = -1; //-1 = nothing logged yet, 0 = silent, 1 = sounding

public:
	EnhancedSynth(Emulator* emu, NesConsole* console);
	virtual ~EnhancedSynth();

	//Clears delay lines and voice state, and re-reads EnhancedAudioPresets.cfg
	//(so editing the file only needs a console reset, not a restart). Called
	//on console reset - on the emulation thread, outside the mix path, so the
	//file I/O never runs inside MixAudio. Deliberately NOT called on state
	//load (run-ahead deserializes per frame).
	void Reset();

	void MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate) override;

private:
	void LogDiagnostics(const EnhancedSynthEngine::Input& in, const EnhancedSynthEngine::RawChannel* raw, int32_t peakBefore, int32_t peakAfter, AudioConfig& cfg, uint32_t sampleCount, uint32_t sampleRate);
};
