#pragma once
#include "pch.h"
#include <thread>
#include "Shared/SettingTypes.h"
#include "Shared/RenderedFrame.h"
#include "Shared/Interfaces/IRenderingDevice.h"
#include "Shared/Video/BorderLayout.h"
#include "Utilities/AutoResetEvent.h"
#include "Utilities/SimpleLock.h"
#include "Utilities/safe_ptr.h"

class IRenderingDevice;
class Emulator;
class SystemHud;
class DebugHud;
class InputHud;

class IVideoRecorder;
class INotificationListener;
enum class VideoCodec;

struct RecordAviOptions
{
	VideoCodec Codec;
	uint32_t CompressionLevel;
	bool RecordSystemHud;
	bool RecordInputHud;
};

class VideoRenderer
{
private:
	Emulator* _emu;

	AutoResetEvent _waitForRender;
	unique_ptr<std::thread> _renderThread;
	IRenderingDevice* _renderer = nullptr;
	atomic<bool> _stopFlag;
	SimpleLock _stopStartLock;

	uint32_t _rendererWidth = 512;
	uint32_t _rendererHeight = 480;

	unique_ptr<DebugHud> _rendererHud;
	unique_ptr<SystemHud> _systemHud;
	unique_ptr<InputHud> _inputHud;
	SimpleLock _hudLock;

	RenderSurfaceInfo _aviRecorderSurface = {};
	RecordAviOptions _recorderOptions = {};

	RenderSurfaceInfo _emuHudSurface = {};
	RenderSurfaceInfo _scriptHudSurface = {};
	bool _needScriptHudClear = false;
	uint32_t _scriptHudScale = 2;
	uint32_t _lastScriptHudFrameNumber = 0;
	bool _needRedraw = true;

	//ADR-0149 (F8): border layer cache & compositing state. All of it is
	//owned by the decode thread (UpdateFrame); the only cross-thread member is
	//_borderDirty, set by the notification listener below when the active
	//pack may have changed (GameLoaded / BeforeGameUnload / EmulationStopped)
	//and consumed by UpdateBorderAsset. The border folder is therefore
	//resolved through MepPackManager only on those events, never per frame:
	//the per-frame path touches no MepPackManager state and builds no
	//strings. The remaining window - a load-time read racing LoadForRom on
	//the emulation thread - is the one that existed before, for those two
	//events only.
	std::atomic<bool> _borderDirty { true };
	shared_ptr<INotificationListener> _borderListener;
	string _borderPackFolder;
	bool _borderAvailable = false;
	BorderLayout _borderLayout;
	vector<uint32_t> _borderPixels;
	vector<uint32_t> _borderBackdrop; //BorderPrepareBackdrop, once per load
	vector<uint32_t> _borderSxLut;    //per-frame nearest-neighbour column LUT
	vector<uint32_t> _compositeBuffer;
	RenderedFrame _compositedFrame;

	void UpdateBorderAsset();
	void ResetBorderAsset();
	//Returns `&inFrame` when the border is disabled or unavailable (no copy),
	//or `&_compositedFrame` (backed by _compositeBuffer) otherwise. Non-const
	//only because IRenderingDevice::UpdateFrame takes a mutable reference.
	RenderedFrame* CompositeBorder(RenderedFrame& inFrame);

	RenderedFrame _lastFrame;
	SimpleLock _frameLock;

	safe_ptr<IVideoRecorder> _recorder;

	void RenderThread();
	bool DrawScriptHud(RenderedFrame& frame);

	FrameInfo GetEmuHudSize(FrameInfo baseFrameSize);

	void ProcessAviRecording(RenderedFrame& frame);

public:
	VideoRenderer(Emulator* emu);
	~VideoRenderer();

	FrameInfo GetRendererSize();
	void SetRendererSize(uint32_t width, uint32_t height);

	//ADR-0149: the UI changed which pack is preferred or enabled without a
	//game reload; the decode thread re-resolves the border on its next frame.
	void InvalidateBorderAsset() { _borderDirty.store(true, std::memory_order_release); }

	void SetScriptHudScale(uint32_t scale) { _scriptHudScale = scale; }
	std::pair<FrameInfo, OverscanDimensions> GetScriptHudSize();

	void StartThread();
	void StopThread();

	void UpdateFrame(RenderedFrame& frame);
	void ClearFrame();
	void RegisterRenderingDevice(IRenderingDevice* renderer);
	void UnregisterRenderingDevice(IRenderingDevice* renderer);

	void StartRecording(string filename, RecordAviOptions options);
	void AddRecordingSound(int16_t* soundBuffer, uint32_t sampleCount, uint32_t sampleRate);
	void StopRecording();
	bool IsRecording();
};