#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/HeadlessInputProvider.h"
#include "Core/Shared/MessageManager.h"
#include "Core/Shared/Video/VideoDecoder.h"
#include "Core/Shared/Video/VideoRenderer.h"
#include "Core/Shared/Video/FrameCapture.h"
#include "Utilities/StringUtilities.h"

//F9.14 (ADR-0157), F9.15 and ADR-0167: the DLL surface scripts/headless_record
//needs to drive a recording in emulated frames instead of wall-clock seconds,
//read the frame it stopped on without going through Screenshots/, capture the
//system HUD alone, and gate the OSD message queue. Sibling file to
//EmuApiWrapper.cpp (already at its 200-line-per-file guardrail, see
//EmuApiWrapperMep.cpp for the same call). The input exports are thin
//marshaling over HeadlessInputProvider; the capture and OSD exports marshal
//over VideoRenderer/MessageManager directly - no scheduling logic lives here.

extern unique_ptr<Emulator> _emu;

//Kept alive for the process' lifetime: NotificationManager holds listeners by
//weak_ptr, so dropping this would silently unsubscribe the provider from
//GameLoaded and reintroduce the "input= is a no-op after a game load" trap.
static shared_ptr<HeadlessInputProvider> _headlessInput;

//F9.15: the last capture taken by HeadlessCaptureFrame, kept here so the
//harness can ask for its size and then read the pixels of *that* capture -
//a second call into the emulator would answer about a different frame.
static vector<uint32_t> _headlessCapture;
static ScreenshotCapture _headlessCaptureInfo;

//ADR-0167: the last capture taken by HeadlessCaptureHud, same one-buffer-at-a-
//time rule as _headlessCapture above.
static vector<uint32_t> _headlessHudCapture;

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

	//Capture the frame the emulator is currently showing into the DLL-side
	//buffer, filtered exactly like a saved screenshot would be. Returns false
	//when nothing has been decoded yet; the out parameters are always written.
	DllExport bool __stdcall HeadlessCaptureFrame(uint32_t* outWidth, uint32_t* outHeight, uint32_t* outFrameNumber, uint32_t* outPixelCount)
	{
		_headlessCaptureInfo = _emu->GetVideoDecoder()->CaptureScreenshot(_headlessCapture);
		if(outWidth) { *outWidth = _headlessCaptureInfo.Width; }
		if(outHeight) { *outHeight = _headlessCaptureInfo.Height; }
		if(outFrameNumber) { *outFrameNumber = _headlessCaptureInfo.FrameNumber; }
		if(outPixelCount) { *outPixelCount = (uint32_t)_headlessCapture.size(); }
		return !_headlessCaptureInfo.IsEmpty();
	}

	//Copy the pixels of the last HeadlessCaptureFrame into the caller's
	//buffer, 0xAARRGGBB, row-major. Returns how many pixels were copied
	//(never more than maxPixels, never more than the capture holds).
	DllExport uint32_t __stdcall HeadlessReadCapturedPixels(uint32_t* outPixels, uint32_t maxPixels)
	{
		if(!outPixels || _headlessCapture.empty()) {
			return 0;
		}
		uint32_t count = std::min(maxPixels, (uint32_t)_headlessCapture.size());
		memcpy(outPixels, _headlessCapture.data(), (size_t)count * sizeof(uint32_t));
		return count;
	}

	//ADR-0167: draw the system HUD alone (no game frame under it) into the
	//DLL-side buffer, at the caller-chosen size - unlike HeadlessCaptureFrame
	//there is no filter pipeline deciding the size, so the caller supplies one
	//(typically the base frame size) instead of reading it back. Returns false
	//on a degenerate size (zero, or over FrameCaptureMath::MaxCapturePixels)
	//without touching the emulator; the out parameters are always written.
	DllExport bool __stdcall HeadlessCaptureHud(uint32_t width, uint32_t height, uint32_t* outWidth, uint32_t* outHeight, uint32_t* outPixelCount)
	{
		uint64_t total = (uint64_t)width * (uint64_t)height;
		bool valid = width != 0 && height != 0 && total <= FrameCaptureMath::MaxCapturePixels;
		if(valid) {
			_emu->GetVideoRenderer()->CaptureSystemHud(width, height, _headlessHudCapture);
		} else {
			_headlessHudCapture.clear();
		}
		if(outWidth) { *outWidth = valid ? width : 0; }
		if(outHeight) { *outHeight = valid ? height : 0; }
		if(outPixelCount) { *outPixelCount = (uint32_t)_headlessHudCapture.size(); }
		return valid;
	}

	//Copy the pixels of the last HeadlessCaptureHud into the caller's buffer,
	//same contract as HeadlessReadCapturedPixels (0xAARRGGBB, row-major, never
	//more than maxPixels or the capture's own size).
	DllExport uint32_t __stdcall HeadlessReadCapturedHudPixels(uint32_t* outPixels, uint32_t maxPixels)
	{
		if(!outPixels || _headlessHudCapture.empty()) {
			return 0;
		}
		uint32_t count = std::min(maxPixels, (uint32_t)_headlessHudCapture.size());
		memcpy(outPixels, _headlessHudCapture.data(), (size_t)count * sizeof(uint32_t));
		return count;
	}

	//ADR-0167: gate MessageManager's OSD queue. With the OSD enabled (the
	//default), a ROM load enqueues a "game loaded" toast (Emulator.cpp) that
	//never ages out of a short headless run - UpdateHud only drops expired
	//messages on running frames, and the harness parks the emulator within a
	//few frames of load. That toast would make a HUD capture read non-blank
	//whether or not a message was queued, so the harness disables the OSD for
	//the load/run, then enables it for the instant it queues the one toast a
	//test wants to see. MessageManager::SetOptions also sets outputToStdout;
	//this keeps it false (the harness never enables stdout logging, and the
	//core's Log() lines would otherwise pollute the parsed capture output).
	DllExport void __stdcall HeadlessSetOsdEnabled(bool osdEnabled)
	{
		MessageManager::SetOptions(osdEnabled, false);
	}
}
