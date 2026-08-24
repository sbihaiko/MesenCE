#pragma once
#include "pch.h"
#include <chrono>
#include "Utilities/safe_ptr.h"
#include "Shared/Audio/EnhancedSynthEngine.h"

//Live logger that turns per-flush EnhancedSynthEngine::Input snapshots into a
//Standard MIDI File (SMF) format-1 / General MIDI capture, mirroring
//VgmExporter's "live logger, static-instance API" shape (see VgmExporter.h)
//but consuming aggregated synth-voice state instead of raw chip register
//writes: each console wrapper's already-Enhanced-Audio-enabled MixAudio
//branch gets one added, IsRecording()-guarded call to
//MidiExporter::LogFrame(consoleTag, presetId, in) right before
//_engine.Render(in, ...), reusing the exact Input values already built for
//the synth - no parallel snapshot type, no extra state threaded through
//SoundMixer/Emulator.
//
//KNOWN v1 LIMITATION: because LogFrame is only ever called from inside that
//Enhanced-Audio-gated branch (Core/NES/EnhancedSynth.cpp,
//Core/Gameboy/GbEnhancedSynth.cpp, Core/SMS/SmsEnhancedSynth.cpp all early-
//return before building "in" when cfg.EnableEnhancedAudio is false), MIDI
//capture is silently empty for any console-second where Enhanced Audio is
//off, even while a MIDI recording is active. This is a stated, accepted
//limitation of this slice - not a new gating mechanism invented here - and
//is unlike VgmExporter's raw-register tap, which keeps working regardless of
//that toggle.
//
//Ownership: a single static-instance singleton (StartRecording/StopRecording
//create and destroy it), exactly like VgmExporter's own _instance. This is a
//documented, accepted trade-off (see ADR-0012/0016/0017): only one MIDI
//capture can be active process-wide at a time. The VS DualSystem sub-console
//(two active cores sharing one process) therefore shares this single
//instance across both cores rather than getting one MidiExporter each - a
//single-active-console contract inherited unchanged from VgmExporter, not
//redesigned by this class.
//
//Timing model - HONESTLY NOT sample/cycle accurate, and NOT PAL/GB/SMS
//corrected: LogFrame() carries no elapsed-time or master-clock parameter of
//its own (each console wrapper simply calls it once per audio-mix flush).
//kFlushRateHz below is the same nominal ~179Hz NTSC flush cadence already
//assumed by the parallel VgmExporter-adjacent timing code in this directory;
//it is a fixed constant, not measured via std::chrono the way VgmExporter's
//EmitWait() measures real wall-clock time between chip writes. Every MIDI
//tick this class advances is therefore ticks-per-flush = (kTicksPerQuarterNote
//* tempoBpm / 60) / kFlushRateHz, accumulated with a carried fractional
//remainder (see AdvanceTick()) so rounding cannot drift the capture over a
//long session - but the nominal 179Hz itself only holds on NTSC. On PAL,
//Game Boy or SMS consoles whose actual flush cadence differs, playback tempo
//will drift proportionally; this is a known, un-fixed limitation (flagged by
//ADR-0018/0019/0023) that this slice only documents rather than corrects.
class MidiExporter
{
private:
	//See the class comment above for the honest NTSC-nominal-only rationale
	//behind these two constants.
	static constexpr uint32_t kTicksPerQuarterNote = 480;
	static constexpr double kFlushRateHz = 179.0;
	static constexpr double kDefaultTempoBpm = 120.0; //Fixed playback reference tempo (FF 51 03 meta); the ticks themselves already encode the real nominal-cadence timing, so this only needs to be "a sane default", not the true tempo.

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

	static safe_ptr<MidiExporter> _instance;

	string _outputFile;
	VoiceState _voices[kNumMelodicVoices];
	bool _drumActive = false;
	uint8_t _drumNote = 0;
	double _drumLastVol = 0;
	vector<uint8_t> _trackData[kTrackCount];
	uint32_t _trackLastTick[kTrackCount] = { 0, 0, 0 };
	uint32_t _currentTick = 0;
	double _tickFraction = 0;
	bool _programsSent = false;

	explicit MidiExporter(string outputFile);

	void EnsureProgramsSent(const char* consoleTag, uint32_t presetId);
	void ProcessMelodicVoice(uint32_t voiceIndex, double freq, double vol);
	void ProcessDrumVoice(const EnhancedSynthEngine::Input& in);

	//Appends one channel-voice MIDI event (Note-On/Off = 0x9n/0x8n, Program
	//Change = 0xCn) to "track", preceded by its delta-time. "data2" is the
	//event's 3rd byte (velocity, or 0 for a Note-Off); left at -1 for the
	//2-byte Program Change event, which has no 3rd byte.
	void EmitEvent(uint32_t track, uint8_t status, uint8_t data1, int data2 = -1);
	void AppendDelta(uint32_t track);
	void AppendBytes(uint32_t track, std::initializer_list<uint8_t> bytes);

	//Emits a Note-Off for every voice still held (melodic or drum). Called
	//from StopRecording()/the destructor BEFORE the End-Of-Track meta event
	//is written (see WriteFile()), so a capture stopped mid-note never ships
	//with a hung Note-On that some players/DAWs would otherwise sustain
	//forever or misinterpret.
	void FlushActiveVoices();
	void WriteFile();

	static void WriteVarLen(vector<uint8_t>& buf, uint32_t value);
	static uint8_t FreqToMidiNote(double freqHz);
	static uint8_t MelodicChannel(uint32_t voiceIndex);
	static uint8_t VelocityFromVol(double vol);

public:
	~MidiExporter();

	static void StartRecording(string outputFile);
	static void StopRecording();
	static bool IsRecording();

	//Consumes one console wrapper's per-flush synth-voice snapshot. Guarded
	//internally by IsRecording() (via the safe_ptr lock), so call sites don't
	//need their own IsRecording() check - see the class comment above for
	//exactly where each console wrapper should call this from.
	static void LogFrame(const char* consoleTag, uint32_t presetId, const EnhancedSynthEngine::Input& in);
};
