#pragma once
#include "pch.h"
#include <thread>
#include <atomic>
#include "Utilities/SimpleLock.h"
#include "Utilities/Timer.h"

class Emulator;
struct LiveSnapshot;

//ADR-0169's other producer: the interactive UI, publishing while a human
//plays with a real gamepad, instead of scripts/headless_record's scripted
//run. Same wire format (Utilities/LiveRecordFormat.h), same lossy-latest
//atomic-swap contract (section 1) - only the driver differs. Owned by
//Emulator (GetLiveFrameRecorder()), one instance per emulator, imitating
//VideoRenderer's own start/stop-thread pattern.
//
//Runs its own timer thread rather than hooking VideoRenderer::UpdateFrame:
//the NES sprite-layer read holds the emulation thread with Emulator::Lock()
//(same mechanism scripts/headless_record uses from its own, equally
//independent, main thread - Context bullet 3 of ADR-0169), and doing that
//from the video decode thread instead would tie an unproven wait into the
//render pipeline's own thread for no benefit. A dedicated thread keeps the
//risk identical to the already-measured headless case.
class LiveFrameRecorder
{
private:
	Emulator* _emu;

	unique_ptr<std::thread> _thread;
	std::atomic<bool> _stopFlag;
	SimpleLock _stopStartLock;

	string _liveDir;
	int _intervalMs = 0;
	Timer _wallClock;

	//The run's 64-color RGB table (palette.json), captured once from the NES
	//config on the first sprite read and immutable for the run. Empty until a
	//NES console yields the first capture.
	string _paletteJson;

	//Last published LiveSnapshot::HdPackActive, so the final "stopped" status
	//StopRecording() writes (which has no snapshot in hand) keeps saying it.
	std::atomic<bool> _hdPackActive{false};

	//The ROM the published frames belong to, and the one the UI last announced
	//(SetRomName, from its GameLoaded handler). The two differ for exactly one
	//tick after the human opens a different game, which is what ThreadLoop
	//re-targets the slot on. Both go through _romLock rather than being
	//compared raw across the two threads; and the UI hands the name over
	//instead of the recorder reading Emulator::GetRomInfo() itself, because
	//that returns a reference to a string InternalLoadRom reassigns while this
	//thread is running.
	SimpleLock _romLock;
	string _romName;
	string _announcedRomName;

	void ThreadLoop();

	//Empties the convention slot of the whole publish set before a run starts -
	//see the implementation's comment for the cross-ROM contamination this
	//prevents (a leftover chrlatch.json/chrfull.bin sending the viewer down the
	//CHR-latch path with the previous ROM's data).
	void ClearSlot(const string& liveDir);

	//Fills 'snapshot' from whatever the console has decoded/holds right now.
	//Returns false when nothing has been decoded yet (snapshot.Width/Height
	//stay 0) - the caller skips publishing that tick rather than writing a
	//blank frame.
	bool CaptureSnapshot(LiveSnapshot& snapshot);

public:
	LiveFrameRecorder(Emulator* emu);
	~LiveFrameRecorder();

	//liveDir is created if missing. intervalMs below 50 is rejected (same
	//floor as headless_record's live=<ms>, ADR-0169 Consequences bullet 2 -
	//below it the capture+publish itself costs more than the interval).
	bool StartRecording(string liveDir, int intervalMs);
	void StopRecording();
	bool IsRecording();

	//The ROM currently open, as the UI knows it (RecordApiWrapper's
	//LiveRecordingSetRom, called when a game loads and when a session starts).
	//A live session outlives the game that started it - the human keeps
	//playing and opens something else - so the recorder is told, rather than
	//publishing the previous ROM's identity over the new game's frames. Empty
	//means "no game open"; safe to call whether or not a recording is running.
	void SetRomName(string romName);
};
