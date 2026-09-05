#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/HeadlessInputProvider.h"
#include "Core/Shared/Video/VideoDecoder.h"
#include "Utilities/StringUtilities.h"

//F9.14 (ADR-0157) and F9.15: the DLL surface scripts/headless_record needs to
//drive a recording in emulated frames instead of wall-clock seconds, and to
//read the frame it stopped on without going through Screenshots/. Sibling file to
//EmuApiWrapper.cpp (already at its 200-line-per-file guardrail, see
//EmuApiWrapperMep.cpp for the same call), and all four exports are thin
//marshaling over HeadlessInputProvider - no scheduling logic lives here.

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
}
