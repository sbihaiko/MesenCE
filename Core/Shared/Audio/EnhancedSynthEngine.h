#pragma once
#include "pch.h"
#include "Shared/Audio/EnhancedSynthPreset.h"
#include "Shared/Audio/ChannelRoleClassifier.h"

struct tsf;

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
	static constexpr uint32_t MaxSfxVoices = 4;
	//F5.4g Bloco B item 3 (ADR-0052): a folded arpeggio holds at most a 2-4
	//note cycle as a sustained chord, so a slot can stack up to 4 notes.
	static constexpr uint32_t MaxChordNotes = 4;

	//F5.4g Bloco B item 4 (ADR-0052): expression read from the live chip state
	//- decay, vibrato and portamento - that picks the patch family (pluck ×
	//sustained × strings) and modulates the voice. EvaluateExpression turns
	//the three measurements into a family; Render applies the family to the
	//SoundFont program choice (kFamilyPrograms) and the DSP attack/release.
	struct ExpressionEnvelope
	{
		double DecayRate = 0;      //volume fall after the note's peak, vol/s
		double VibratoDepth = 0;   //peak-to-peak pitch oscillation, semitones
		double PortamentoRate = 0; //pitch slide rate, semitones/s
		uint32_t Family = 0;       //FamilyPluck / FamilySustained / FamilyStrings
		static constexpr uint32_t FamilyPluck = 0;
		static constexpr uint32_t FamilySustained = 1;
		static constexpr uint32_t FamilyStrings = 2;
	};
	//F5.4g Bloco B item 4: classify the three measurements into a patch
	//family. A note that falls fast after its onset and barely oscillates is a
	//pluck; a pitch that oscillates while held or slides between notes reads
	//as a bowed/pad instrument (strings); otherwise the tone sustains as-is.
	static ExpressionEnvelope EvaluateExpression(double decayRate, double vibratoDepth, double portamentoRate);

	//F5.4g Bloco B item 4: GM programs (0-based) per expression family for the
	//three music slots - pluck and strings replace the preset's Gm*Program
	//(which stays the sustained default); -1 keeps the preset choice. A slot
	//with a FixedRole override (item 6) is exempt, so a human choice always
	//wins.
	static constexpr int kFamilyPrograms[3][3] = {
		{ 26, 24, 33 }, //pluck: steel guitar, nylon guitar, electric bass (finger)
		{ -1, -1, -1 }, //sustained: preset's Gm*Program unchanged
		{ 49, 48, 44 }, //strings: string ensemble 2, string ensemble 1, tremolo strings
	};

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

		//F5.4g Bloco B item 3: sustained-chord stacks for the music slots.
		//When a channel plays a fast arpeggio (20-60 Hz cycle), Route() folds
		//its notes into these (>= 2 frequencies) and Render sounds all of them
		//together instead of the single note. Count 0/1 = the slot's plain
		//frequency is used.
		uint32_t LeadChordCount = 0, HarmChordCount = 0, BassChordCount = 0;
		double LeadChord[MaxChordNotes] = {};
		double HarmChord[MaxChordNotes] = {};
		double BassChord[MaxChordNotes] = {};

		//F5.4g Bloco B item 4: per-slot expression family from the live chip
		//state (EvaluateExpression), used by Render to pick the SoundFont
		//program (kFamilyPrograms) and shape the DSP attack/release.
		//FamilyLocked = the slot's channel carries a FixedRole override
		//(item 6), so the family must not replace its program.
		uint32_t Family[3] = { ExpressionEnvelope::FamilySustained, ExpressionEnvelope::FamilySustained, ExpressionEnvelope::FamilySustained };
		bool FamilyLocked[3] = {};

		//Channels the wrapper's ChannelRoleClassifier flagged as sound
		//effects (ADR-0052 item 2): rendered as plain dry pulses, outside the
		//music patches and the echo/reverb sends, so a jump or a hit keeps
		//its chip character while the music gets the instrument treatment.
		struct SfxVoice
		{
			double Freq = 0;
			double Vol = 0;
			double Width = 0.5;
		};
		uint32_t SfxCount = 0;
		SfxVoice Sfx[MaxSfxVoices];
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
	//F5.4g Bloco B item 3: per-note oscillators for the folded sustained
	//chords (one voice per slot per chord note; the single _lead/_harmony/
	//_bass voices play when the slot is a plain note)
	Voice _leadChord[MaxChordNotes];
	Voice _harmChord[MaxChordNotes];
	Voice _bassChord[MaxChordNotes];
	double _noiseVol = 0;
	uint32_t _noiseRng = 0x1D872B41;

	//One voice per FM melodic channel, summed into a single bus (post-filtered
	//by _fmLp) - see Render()
	Voice _fmVoices[MaxFmVoices];
	double _fmLp = 0;

	//Dry SFX voices (one per Input::Sfx slot)
	Voice _sfx[MaxSfxVoices];

	//SoundFont back end (TinySoundFont) - null when no .sf2 is loaded, in
	//which case the DSP voices above render the music as before. Channels:
	//0 lead, 1 harmony, 2 bass, 9 percussion.
	struct SfNote
	{
		int Key = -1;
		double OnVol = 0;
	};
	tsf* _sf = nullptr;
	string _sfPath;
	uint32_t _sfRate = 0;
	int _sfPrograms[3] = { -1, -1, -1 };
	SfNote _sfNotes[3];
	//F5.4g Bloco B item 3: the SoundFont side of a folded chord - up to
	//MaxChordNotes held notes per music channel (the single _sfNotes entry
	//plays when the slot is a plain note)
	SfNote _sfChordNotes[3][MaxChordNotes] = {};
	//Percussion voices must be released explicitly: a drum kit region with an
	//infinite sustain never leaves its sustain segment on its own, and TSF
	//(with a voice cap set) can only recycle voices that are *in release* - a
	//pool full of held drum voices makes it drop every new melodic note
	//silently, which is heard as the music fading out after ~30s.
	struct SfDrumHit
	{
		int Key = -1;
		double LeftS = 0;
	};
	static constexpr uint32_t MaxSfDrumHits = 6;
	static constexpr double kSfDrumHoldS = 0.18;
	SfDrumHit _sfDrums[MaxSfDrumHits];
	void SfTriggerDrum(int key, double vel, double gain);
	void SfAgeDrums(double dt);
	std::vector<float> _sfBuf;
	double _sfLastPeak = 0;
	double _sfChannelVol[3] = {};
	uint64_t _sfNoteOns = 0;
	uint64_t _sfNoteOnFails = 0;
	void SfUpdateVoice(int channel, SfNote& note, double freq, double vol, double gain);
	void SfUpdateChord(int channel, SfNote* notes, uint32_t count, const double* freqs, double vol, double gain);

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
	//ESP file from the active MEP pack's synth section ("" = none) - ADR-0042
	vector<string> _packPresetPaths;

	static double PolyBlep(double t, double dt);
	static double BlepSaw(double phase, double inc);
	static void Retrigger(Voice& voice, double vol);
	double NextNoise();

public:
	//Diagnostics: active SoundFont voices and the peak of the last SF flush
	//(a voice leak or a stuck channel shows up here before it is audible)
	int SfVoiceCount() const;
	double SfLastPeak() const { return _sfLastPeak; }
	//Last values handed to TinySoundFont per channel (key, channel volume)
	int SfKey(int ch) const { return _sfNotes[ch].Key; }
	double SfChannelVolume(int ch) const { return _sfChannelVol[ch]; }
	double SfOnVol(int ch) const { return _sfNotes[ch].OnVol; }
	int SfChannelVoices(int channel) const;
	double SfChannelGainDb(int channel) const;
	uint64_t SfNoteOns() const { return _sfNoteOns; }
	uint64_t SfNoteOnFails() const { return _sfNoteOnFails; }
	int SfPresetIndex(int channel) const;
	//Stores the wrapper's built-in preset table + its EnhancedAudioPresets.cfg
	//section suffix (see EnhancedSynthPresetLoader::Load) and loads the user
	//overrides once. Call from the wrapper's constructor.
	void InitPresets(const EnhancedSynthPreset builtInPresets[5], const char* sectionSuffix, const vector<string>& packPresetPaths = {});

	//Re-reads EnhancedAudioPresets.cfg (file I/O + parsing). Must only be
	//called from outside the audio mix path - e.g. on console reset, on the
	//emulation thread - never from MixAudio/Render.
	void ReloadUserPresets();
	//Path of the MEP synth preset applied between built-ins and the user's
	//file (takes effect on the next ReloadUserPresets)
	void SetPackPresetPaths(const vector<string>& paths) { _packPresetPaths = paths; }

	const EnhancedSynthPreset& GetPreset(uint32_t presetId) const;

	//Clears delay lines, voice phases and the compressor envelope. No file
	//I/O - safe to call from the mix path (used when the synth is disabled,
	//so re-enabling it does not replay stale audio frozen in the buffers).
	void Reset();

	//Loads a SoundFont (.sf2) for the level-2 GM timbres (ADR-0052). File
	//I/O - only call from outside the mix path (constructor / console reset,
	//next to ReloadUserPresets). Returns false and keeps the DSP voices when
	//the file cannot be loaded; an empty path unloads.
	bool LoadSoundFont(const string& path);
	bool HasSoundFont() const { return _sf != nullptr; }
	const string& GetSoundFontPath() const { return _sfPath; }
	~EnhancedSynthEngine();

	//Level-2 routing (ADR-0052): one RawChannel per melodic chip channel, in
	//the wrapper's fixed order; runs the classifier for this flush and fills
	//the Input's Lead/Harmony/Bass slots by role and its Sfx slots with the
	//channels flagged as effects. dt is the flush duration in seconds.
	struct RawChannel
	{
		double Freq = 0;
		double Vol = 0;
		double Width = 0.5;
		bool HwSweep = false;
	};
	static void Route(Input& in, ChannelRoleClassifier& roles, const RawChannel* raw, uint32_t count, double dt);

	//SoundFont to use for the given setting: the configured path if any,
	//else "<Mesen home>/EnhancedAudio.sf2" when that file exists, else "".
	static string ResolveSoundFontPath(const char* configuredPath);

	//F5.4g Bloco B item 3 (ADR-0052): fold a fast periodic arpeggio into a
	//sustained chord. cycleKeys = the 2-4 distinct MIDI notes the channel
	//alternates between at 20-60 Hz (from ChannelRoleClassifier::ArpeggioKeys);
	//writes their frequencies, lowest first, into outFreq[] and returns the
	//chord size (0 when cycleCount == 0 - a single note, no chord).
	static uint32_t FoldArpeggioToChord(const int* cycleKeys, uint32_t cycleCount, double outFreq[MaxChordNotes]);

	//Synthesizes sampleCount stereo samples from the Input snapshot and adds
	//them onto "out" (interleaved L/R). "p" comes from GetPreset();
	//volumePct is the user's synth volume (0-100).
	void Render(int16_t* out, uint32_t sampleCount, uint32_t sampleRate, const Input& in, const EnhancedSynthPreset& p, double volumePct);
};
