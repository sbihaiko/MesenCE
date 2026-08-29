#include "pch.h"
#include <filesystem>
#include "Shared/EnhancementPacks/AudioFingerprint.h"
#include "Shared/Audio/SmfWriter.h"
#include "Utilities/JsonReader.h"
#include "Utilities/FolderUtilities.h"

namespace fs = std::filesystem;

//---------------------------------------------------------------------------
// FingerprintStore
//---------------------------------------------------------------------------
bool FingerprintStore::Load(const string& path, vector<AudioFingerprint>& out, string& error)
{
	ifstream file(path, std::ios::in | std::ios::binary);
	if(!file) {
		error = "cannot open " + path;
		return false;
	}
	std::stringstream ss;
	ss << file.rdbuf();

	JsonReader reader;
	JsonValue root;
	if(!reader.Parse(ss.str(), root) || !root.IsObject()) {
		error = "fingerprints.json is not valid JSON: " + reader.GetError();
		return false;
	}
	const JsonValue* tracks = root.Get("tracks");
	if(!tracks || !tracks->IsArray()) {
		error = "fingerprints.json: 'tracks' must be an array";
		return false;
	}
	for(const JsonValue& entry : tracks->GetArray()) {
		if(!entry.IsObject()) {
			continue;
		}
		AudioFingerprint fp;
		fp.Id = entry.GetString("id");
		fp.Kind = entry.GetString("kind", "bgm");
		fp.MidiFile = entry.GetString("midi");
		//F5.4g Block C item 8 (ADR-0134 Option A): optional loop point, PCM
		//samples at the OGG's own rate; absent or invalid falls back to 0.
		const JsonValue* loop = entry.Get("loop");
		if(loop && loop->IsNumber()) {
			double l = loop->GetNumber();
			fp.Loop = l > 0 ? (uint32_t)l : 0;
		}
		const JsonValue* frames = entry.Get("frames");
		if(frames && frames->IsNumber()) {
			fp.Frames = (uint32_t)frames->GetNumber();
		}
		const JsonValue* events = entry.Get("events");
		if(fp.Id.empty() || !events || !events->IsArray()) {
			continue;
		}
		for(const JsonValue& ev : events->GetArray()) {
			if(!ev.IsArray() || ev.GetArray().size() < 3) {
				continue;
			}
			const auto& v = ev.GetArray();
			if(!v[0].IsNumber() || !v[1].IsNumber() || !v[2].IsNumber()) {
				continue;
			}
			FingerprintEvent e;
			e.Voice = (uint8_t)std::min<double>(NoteFrame::VoiceCount - 1, std::max<double>(0, v[0].GetNumber()));
			e.RelPitch = (int8_t)std::max<double>(-127, std::min<double>(127, v[1].GetNumber()));
			e.Frame = (uint16_t)std::max<double>(0, std::min<double>(65535, v[2].GetNumber()));
			fp.Events.push_back(e);
			if(fp.Events.size() >= AudioFingerprint::MaxEvents) {
				break;
			}
		}
		if(!fp.Events.empty()) {
			out.push_back(fp);
		}
	}
	return true;
}

bool FingerprintStore::Save(const string& path, const vector<AudioFingerprint>& tracks)
{
	ofstream out(path, std::ios::out | std::ios::binary);
	if(!out) {
		return false;
	}
	out << "{\n  \"version\": 1,\n  \"tracks\": [";
	for(size_t i = 0; i < tracks.size(); i++) {
		const AudioFingerprint& fp = tracks[i];
		out << (i ? ",\n" : "\n") << "    { \"id\": \"" << fp.Id << "\", \"kind\": \"" << fp.Kind << "\", \"frames\": " << fp.Frames;
		//F5.4g Block C item 8 (ADR-0134 Option A): emit the loop point only
		//when non-zero, so a track that loops the whole file stays schema-minimal.
		if(fp.Loop > 0) {
			out << ", \"loop\": " << fp.Loop;
		}
		if(!fp.MidiFile.empty()) {
			out << ", \"midi\": \"" << fp.MidiFile << "\"";
		}
		out << ", \"events\": [";
		for(size_t j = 0; j < fp.Events.size(); j++) {
			const FingerprintEvent& e = fp.Events[j];
			out << (j ? ", " : "") << "[" << (int)e.Voice << ", " << (int)e.RelPitch << ", " << e.Frame << "]";
		}
		out << "] }";
	}
	out << "\n  ]\n}\n";
	return true;
}

//---------------------------------------------------------------------------
// SimpleMidi
//---------------------------------------------------------------------------
bool SimpleMidi::Write(const string& path, const vector<NoteFrame>& frames)
{
	constexpr uint16_t tpqn = 480;
	constexpr uint32_t ticksPerFrame = 16; //120 bpm: 960 ticks/s / 60 fps
	constexpr uint8_t channelForVoice[NoteFrame::VoiceCount] = { 0, 1, 2, 9 };
	constexpr uint8_t programForVoice[NoteFrame::VoiceCount] = { 80, 81, 38, 0 }; //GM: square lead, saw lead, synth bass, (drums)

	SmfWriter writer(NoteFrame::VoiceCount, tpqn);
	writer.SetCurrentTick(0);
	writer.EmitMeta(0, 0x51, { 0x07, 0xA1, 0x20 }); //500000 us per quarter = 120 bpm
	for(int v = 0; v < NoteFrame::VoiceCount; v++) {
		if(v != 3) {
			writer.EmitEvent(v, 0xC0 | channelForVoice[v], programForVoice[v]);
		}
	}

	int8_t held[NoteFrame::VoiceCount] = { NoteFrame::Rest, NoteFrame::Rest, NoteFrame::Rest, NoteFrame::Rest };
	for(size_t f = 0; f < frames.size(); f++) {
		writer.SetCurrentTick((uint32_t)f * ticksPerFrame);
		for(int v = 0; v < NoteFrame::VoiceCount; v++) {
			int8_t note = frames[f].Note[v];
			if(note == held[v]) {
				//Drums retrigger every frame they are audible only on onset; keep held
				continue;
			}
			if(held[v] != NoteFrame::Rest) {
				writer.EmitEvent(v, 0x80 | channelForVoice[v], (uint8_t)held[v], 0);
			}
			if(note != NoteFrame::Rest) {
				writer.EmitEvent(v, 0x90 | channelForVoice[v], (uint8_t)note, 100);
			}
			held[v] = note;
		}
	}
	writer.SetCurrentTick((uint32_t)frames.size() * ticksPerFrame);
	for(int v = 0; v < NoteFrame::VoiceCount; v++) {
		if(held[v] != NoteFrame::Rest) {
			writer.EmitEvent(v, 0x80 | channelForVoice[v], (uint8_t)held[v], 0);
		}
	}

	ofstream out(path, std::ios::out | std::ios::binary);
	if(!out) {
		return false;
	}
	return writer.Write(out);
}

//---------------------------------------------------------------------------
// TrackSegmenter
//---------------------------------------------------------------------------
void TrackSegmenter::ExtractEvents(const vector<NoteFrame>& frames, vector<FingerprintEvent>& out)
{
	out.clear();
	int8_t prev[NoteFrame::VoiceCount] = { NoteFrame::Rest, NoteFrame::Rest, NoteFrame::Rest, NoteFrame::Rest };
	int basePitch = 1000;
	int32_t firstFrame = -1;
	for(size_t f = 0; f < frames.size() && out.size() < AudioFingerprint::MaxEvents; f++) {
		for(int v = 0; v < NoteFrame::VoiceCount; v++) {
			int8_t note = frames[f].Note[v];
			bool onset = note != NoteFrame::Rest && note != prev[v];
			prev[v] = note;
			if(!onset) {
				continue;
			}
			if(firstFrame < 0) {
				firstFrame = (int32_t)f;
			}
			if(v != 3 && basePitch == 1000) {
				basePitch = note;
			}
			FingerprintEvent e;
			e.Voice = (uint8_t)v;
			e.RelPitch = v == 3 ? 0 : (int8_t)(basePitch == 1000 ? 0 : note - basePitch);
			e.Frame = (uint16_t)std::min<size_t>(65535, f - firstFrame);
			out.push_back(e);
			if(out.size() >= AudioFingerprint::MaxEvents) {
				break;
			}
		}
	}
}

void TrackSegmenter::Feed(const NoteFrame& frame)
{
	_frame++;
	if(frame.IsSilent()) {
		if(_open) {
			_silentRun++;
			_current.Frames.push_back(frame);
			if(_silentRun >= SilenceEndFrames) {
				//Trim the trailing silence, keep the track
				_current.Frames.resize(_current.Frames.size() - _silentRun);
				Close();
			}
		}
		return;
	}
	if(!_open) {
		_open = true;
		_current = Segment();
		_current.StartFrame = _frame;
	}
	_silentRun = 0;
	_current.Frames.push_back(frame);
}

void TrackSegmenter::Close()
{
	if(!_open) {
		return;
	}
	_open = false;
	_silentRun = 0;
	if(_current.Frames.size() < MinKeepFrames) {
		return;
	}
	AudioFingerprint& fp = _current.Fingerprint;
	ExtractEvents(_current.Frames, fp.Events);
	if(fp.Events.empty()) {
		return;
	}
	fp.Frames = (uint32_t)_current.Frames.size();
	bool bgm = fp.Frames >= MinBgmFrames;
	fp.Kind = bgm ? "bgm" : "sfx";
	char id[32];
	snprintf(id, sizeof(id), "%s%02u", bgm ? "track" : "sfx", bgm ? ++_bgmCount : ++_sfxCount);
	fp.Id = id;
	fp.MidiFile = string("midi/") + id + ".mid";
	_done.push_back(std::move(_current));
	_current = Segment();
}

uint32_t TrackSegmenter::Save(const string& audioFolder)
{
	Close();
	if(_done.empty()) {
		return 0;
	}
	std::error_code ec;
	fs::create_directories(fs::u8path(FolderUtilities::CombinePath(audioFolder, "midi")), ec);
	fs::create_directories(fs::u8path(FolderUtilities::CombinePath(audioFolder, "bgm")), ec);
	fs::create_directories(fs::u8path(FolderUtilities::CombinePath(audioFolder, "sfx")), ec);

	//Merge with what an earlier session recorded: known ids are kept, new
	//tracks whose fingerprint already exists are dropped
	vector<AudioFingerprint> tracks;
	string error;
	string jsonPath = FolderUtilities::CombinePath(audioFolder, "fingerprints.json");
	FingerprintStore::Load(jsonPath, tracks, error);
	uint32_t bgmMax = 0;
	uint32_t sfxMax = 0;
	for(const AudioFingerprint& t : tracks) {
		uint32_t n = (uint32_t)atoi(t.Id.c_str() + (t.Kind == "bgm" ? 5 : 3));
		(t.Kind == "bgm" ? bgmMax : sfxMax) = std::max(t.Kind == "bgm" ? bgmMax : sfxMax, n);
	}

	uint32_t written = 0;
	for(Segment& seg : _done) {
		bool duplicate = false;
		for(const AudioFingerprint& t : tracks) {
			if(t.Kind == seg.Fingerprint.Kind && t.Events.size() == seg.Fingerprint.Events.size()) {
				bool same = true;
				for(size_t i = 0; i < t.Events.size() && same; i++) {
					same = t.Events[i].Voice == seg.Fingerprint.Events[i].Voice && t.Events[i].RelPitch == seg.Fingerprint.Events[i].RelPitch && (uint32_t)std::abs((int)t.Events[i].Frame - (int)seg.Fingerprint.Events[i].Frame) <= 2;
				}
				duplicate = same;
				if(duplicate) {
					break;
				}
			}
		}
		if(duplicate) {
			continue;
		}
		bool bgm = seg.Fingerprint.Kind == "bgm";
		char id[32];
		snprintf(id, sizeof(id), "%s%02u", bgm ? "track" : "sfx", bgm ? ++bgmMax : ++sfxMax);
		seg.Fingerprint.Id = id;
		seg.Fingerprint.MidiFile = string("midi/") + id + ".mid";
		if(SimpleMidi::Write(FolderUtilities::CombinePath(audioFolder, seg.Fingerprint.MidiFile), seg.Frames)) {
			tracks.push_back(seg.Fingerprint);
			written++;
		}
	}
	if(written > 0) {
		FingerprintStore::Save(jsonPath, tracks);
	}
	return written;
}

//---------------------------------------------------------------------------
// FingerprintMatcher
//---------------------------------------------------------------------------
void FingerprintMatcher::SetTracks(const vector<AudioFingerprint>& tracks)
{
	_tracks = tracks;
	_cursors.assign(_tracks.size(), Cursor());
	_playing = -1;
	_frame = 0;
	_silentRun = 0;
	_last = NoteFrame();
}

int FingerprintMatcher::Feed(const NoteFrame& frame)
{
	_frame++;
	int result = -1;

	if(frame.IsSilent()) {
		_silentRun++;
		if(_playing >= 0 && _silentRun >= SilenceStopFrames) {
			_playing = -1;
			result = -2;
		}
	} else {
		_silentRun = 0;
	}

	//Onsets this frame, in voice order
	for(int v = 0; v < NoteFrame::VoiceCount && result == -1; v++) {
		int8_t note = frame.Note[v];
		bool onset = note != NoteFrame::Rest && note != _last.Note[v];
		if(!onset) {
			continue;
		}
		for(size_t i = 0; i < _tracks.size(); i++) {
			if((int)i == _playing || _tracks[i].Kind != "bgm") {
				continue;
			}
			const vector<FingerprintEvent>& ev = _tracks[i].Events;
			Cursor& c = _cursors[i];
			if(c.Next == 0) {
				//Any onset on the right voice may start the track
				if(ev[0].Voice == (uint8_t)v) {
					c.Next = 1;
					c.StartFrame = _frame;
					c.BasePitch = v == 3 ? 0 : note;
					if(ev.size() == 1) {
						result = (int)i;
					}
				}
				continue;
			}
			const FingerprintEvent& expected = ev[c.Next];
			uint32_t expectedFrame = c.StartFrame + expected.Frame;
			bool voiceOk = expected.Voice == (uint8_t)v;
			bool pitchOk = v == 3 || (int)note - (int)c.BasePitch == (int)expected.RelPitch;
			bool timeOk = _frame + FrameTolerance >= expectedFrame && _frame <= expectedFrame + FrameTolerance;
			if(voiceOk && pitchOk && timeOk) {
				c.Next++;
				if(c.Next >= std::min(ConfirmEvents, ev.size())) {
					result = (int)i;
				}
			} else if(_frame > expectedFrame + FrameTolerance || (voiceOk && !pitchOk)) {
				//Missed the expected onset: restart, this onset may be a new start
				ResetCursor(i);
				if(ev[0].Voice == (uint8_t)v) {
					c.Next = 1;
					c.StartFrame = _frame;
					c.BasePitch = v == 3 ? 0 : note;
				}
			}
			//Onsets on other voices (SFX, unrelated) are ignored while waiting
		}
	}

	if(result >= 0) {
		for(size_t i = 0; i < _cursors.size(); i++) {
			ResetCursor(i);
		}
		_playing = result;
	}
	_last = frame;
	return result;
}
