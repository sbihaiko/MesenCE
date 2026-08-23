#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

class Emulator;
class NesConsole;

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
	bool _wasActive = false;

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
};
