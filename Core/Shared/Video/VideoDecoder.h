#pragma once
#include "pch.h"
#include "Utilities/SimpleLock.h"
#include "Utilities/AutoResetEvent.h"
#include "Shared/SettingTypes.h"
#include "Shared/RenderedFrame.h"
#include "Shared/Video/FrameCapture.h"

class BaseVideoFilter;
class ScaleFilter;
class RotateFilter;
class IRenderingDevice;
class Emulator;

class VideoDecoder
{
private:
	Emulator* _emu;

	ConsoleType _consoleType = ConsoleType::Snes;

	unique_ptr<thread> _decodeThread;

	SimpleLock _stopStartLock;
	AutoResetEvent _waitForFrame;

	atomic<bool> _frameChanged;
	atomic<bool> _stopFlag;
	uint32_t _frameCount = 0;
	bool _forceFilterUpdate = false;

	double _lastAspectRatio = 0.0;

	FrameInfo _baseFrameSize = {};
	FrameInfo _lastFrameSize = {};
	RenderedFrame _frame = {};

	VideoFilterType _videoFilterType = VideoFilterType::None;
	unique_ptr<BaseVideoFilter> _videoFilter;
	unique_ptr<ScaleFilter> _scaleFilter;
	unique_ptr<RotateFilter> _rotateFilter;

	void UpdateVideoFilter();

	void DecodeThread();

public:
	VideoDecoder(Emulator* console);
	~VideoDecoder();

	void Init();

	void DecodeFrame(bool synchronous = false);
	void TakeScreenshot(string romName = "");
	void TakeScreenshot(std::stringstream& stream);

	//F9.15: the same screenshot, kept in memory. `out` is the caller's; the
	//returned capture is empty when no filter/frame exists yet.
	ScreenshotCapture CaptureScreenshot(vector<uint32_t>& out);

	void ForceFilterUpdate() { _forceFilterUpdate = true; }

	uint32_t GetFrameCount();
	FrameInfo GetBaseFrameInfo(bool removeOverscan);
	FrameInfo GetFrameInfo();
	double GetLastFrameScale() { return _frame.Scale; }

	void UpdateFrame(RenderedFrame frame, bool sync, bool forRewind);

	void WaitForAsyncFrameDecode();

	bool IsRunning();
	void StartThread();
	void StopThread();
};