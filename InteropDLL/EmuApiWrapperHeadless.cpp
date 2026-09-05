#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/HeadlessInputProvider.h"
#include "Utilities/StringUtilities.h"

//F9.14 (ADR-0157): the DLL surface scripts/headless_record needs to drive a
//recording in emulated frames instead of wall-clock seconds. Sibling file to
//EmuApiWrapper.cpp (already at its 200-line-per-file guardrail, see
//EmuApiWrapperMep.cpp for the same call), and all four exports are thin
//marshaling over HeadlessInputProvider - no scheduling logic lives here.

extern unique_ptr<Emulator> _emu;

//Kept alive for the process' lifetime: NotificationManager holds listeners by
//weak_ptr, so dropping this would silently unsubscribe the provider from
//GameLoaded and reintroduce the "input= is a no-op after a game load" trap.
static shared_ptr<HeadlessInputProvider> _headlessInput;

static HeadlessInputProvider* GetHeadlessInput()
{
	if(!_headlessInput) {
		_headlessInput.reset(new HeadlessInputProvider(_emu.get()));
		_headlessInput->Init();
	}
	return _headlessInput.get();
}

extern "C"
{
	//scriptText is the whole script file; frameRate resolves its 's' steps
	//(NTSC 60.0988 / PAL 50.0070 - the caller knows which region it forced).
	//Returns false and writes an en-US message naming the offending line into
	//outError when the script does not parse.
	DllExport bool __stdcall HeadlessLoadInputScript(const char* scriptText, double frameRate, char* outError, uint32_t maxErrorLength)
	{
		string error;
		bool success = GetHeadlessInput()->LoadScript(scriptText ? scriptText : "", frameRate, error);
		StringUtilities::CopyToBuffer(error, outError, maxErrorLength);
		return success;
	}

	//Pause the emulator from inside the first frame whose number reaches
	//'frame' (UINT32_MAX never pauses). This is how the harness stops a run on
	//an exact frame count rather than on elapsed host time.
	DllExport void __stdcall HeadlessSetPauseFrame(uint32_t frame)
	{
		GetHeadlessInput()->SetPauseFrame(frame);
	}

	//Length of the loaded script, in frames.
	DllExport uint32_t __stdcall HeadlessGetScriptFrameCount()
	{
		return GetHeadlessInput()->GetScriptFrameCount();
	}

	//The core's own frame counter - the cross-check that the harness' frame
	//budget and the emulated console agree (ADR-0157 section 4).
	DllExport uint32_t __stdcall HeadlessGetFrameCount()
	{
		return _emu->GetFrameCount();
	}
}
