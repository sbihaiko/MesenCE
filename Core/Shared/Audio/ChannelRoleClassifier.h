#pragma once
#include <cstdint>
#include <cmath>

//Level-2 "GM cover" front end (ADR-0052, F5.4g items 1 and 2): decides, from
//nothing but the live chip state, which melodic channel is currently playing
//the lead, the harmony and the bass, and which channels are momentarily
//playing a sound effect instead of music. Console-agnostic and free of any
//emulator dependency so the headless validation harness can compile this
//same file and feed it sampled APU state.
//
//The console wrapper (Core/NES/EnhancedSynth, Core/SMS/SmsEnhancedSynth)
//calls Update() once per audio flush (~5.6 ms) with one Channel per melodic
//chip channel; it then reads Role()/IsSfx() to route each channel into the
//EnhancedSynthEngine::Input slots (music) or its dry Sfx slots.
//
//Music/SFX (item 2). A channel is flagged as SFX while any of these hold:
// - the chip's hardware frequency sweep is running on it AND is moving the
//   pitch fast (>= kGlideMinRate) over >= kSweepMinTotal semitones (jump,
//   laser and explosion effects sweep far and fast; Zelda's driver uses the
//   same unit for slow 2-semitone musical slides, which must stay music);
// - it is gliding fast: pitch moving in one direction in >= kGlideMinSteps
//   steps of >= kGlideMinStep semitones, covering >= kGlideMinTotal semitones
//   at >= kGlideMinRate semitones/s (vibrato alternates direction; musical
//   portamento covers the same distance far more slowly);
// - it retriggers very fast over a range of >= kRetrigMinRange semitones with a
//   pitch sequence that is *not* a short cycle (a 2-4 note cycle at that rate
//   is an arpeggio - item 3 - and a narrow fast alternation is a wide vibrato
//   or a trill: both stay music);
// - it plays above kSqueakNote (piercing high squeals are effects).
//The flag holds until the channel falls silent for kSfxReleaseS or has been
//continuously sounding for kSfxMaxHoldS (a long sustained tone is music).
//
//Roles (item 1). Per-channel features are tracked with a ~1 s exponential
//window: mean pitch while audible, onset rate and audible fraction. Every
//kDecisionPeriodS the candidate assignment is: bass = the lowest channel if
//it sits low enough and clearly below the next one (else the wrapper's
//default bass channel); lead = the remaining channel with the highest
//"melody score" (pitch + onset activity); harmony = the other. Hysteresis:
//a new assignment only replaces the current one after it wins
//kDecisionsToSwitch consecutive decisions, and the swap is realised on the
//next note boundary of the channels involved (or after kSwapGraceS), so a
//voice never changes timbre in the middle of a held note.
class ChannelRoleClassifier
{
public:
	static constexpr uint32_t MaxChannels = 4;

	enum class ChannelRole : uint8_t
	{
		Lead = 0,
		Harmony = 1,
		Bass = 2
	};

	//Why a channel was flagged (diagnostics)
	enum SfxCue : uint8_t
	{
		CueSweep = 1,
		CueGlide = 2,
		CueSqueak = 4,
		CueRetrigger = 8
	};

	struct Channel
	{
		double Freq = 0; //Hz
		double Vol = 0; //0..1 (0 = silent)
		bool HwSweep = false; //hardware frequency sweep active on this channel
	};

	//Tuning constants (public so the harness can print them next to results)
	static constexpr double kVolThreshold = 0.001;
	static constexpr double kFeatureWindowS = 1.0;
	static constexpr double kDecisionPeriodS = 0.25;
	static constexpr uint32_t kDecisionsToSwitch = 3;
	static constexpr double kSwapGraceS = 0.35;
	static constexpr double kScoreMargin = 4.0;
	static constexpr double kOnsetRateWeight = 2.0; //semitones of score per onset/s (capped at 4/s)
	static constexpr double kBassMaxNote = 60.0; //C4
	static constexpr double kBassMinGap = 5.0; //semitones below the next channel
	static constexpr double kMinAudibleFraction = 0.12;
	static constexpr double kOnsetJumpSemitones = 0.65;
	static constexpr double kGlideMinStep = 0.25; //semitones per driver step (~15 st/s at 60 Hz; musical portamento is slower)
	static constexpr double kGlideMaxStep = 3.0; //bigger jumps are note changes, not glides
	static constexpr uint32_t kGlideMinSteps = 3;
	static constexpr double kGlideMinTotal = 7.0; //semitones a software glide must travel (Zelda's title swoops 6 st; effects with no hardware sweep go further)
	static constexpr double kSweepMinTotal = 4.0; //semitones a *fast* hardware sweep must cover before it reads as an effect
	static constexpr double kGlideMinRate = 12.0; //semitones per second (Zelda's title portamento is ~3 st/s, a Mario jump ~45 st/s)
	static constexpr double kMaxAudibleHz = 20000.0; //an ultrasonic sweep tail is silence, not a note
	static constexpr double kRetrigWindowS = 0.14;
	static constexpr uint32_t kRetrigMinOnsets = 5;
	static constexpr double kRetrigMinRange = 3.0; //semitones: narrower fast alternation is vibrato/trill (music)
	static constexpr double kSqueakNote = 105.0; //~A7
	static constexpr double kSfxReleaseS = 0.04;
	static constexpr double kSfxMaxHoldS = 1.5;
	static constexpr uint32_t kOnsetHistory = 8;
	//F5.4g Bloco B item 3: an arpeggio detection stays reportable until this
	//long after its last confirmation (slightly beyond the retrigger window so
	//consecutive cycle confirmations never gap).
	static constexpr double kArpeggioFreshS = 0.15;

private:
	struct State
	{
		//Note tracking
		bool Sounding = false;
		double Note = 0; //current pitch in MIDI note units (fractional)
		double HeldNote = 0; //pitch the current note started at (for onset-by-jump)
		double LastNote = 0;
		double LastVol = 0; //volume of the last flush (for the expression decay)
		double SoundingS = 0; //time since the current sound started (through onsets)
		double SilentS = 0;

		//F5.4g Bloco B item 4 (ADR-0052): expression measurements. PeakVol/
		//PeakAtS = the note's volume peak and when it happened, so DecayRate
		//can read how fast the note falls after its onset (pluck vs sustained);
		//VibratoDepth = peak semitones covered by opposing glide runs (pitch
		//oscillation); GlideRate = the current portamento slide rate (st/s).
		double PeakVol = 0;
		double PeakAtS = 0;
		double VibratoDepth = 0;
		double GlideRate = 0;

		//Glide detector
		int GlideDir = 0;
		uint32_t GlideSteps = 0;
		double GlideTotal = 0;
		double GlideStartS = 0;

		//Recent onsets (ring): time stamps + rounded pitches
		double OnsetTimes[kOnsetHistory] = {};
		int OnsetKeys[kOnsetHistory] = {};
		uint32_t OnsetPos = 0;
		uint32_t OnsetCount = 0;

		//Windowed features (exponential averages)
		double MeanNote = 60;
		double OnsetRate = 0;
		double AudibleFraction = 0;

		//SFX gate
		bool Sfx = false;
		double SfxHeldS = 0;
		uint8_t Cue = 0; //SfxCue bits that fired on the last update

		bool AtBoundary = true; //silent or just started a note this update
	};

	State _ch[MaxChannels];
	uint32_t _count = 0;
	ChannelRole _role[MaxChannels] = {};
	ChannelRole _defaultRole[MaxChannels] = {};
	ChannelRole _pendingRole[MaxChannels] = {};
	//F5.4g Bloco B: role each channel held when it last fell silent, for
	//HandleChannelSteal - when a channel's *native* role (its defaultRole) was
	//reassigned to another channel while it was away, the moment it resumes
	//that role is handed back (the composer-swap-back case ADR-0052 names)
	ChannelRole _heldRoleAtSilence[MaxChannels] = {};
	//F5.4g Bloco B item 6: per-channel FixedRole override from the pack's ESP
	//(-1 = auto; 0/1/2 = force Lead/Harmony/Bass), see SetFixedRoles
	int32_t _fixedRole[MaxChannels] = {};
	//F5.4g Bloco B item 3: the channel's current arpeggio cycle (2-4 distinct
	//notes at 20-60 Hz) + the last time it was re-confirmed, for
	//EnhancedSynthEngine::FoldArpeggioToChord
	int _arpeggioKeys[MaxChannels][4] = {};
	uint32_t _arpeggioCount[MaxChannels] = {};
	double _arpeggioAt[MaxChannels] = {};
	bool _swapPending = false;
	double _swapWaitS = 0;
	uint32_t _pendingVotes = 0;
	double _sinceDecisionS = 0;
	double _now = 0;
	bool _autoRoles = true;
	bool _sfxSeparation = true;

	static double ToNote(double freq) { return freq > 1.0 ? 69.0 + 12.0 * std::log2(freq / 440.0) : 0.0; }
	void UpdateNoteTracking(uint32_t i, const Channel& c, double dt);
	void UpdateSfxGate(uint32_t i, const Channel& c, double dt);
	void Decide();

public:
	//count melodic channels; defaultRole[i] is the wrapper's traditional
	//role for channel i (NES: pulse1=Lead, pulse2=Harmony, triangle=Bass).
	void Init(uint32_t count, const ChannelRole* defaultRole);
	void Reset();

	//Toggles (both default on). With auto roles off the default roles are
	//reported; with SFX separation off IsSfx() is always false.
	void SetAutoRoles(bool enabled) { _autoRoles = enabled; }
	void SetSfxSeparation(bool enabled) { _sfxSeparation = enabled; }

	//F5.4g Bloco B item 6 (ADR-0052): per-channel FixedRole override from the
	//pack's synth/preset.cfg (ESP) - index = physical channel, value -1 (auto)
	/// 0 (Lead) / 1 (Harmony) / 2 (Bass). A pinned channel always reports that
	//role, regardless of the auto decision (see EnhancedSynthPresetLoader).
	void SetFixedRoles(const int32_t fixedRoles[MaxChannels]);
	bool HasFixedRole(uint32_t i) const { return i < MaxChannels && _fixedRole[i] >= 0; }

	//One step of dt seconds (the audio flush duration) with the current
	//channel snapshot.
	void Update(const Channel* channels, double dt);

	ChannelRole Role(uint32_t i) const { return _role[i]; }
	bool IsSfx(uint32_t i) const { return _sfxSeparation && _ch[i].Sfx; }
	uint8_t SfxCues(uint32_t i) const { return _ch[i].Cue; }

	//F5.4g Bloco B (ADR-0052 item 2): a role that was reassigned to another
	//channel while its original channel was silent is handed back the moment
	//that channel resumes, bypassing the kDecisionsToSwitch hysteresis (only
	//fires for a brief silence - kStealMaxSilenceS - so a genuine melody
	//handoff stays as the classifier decided it). See UpdateNoteTracking.
	void HandleChannelSteal(uint32_t channel, ChannelRole stolenRole);

	//F5.4g Bloco B item 3: the channel's current arpeggio cycle - 2-4 distinct
	//MIDI notes alternating at 20-60 Hz - written into outKeys; returns the
	//note count (0 = not arpeggiating). Feeds EnhancedSynthEngine's
	//FoldArpeggioToChord so a fast broken chord becomes a sustained chord.
	uint32_t ArpeggioKeys(uint32_t i, int outKeys[4]) const;

	//F5.4g Bloco B item 4: expression measurements for the engine's
	//patch-family choice (EnhancedSynthEngine::ExpressionEnvelope) - decay in
	//vol/s since the note's peak, peak volume, vibrato depth in semitones and
	//the portamento slide rate in semitones/s.
	double DecayRate(uint32_t i) const;
	double PeakVol(uint32_t i) const { return _ch[i].PeakVol; }
	double VibratoDepth(uint32_t i) const { return _ch[i].VibratoDepth; }
	double PortamentoRate(uint32_t i) const { return _ch[i].GlideRate; }

	//Diagnostics (harness / debug HUD)
	double MeanNote(uint32_t i) const { return _ch[i].MeanNote; }
	double OnsetRate(uint32_t i) const { return _ch[i].OnsetRate; }
	double AudibleFraction(uint32_t i) const { return _ch[i].AudibleFraction; }
	static const char* RoleName(ChannelRole r) { return r == ChannelRole::Lead ? "lead" : r == ChannelRole::Harmony ? "harm" :
																																							"bass"; }
};
