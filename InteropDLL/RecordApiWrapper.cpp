#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/Video/VideoRenderer.h"
#include "Core/Shared/Audio/SoundMixer.h"
#include "Core/Shared/Movies/MovieManager.h"

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
}