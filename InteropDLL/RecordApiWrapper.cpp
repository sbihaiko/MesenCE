#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/Video/VideoRenderer.h"
#include "Core/Shared/Audio/SoundMixer.h"
#include "Core/Shared/Movies/MovieManager.h"
#include "Core/Shared/LiveFrameRecorder.h"

extern unique_ptr<Emulator> _emu;

extern "C"
{
	DllExport void __stdcall AviRecord(char* filename, RecordAviOptions options)
	{
		_emu->GetVideoRenderer()->StartRecording(filename, options);
	}

	DllExport void __stdcall AviStop()
	{
		_emu->GetVideoRenderer()->StopRecording();
	}

	DllExport bool __stdcall AviIsRecording()
	{
		return _emu->GetVideoRenderer()->IsRecording();
	}

	DllExport void __stdcall WaveRecord(char* filename)
	{
		_emu->GetSoundMixer()->StartRecording(filename);
	}

	DllExport void __stdcall WaveStop()
	{
		_emu->GetSoundMixer()->StopRecording();
	}

	DllExport bool __stdcall WaveIsRecording()
	{
		return _emu->GetSoundMixer()->IsRecording();
	}

	//Music-capture start/stop mutate exporter instances the emulation thread
	//reads through plain pointer loads (see SoundMixer::GetVgmExporter), so
	//they take the emulator lock to pause emulation for the swap (ADR-0012).
	DllExport void __stdcall MidiRecord(char* filename)
	{
		auto lock = _emu->AcquireLock();
		_emu->GetSoundMixer()->StartMidiRecording(filename);
	}

	DllExport void __stdcall MidiStop()
	{
		auto lock = _emu->AcquireLock();
		_emu->GetSoundMixer()->StopMidiRecording();
	}

	DllExport bool __stdcall MidiIsRecording()
	{
		return _emu->GetSoundMixer()->IsMidiRecording();
	}

	DllExport void __stdcall VgmRecord(char* filename)
	{
		auto lock = _emu->AcquireLock();
		_emu->GetSoundMixer()->StartVgmRecording(filename);
	}

	DllExport void __stdcall VgmStop()
	{
		auto lock = _emu->AcquireLock();
		_emu->GetSoundMixer()->StopVgmRecording();
	}

	DllExport bool __stdcall VgmIsRecording()
	{
		return _emu->GetSoundMixer()->IsVgmRecording();
	}

	DllExport void __stdcall MoviePlay(char* filename)
	{
		_emu->GetMovieManager()->Play(string(filename));
	}

	DllExport void __stdcall MovieStop()
	{
		_emu->GetMovieManager()->Stop();
	}

	DllExport bool __stdcall MoviePlaying()
	{
		return _emu->GetMovieManager()->Playing();
	}

	DllExport bool __stdcall MovieRecording()
	{
		return _emu->GetMovieManager()->Recording();
	}

	DllExport void __stdcall MovieRecord(RecordMovieOptions options)
	{
		_emu->GetMovieManager()->Record(options);
	}

	//Live recording (ADR-0169's interactive producer): publishes frames + the
	//sprite layer from the running emulator to liveDir, while a human plays with
	//a real controller. Start/stop here never take the emulator lock - the
	//recorder's own thread acquires it briefly per published frame. liveDir is a
	//UTF-8 path.
	DllExport bool __stdcall LiveRecordingStart(char* liveDir, int intervalMs)
	{
		return _emu->GetLiveFrameRecorder()->StartRecording(string(liveDir), intervalMs);
	}

	DllExport void __stdcall LiveRecordingStop()
	{
		_emu->GetLiveFrameRecorder()->StopRecording();
	}

	DllExport bool __stdcall LiveRecordingIsRecording()
	{
		return _emu->GetLiveFrameRecorder()->IsRecording();
	}

	//The ROM the live session is now showing, announced by the UI on every
	//game load (and on start). The recorder re-targets its slot on a change -
	//see LiveFrameRecorder::SetRomName. romName is UTF-8, empty for "no game".
	DllExport void __stdcall LiveRecordingSetRom(char* romName)
	{
		_emu->GetLiveFrameRecorder()->SetRomName(romName ? string(romName) : string());
	}
}