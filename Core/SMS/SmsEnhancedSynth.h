#pragma once
#include "pch.h"
#include "Shared/Interfaces/IAudioProvider.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

class Emulator;
class SmsConsole;

//Experimental "enhanced audio" synth for the SMS/Game Gear/SG-1000/ColecoVision
//PSG (SN76489: 3 tone channels + 1 noise channel, shared by every SmsModel via
//SmsConsole/SmsPsg). Re-interprets the PSG's live channel state (frequency,
//4-bit volume) with modern instrument timbres, mixed on top of (or in place
//of) the original chip output. The PSG remains the source of truth: this only
//*reads* its state. All the DSP lives in the shared EnhancedSynthEngine -
//this class only maps PSG/FM state to the engine's Input snapshot. The
//SN76489 has no duty register, so FollowDuty has no effect here (the lead
//always uses FixedWidth or LeadAlwaysSaw).
//
//Also re-interprets the optional YM2413 FM add-on's (SmsFmAudio) melodic
//channels (0-8), read directly from its raw register file - some games (e.g.
//After Burner, Shadow Dancer) switch their whole soundtrack over to FM and
//mute the PSG entirely, leaving nothing in the PSG registers above to
//re-interpret. Rhythm-mode percussion (channels 6-8 repurposed as BD/SD/
//TOM/CYM/HH) is mapped onto the engine's drum path - see MixAudio.
class SmsEnhancedSynth final : public IAudioProvider
{
private:
	Emulator* _emu = nullptr;
	SmsConsole* _console = nullptr;
	EnhancedSynthEngine _engine;
	ChannelRoleClassifier _roles;
	bool _wasActive = false;

public:
	SmsEnhancedSynth(Emulator* emu, SmsConsole* console);
	virtual ~SmsEnhancedSynth();

	//No public Reset(): SmsConsole::Reset power-cycles via ReloadRom, which
	//recreates this object (the constructor re-reads EnhancedAudioPresets.cfg),
	//and disabling the synth clears the engine state from MixAudio itself.

	void MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate) override;
};
