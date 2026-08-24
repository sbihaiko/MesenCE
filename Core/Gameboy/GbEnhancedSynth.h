#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

class Emulator;
class Gameboy;

//Experimental "enhanced audio" synth for the Game Boy APU (2 duty squares +
//wave + noise). Re-interprets the APU's live channel state (frequency,
//envelope volume, duty) with modern instrument timbres, mixed on top of (or
//in place of) the original chip output. The APU remains the source of truth:
//this only *reads* its state. All the DSP lives in the shared
//EnhancedSynthEngine - this class only maps APU state to the engine's Input
//snapshot (Square1 = lead, Square2 = harmony, Wave = bass, Noise = drums).
//Only created for the main handheld console - not for SGB (audio there is
//owned by the SNES core) nor for the link-cable secondary console (two synths
//re-interpreting two games at once would just double the output).
//
//No public Reset(): Gameboy::Reset power-cycles via ReloadRom, which
//recreates this object (the constructor re-reads EnhancedAudioPresets.cfg),
//and disabling the synth clears the engine state from MixAudio itself.
class GbEnhancedSynth final : public IAudioProvider
{
private:
	Emulator* _emu = nullptr;
	Gameboy* _console = nullptr;
	EnhancedSynthEngine _engine;
	bool _wasActive = false;

public:
	GbEnhancedSynth(Emulator* emu, Gameboy* console);
	virtual ~GbEnhancedSynth();

	void MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate) override;
};
