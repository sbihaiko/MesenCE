#pragma once
#include "pch.h"
#include "Shared/Audio/EnhancedSynthEngine.h"
#include "Shared/Audio/SmfWriter.h"

//Live logger that turns per-flush EnhancedSynthEngine::Input snapshots into a
//Standard MIDI File (SMF) format-1 / General MIDI capture. Consumes the
//aggregated synth-voice state each console wrapper already builds: the
//Enhanced-Audio-enabled MixAudio branch calls LogFrame(consoleTag, presetId,
//in, sampleCount, sampleRate) right before _engine.Render(in, ...), reusing
//the exact Input values already built for the synth.
//
//KNOWN v1 LIMITATION: because LogFrame is only ever called from inside that
//Enhanced-Audio-gated branch (Core/NES/EnhancedSynth.cpp,
//Core/Gameboy/GbEnhancedSynth.cpp, Core/SMS/SmsEnhancedSynth.cpp all early-
//return before building "in" when cfg.EnableEnhancedAudio is false), MIDI
//capture is silently empty for any console-second where Enhanced Audio is
//off, even while a MIDI recording is active. SoundMixer::StartMidiRecording
//surfaces a MessageManager notice when a capture starts in that state
//(ADR-0014); the gate itself is a stated, accepted limitation of this slice,
//unlike the VGM raw-register tap which works regardless of the toggle.
//
//Ownership (ADR-0012): owned per-Emulator by SoundMixer (safe_ptr member,
//mirroring _waveRecorder). Start/stop go through SoundMixer and must run
//while the emulation thread is paused (the interop layer wraps them in
//Emulator::AcquireLock()); captures stop on ROM load/unload and power-off
//(Emulator::Stop/LoadRom call StopMidiRecording()) and survive a soft reset.
//
//Timing (ADR-0013): each LogFrame call advances the tick clock by the
//emulated duration of the flush it accompanies - sampleCount/sampleRate, the
//values every MixAudio caller already has in hand - so the capture is
//correct on every region/console and immune to fast-forward, pause and
//save-state loads. kFlushRateHz survives only as the fallback tick length
//when a caller passes sampleRate == 0 (see AdvanceTick()).
//
//SMF byte-level encoding lives in SmfWriter (ADR-0034); this class keeps the
//note-segmentation state machine and the GM voice/channel mapping.
class MidiExporter
{
private:
	static constexpr uint32_t kTicksPerQuarterNote = 480;
	static constexpr double kFlushRateHz = 179.0; //Fallback-only nominal NTSC flush cadence (see AdvanceTick)
	static constexpr double kDefaultTempoBpm = 120.0; //Fixed playback reference tempo (FF 51 03 meta); the ticks themselves already encode the real timing, so this only needs to be "a sane default", not the true tempo.

	//Onset-detection thresholds. A Note-On fires in exactly one of two cases:
	// 1) Volume-attack-from-silence: vol > kOnsetVolThreshold &&
	//    lastVol <= kOnsetVolThreshold. This reuses the EXACT threshold
	//    (0.001) that EnhancedSynthEngine::Retrigger uses to decide whether
	//    to reset oscillator phases (Core/Shared/Audio/EnhancedSynthEngine.cpp:59-73)
	//    - the two decisions should agree, since both are asking "is this
	//    voice starting a new note out of near-silence".
	// 2) Pitch-jump-with-hysteresis: a voice already sounding whose pitch
	//    moves by more than kPitchJumpCents (plus the kPitchJumpHysteresisCents
	//    margin) from the note it's currently holding is treated as a new
	//    note (Note-Off then Note-On) rather than a continuous pitch bend.
	//    Without this second path, a legato slide from one sustained note to
	//    a distant one (no volume dip at all) would render as one impossibly
	//    long bent note instead of two. The hysteresis margin exists because
	//    a single hard threshold retriggers on ordinary vibrato/portamento
	//    wobble around the SAME note, producing a stutter of spurious
	//    Note-Ons when the capture is opened in MuseScore; too loose a
	//    combined threshold instead merges genuinely distinct legato notes
	//    into one held pitch. kPitchJumpCents+kPitchJumpHysteresisCents is
	//    the single combined "don't retrigger until you're sure" threshold.
	static constexpr double kOnsetVolThreshold = 0.001;
	static constexpr double kPitchJumpCents = 50.0;
	static constexpr double kPitchJumpHysteresisCents = 15.0;

	//GM channel 9 (0-based) is the reserved percussion channel; every other
	//melodic voice is assigned a channel via MelodicChannel(), which skips
	//index 9 (0-8 -> channels 0-8, 9-11 -> channels 10-12) so up to
	//kNumMelodicVoices melodic voices plus the drum channel fit in 13 of
	//MIDI's 16 channels without ever colliding with the percussion channel.
	static constexpr uint32_t kDrumChannel = 9;
	static constexpr uint32_t kNumMelodicVoices = 3 + EnhancedSynthEngine::MaxFmVoices; //Lead, Harmony, Bass, + up to MaxFmVoices FM voices
	static constexpr uint8_t kDrumHiHatNote = 42; //GM percussion: Closed Hi-Hat - NoiseBrightness >= 0.5 (bright LFSR top)
	static constexpr uint8_t kDrumTomNote = 45; //GM percussion: Low Tom - NoiseBrightness < 0.5 (slow LFSR body)

	//SMF format-1 track layout: one shared tempo/conductor track, one track
	//multiplexing every melodic voice's Note-On/Off/Program-Change events
	//(each on its own MIDI channel per MelodicChannel()), and one track for
	//the noise/drum voice on the GM percussion channel.
	static constexpr uint32_t kTrackTempo = 0;
	static constexpr uint32_t kTrackMelodic = 1;
	static constexpr uint32_t kTrackDrum = 2;
	static constexpr uint32_t kTrackCount = 3;

	struct VoiceState
	{
		bool Active = false;
		uint8_t Note = 0;
		double LastVol = 0;
		double HeldCents = 0; //Absolute pitch (cents relative to A4) of the currently-held note, for the pitch-jump-with-hysteresis check above
	};

	string _outputFile;
	ofstream _stream;
	SmfWriter _smf;
	VoiceState _voices[kNumMelodicVoices];
	bool _drumActive = false;
	uint8_t _drumNote = 0;
	double _drumLastVol = 0;
	uint32_t _currentTick = 0;
	double _tickFraction = 0;
	bool _programsSent = false;

	//Advances the tick clock by the emulated duration of one flush; the
	//fractional remainder is carried so rounding cannot drift the capture
	//over a long session. sampleRate == 0 falls back to the nominal
	//kFlushRateHz cadence (see the timing comment above).
	void AdvanceTick(uint32_t sampleCount, uint32_t sampleRate);

	void EnsureProgramsSent(const char* consoleTag, uint32_t presetId);
	void ProcessMelodicVoice(uint32_t voiceIndex, double freq, double vol);
	void ProcessDrumVoice(const EnhancedSynthEngine::Input& in);

	//Emits a Note-Off for every voice still held (melodic or drum). Called
	//from the destructor BEFORE the End-Of-Track meta event is written, so a
	//capture stopped mid-note never ships with a hung Note-On that some
	//players/DAWs would otherwise sustain forever or misinterpret.
	void FlushActiveVoices();

	static uint8_t FreqToMidiNote(double freqHz);
	static uint8_t MelodicChannel(uint32_t voiceIndex);
	static uint8_t VelocityFromVol(double vol);

public:
	//Opens and validates the output stream immediately (ADR-0033), so a bad
	//path fails at StartMidiRecording time instead of destroying the capture
	//at stop time. Check IsValid() after construction.
	explicit MidiExporter(string outputFile);
	~MidiExporter();

	bool IsValid() { return (bool)_stream; }

	//Consumes one console wrapper's per-flush synth-voice snapshot, advancing
	//the tick clock by that flush's emulated sampleCount/sampleRate duration.
	void LogFrame(const char* consoleTag, uint32_t presetId, const EnhancedSynthEngine::Input& in, uint32_t sampleCount, uint32_t sampleRate);
};
