#pragma once
#include "pch.h"

//F5.3 (ADR-0047): chip-agnostic building blocks for "BGM/SFX without a ROM
//patch". A console glue (NES: NesAudioFingerprint) reduces its sound chip
//state to one NoteFrame per video frame; from that stream we
//  - segment the recording into tracks and write one MIDI + one fingerprint
//    per track (authoring, during the bootstrap - TrackSegmenter), and
//  - recognise a known track from its first note onsets at run time and
//    tell the host to start the replacement OGG (FingerprintMatcher).
//Nothing here touches files but FingerprintStore / SimpleMidi.

struct NoteFrame
{
	static constexpr int VoiceCount = 4; //lead, harmony, bass, drums
	static constexpr int8_t Rest = -1;
	//MIDI note per voice, Rest when silent. Drums carry a GM percussion note
	//(42 hi-hat / 45 tom) so the same field works for them.
	int8_t Note[VoiceCount] = { Rest, Rest, Rest, Rest };

	bool IsSilent() const
	{
		for(int i = 0; i < VoiceCount; i++) {
			if(Note[i] != Rest) {
				return false;
			}
		}
		return true;
	}
};

//One note onset relative to the track start
struct FingerprintEvent
{
	uint8_t Voice = 0;
	int8_t RelPitch = 0; //semitones from the first melodic onset of the track (drums: 0)
	uint16_t Frame = 0; //frames since the first onset
};

struct AudioFingerprint
{
	string Id; //track01, sfx03... = file stem under bgm/ or sfx/
	string Kind; //"bgm" | "sfx"
	uint32_t Frames = 0; //recorded duration
	vector<FingerprintEvent> Events; //first onsets, at most MaxEvents
	string MidiFile; //relative to the audio folder, may be empty

	static constexpr size_t MaxEvents = 32;
};

class FingerprintStore
{
public:
	//fingerprints.json: { "version": 1, "tracks": [ { "id", "kind", "frames", "midi", "events": [[voice, relPitch, frame], ...] } ] }
	static bool Load(const string& path, vector<AudioFingerprint>& out, string& error);
	static bool Save(const string& path, const vector<AudioFingerprint>& tracks);
};

//Writes a type-1 SMF from a note-frame stream (one track per voice, drums
//on channel 10). 60 frames = 1 s; 120 bpm / 480 tpqn => 16 ticks per frame.
class SimpleMidi
{
public:
	static bool Write(const string& path, const vector<NoteFrame>& frames);
};

//Authoring: cuts the stream at silences and builds fingerprints + MIDI files
class TrackSegmenter
{
public:
	struct Segment
	{
		uint32_t StartFrame = 0;
		vector<NoteFrame> Frames;
		AudioFingerprint Fingerprint;
	};

private:
	static constexpr uint32_t SilenceEndFrames = 60; //1 s of silence closes a segment
	static constexpr uint32_t MinBgmFrames = 180; //>= 3 s => bgm, shorter => sfx
	static constexpr uint32_t MinKeepFrames = 6; //shorter bursts are noise

	uint32_t _frame = 0;
	uint32_t _silentRun = 0;
	bool _open = false;
	Segment _current;
	vector<Segment> _done;
	uint32_t _bgmCount = 0;
	uint32_t _sfxCount = 0;

	void Close();

public:
	static void ExtractEvents(const vector<NoteFrame>& frames, vector<FingerprintEvent>& out);

	void Feed(const NoteFrame& frame);
	void Finish() { Close(); }
	vector<Segment>& GetSegments() { return _done; }

	//Writes <folder>/fingerprints.json and <folder>/midi/<id>.mid for every
	//segment; returns the number of tracks written
	uint32_t Save(const string& audioFolder);
};

//Run time: recognises the start of a known track
class FingerprintMatcher
{
private:
	struct Cursor
	{
		size_t Next = 0; //next fingerprint event expected
		uint32_t StartFrame = 0; //live frame matched to event 0
		int8_t BasePitch = 0; //live pitch of the first melodic onset
	};

	static constexpr uint32_t FrameTolerance = 3;
	static constexpr size_t ConfirmEvents = 8; //onsets that must line up before we trust a match
	static constexpr uint32_t SilenceStopFrames = 90; //1.5 s of silence => "track ended"

	vector<AudioFingerprint> _tracks;
	vector<Cursor> _cursors;
	NoteFrame _last;
	uint32_t _frame = 0;
	uint32_t _silentRun = 0;
	int _playing = -1;

	void ResetCursor(size_t i) { _cursors[i] = Cursor(); }

public:
	void SetTracks(const vector<AudioFingerprint>& tracks);
	const vector<AudioFingerprint>& GetTracks() const { return _tracks; }
	bool HasTracks() const { return !_tracks.empty(); }

	//Feeds one frame. Returns the index of a freshly confirmed track, -2 when
	//the music stopped (silence) while something was playing, -1 otherwise.
	int Feed(const NoteFrame& frame);
	void SetPlaying(int index) { _playing = index; }
	int GetPlaying() const { return _playing; }
	uint32_t GetFrame() const { return _frame; }
};
