#include "pch.h"
#include "Shared/Video/VideoRenderer.h"
#include "Shared/Video/VideoDecoder.h"
#include "Shared/Interfaces/IRenderingDevice.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Video/DebugHud.h"
#include "Shared/Video/SystemHud.h"
#include "Shared/Video/DebugStats.h"
#include "Shared/InputHud.h"
#include "Shared/MessageManager.h"
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "Utilities/Video/IVideoRecorder.h"
#include "Utilities/Video/AviRecorder.h"
#include "Utilities/Video/GifRecorder.h"
#include "Utilities/PNGHelper.h"
#include "Utilities/JsonReader.h"
#include "Utilities/FolderUtilities.h"

namespace
{
	inline uint32_t BlendOver(uint32_t dst, uint32_t src)
	{
		uint32_t sa = (src >> 24) & 0xFF;
		if(sa == 255) {
			return src;
		}
		if(sa == 0) {
			return dst;
		}
		uint32_t sr = (src >> 16) & 0xFF;
		uint32_t sg = (src >> 8) & 0xFF;
		uint32_t sb = src & 0xFF;

		uint32_t da = (dst >> 24) & 0xFF;
		uint32_t dr = (dst >> 16) & 0xFF;
		uint32_t dg = (dst >> 8) & 0xFF;
		uint32_t db = dst & 0xFF;

		uint32_t invA = 255 - sa;
		uint32_t outR = (sr * sa + dr * invA) / 255;
		uint32_t outG = (sg * sa + dg * invA) / 255;
		uint32_t outB = (sb * sa + db * invA) / 255;
		uint32_t outA = sa + (da * invA) / 255;
		return (outA << 24) | (outR << 16) | (outG << 8) | outB;
	}
}

VideoRenderer::VideoRenderer(Emulator* emu)
{
	_emu = emu;
	_stopFlag = false;

	_rendererHud.reset(new DebugHud());
	_systemHud.reset(new SystemHud(_emu));
	_inputHud.reset(new InputHud(emu, _rendererHud.get()));
}

VideoRenderer::~VideoRenderer()
{
	_stopFlag = true;
	StopThread();
}

FrameInfo VideoRenderer::GetRendererSize()
{
	FrameInfo frame = {};
	frame.Width = _rendererWidth;
	frame.Height = _rendererHeight;
	return frame;
}

void VideoRenderer::SetRendererSize(uint32_t width, uint32_t height)
{
	_rendererWidth = width;
	_rendererHeight = height;
}

void VideoRenderer::StartThread()
{
	if(!_renderThread) {
		auto lock = _stopStartLock.AcquireSafe();
		if(!_renderThread) {
			_stopFlag = false;
			_waitForRender.Reset();

			_renderThread.reset(new std::thread(&VideoRenderer::RenderThread, this));
		}
	}
}

void VideoRenderer::StopThread()
{
	_stopFlag = true;
	if(_renderThread) {
		auto lock = _stopStartLock.AcquireSafe();
		if(_renderThread) {
			_renderThread->join();
			_renderThread.reset();
		}
	}
}

void VideoRenderer::RenderThread()
{
	if(_renderer) {
		_renderer->OnRendererThreadStarted();
	}

	Timer lastFrameTimer;
	bool needClearHud = false;
	while(!_stopFlag.load()) {
		//Wait until a frame is ready, or until 32ms have passed (to allow HUD to update at ~30fps when paused)
		bool forceRender = !_waitForRender.Wait(32);
		if(_renderer) {
			FrameInfo size = _emu->GetVideoDecoder()->GetBaseFrameInfo(true);
			_scriptHudSurface.UpdateSize(size.Width * _scriptHudScale, size.Height * _scriptHudScale);

			size = GetEmuHudSize(size);
			if(_emuHudSurface.UpdateSize(size.Width, size.Height)) {
				_rendererHud->ClearScreen();
			}

			RenderedFrame frame;
			{
				auto lock = _frameLock.AcquireSafe();
				frame = _lastFrame;
			}

			if(needClearHud) {
				_emuHudSurface.Clear();
				_rendererHud->ClearScreen();
			}

			_inputHud->DrawControllers(size, frame.InputData);

			{
				auto lock = _hudLock.AcquireSafe();
				_systemHud->Draw(_rendererHud.get(), size.Width, size.Height);
			}

			bool showDebugInfo = _emu->GetSettings()->GetPreferences().ShowDebugInfo;
			if(showDebugInfo) {
				double lastFrameTime = lastFrameTimer.GetElapsedMS();
				lastFrameTimer.Reset();
				_emu->GetDebugStats()->UpdateStats(_emu, true, lastFrameTime);
				_emu->GetDebugStats()->DisplayStats(_emu, _rendererHud.get());
				needClearHud = true;
			}

			_emuHudSurface.IsDirty = _rendererHud->Draw(_emuHudSurface.Buffer, size, {}, 0, {}, !needClearHud);
			_scriptHudSurface.IsDirty = DrawScriptHud(frame);

			needClearHud = showDebugInfo;

			if(forceRender || _needRedraw || _emuHudSurface.IsDirty || _scriptHudSurface.IsDirty) {
				_needRedraw = false;
				_renderer->Render(_emuHudSurface, _scriptHudSurface);
			}
		}
	}
}

FrameInfo VideoRenderer::GetEmuHudSize(FrameInfo baseFrameSize)
{
	FrameInfo size = {};
	if(_emu->GetSettings()->GetPreferences().HudSize == HudDisplaySize::Scaled) {
		//Adjust the system HUD's width to match the aspect ratio to allow text to be unstretched
		//(The Lua HUD is not adjusted to allow scripts that need to match positions on the game screen to work correctly.)
		double aspectRatio = _emu->GetSettings()->GetAspectRatio(_emu->GetRegion(), baseFrameSize);
		size.Width = (uint32_t)std::round(baseFrameSize.Height * aspectRatio);
		size.Height = baseFrameSize.Height;
	} else {
		size.Width = _rendererWidth / 2;
		size.Height = _rendererHeight / 2;
	}
	return size;
}

bool VideoRenderer::DrawScriptHud(RenderedFrame& frame)
{
	bool needRedraw = false;
	if(_lastScriptHudFrameNumber != frame.FrameNumber) {
		//Clear+draw HUD for scripts
		//-Only when frame number changes (to prevent the HUD from disappearing when paused, etc.)
		//-Only when commands are queued, otherwise skip drawing/clearing to avoid wasting CPU time
		if(_needScriptHudClear) {
			_scriptHudSurface.Clear();
			_needScriptHudClear = false;
			needRedraw = true;
		}

		if(_emu->GetScriptHud()->HasCommands()) {
			auto [size, overscan] = GetScriptHudSize();
			_emu->GetScriptHud()->Draw(_scriptHudSurface.Buffer, size, overscan, frame.FrameNumber, {});
			_needScriptHudClear = true;
			_lastScriptHudFrameNumber = frame.FrameNumber;
			needRedraw = true;
		}
	}
	return needRedraw;
}

std::pair<FrameInfo, OverscanDimensions> VideoRenderer::GetScriptHudSize()
{
	FrameInfo scriptHudSize = { _scriptHudSurface.Width, _scriptHudSurface.Height };
	OverscanDimensions overscan = _emu->GetSettings()->GetOverscan();
	overscan.Top *= _scriptHudScale;
	overscan.Bottom *= _scriptHudScale;
	overscan.Left *= _scriptHudScale;
	overscan.Right *= _scriptHudScale;
	return { scriptHudSize, overscan };
}

void VideoRenderer::UpdateBorderAsset()
{
	MepPackManager* mgr = _emu->GetEnhancementPackManager();
	string borderFolder = mgr ? mgr->GetSectionPath(MepSectionType::Border) : "";
	if(borderFolder.empty() && mgr) {
		borderFolder = mgr->GetSectionAutoPath(MepSectionType::Border);
	}

	if(borderFolder != _borderPackFolder || !_borderLoaded) {
		_borderPackFolder = borderFolder;
		_borderLoaded = true;
		_borderAvailable = false;
		_borderPixels.clear();
		_borderCanvasWidth = 0;
		_borderCanvasHeight = 0;
		_borderVpX = 0;
		_borderVpY = 0;
		_borderVpWidth = 0;
		_borderVpHeight = 0;
		_borderUnderlay = false;

		if(!borderFolder.empty()) {
			string pngPath = FolderUtilities::CombinePath(borderFolder, "border.png");
			ifstream pngFile(pngPath, ios::in | ios::binary);
			if(pngFile) {
				vector<uint8_t> fileData((std::istreambuf_iterator<char>(pngFile)), std::istreambuf_iterator<char>());
				uint32_t w = 0, h = 0;
				if(PNGHelper::ReadPNG(fileData, _borderPixels, w, h) && w > 0 && h > 0) {
					_borderCanvasWidth = w;
					_borderCanvasHeight = h;
					_borderAvailable = true;

					//Check for optional border.json (ADR-0149 §1)
					string jsonPath = FolderUtilities::CombinePath(borderFolder, "border.json");
					ifstream jsonFile(jsonPath, ios::in | ios::binary);
					if(jsonFile) {
						string jsonText((std::istreambuf_iterator<char>(jsonFile)), std::istreambuf_iterator<char>());
						JsonReader reader;
						JsonValue root;
						if(reader.Parse(jsonText, root) && root.IsObject()) {
							const JsonValue* vp = root.Get("viewport");
							if(vp && vp->IsObject()) {
								const JsonValue* vx = vp->Get("x");
								const JsonValue* vy = vp->Get("y");
								const JsonValue* vw = vp->Get("width");
								const JsonValue* vh = vp->Get("height");
								if(vx && vx->IsNumber()) _borderVpX = (int32_t)vx->GetNumber();
								if(vy && vy->IsNumber()) _borderVpY = (int32_t)vy->GetNumber();
								if(vw && vw->IsNumber()) _borderVpWidth = (uint32_t)vw->GetNumber();
								if(vh && vh->IsNumber()) _borderVpHeight = (uint32_t)vh->GetNumber();
							}
							const JsonValue* u = root.Get("underlay");
							if(u && u->IsBool()) {
								_borderUnderlay = u->GetBool();
							}
						}
					}

					//Fallback if viewport was absent or invalid: center inside canvas
					if(_borderVpWidth == 0 || _borderVpHeight == 0) {
						//Default 4:3 area inside 16:9 canvas
						_borderVpHeight = _borderCanvasHeight;
						_borderVpWidth = (_borderCanvasHeight * 4) / 3;
						_borderVpX = (_borderCanvasWidth > _borderVpWidth) ? (_borderCanvasWidth - _borderVpWidth) / 2 : 0;
						_borderVpY = 0;
					}
				}
			}
		}
	}
}

void VideoRenderer::CompositeBorder(RenderedFrame& inFrame, RenderedFrame& outFrame)
{
	outFrame = inFrame;
	bool enableBorder = _emu->GetSettings()->GetEnhancementPackConfig().EnableBorder;
	if(!enableBorder) {
		return;
	}

	UpdateBorderAsset();
	if(!_borderAvailable || _borderCanvasWidth == 0 || _borderCanvasHeight == 0 || _borderPixels.empty()) {
		return;
	}

	uint32_t totalPixels = _borderCanvasWidth * _borderCanvasHeight;
	if(_compositeBuffer.size() != totalPixels) {
		_compositeBuffer.resize(totalPixels);
	}

	uint32_t* dst = _compositeBuffer.data();
	const uint32_t* border = _borderPixels.data();
	const uint32_t* src = (const uint32_t*)inFrame.FrameBuffer;
	uint32_t srcW = inFrame.Width;
	uint32_t srcH = inFrame.Height;

	if(_borderUnderlay) {
		//Underlay: copy border first, then draw game on top of viewport
		memcpy(dst, border, totalPixels * sizeof(uint32_t));
		for(uint32_t vy = 0; vy < _borderVpHeight; vy++) {
			int32_t dy = _borderVpY + (int32_t)vy;
			if(dy < 0 || dy >= (int32_t)_borderCanvasHeight) continue;
			uint32_t sy = (vy * srcH) / _borderVpHeight;
			const uint32_t* srcRow = src + sy * srcW;
			uint32_t* dstRow = dst + dy * _borderCanvasWidth;
			for(uint32_t vx = 0; vx < _borderVpWidth; vx++) {
				int32_t dx = _borderVpX + (int32_t)vx;
				if(dx < 0 || dx >= (int32_t)_borderCanvasWidth) continue;
				uint32_t sx = (vx * srcW) / _borderVpWidth;
				dstRow[dx] = srcRow[sx];
			}
		}
	} else {
		//Overlay (default): clear to black, draw game into viewport, blend border.png on top
		memset(dst, 0, totalPixels * sizeof(uint32_t));
		for(uint32_t vy = 0; vy < _borderVpHeight; vy++) {
			int32_t dy = _borderVpY + (int32_t)vy;
			if(dy < 0 || dy >= (int32_t)_borderCanvasHeight) continue;
			uint32_t sy = (vy * srcH) / _borderVpHeight;
			const uint32_t* srcRow = src + sy * srcW;
			uint32_t* dstRow = dst + dy * _borderCanvasWidth;
			for(uint32_t vx = 0; vx < _borderVpWidth; vx++) {
				int32_t dx = _borderVpX + (int32_t)vx;
				if(dx < 0 || dx >= (int32_t)_borderCanvasWidth) continue;
				uint32_t sx = (vx * srcW) / _borderVpWidth;
				dstRow[dx] = srcRow[sx];
			}
		}
		//Blend border on top (alpha over)
		for(uint32_t i = 0; i < totalPixels; i++) {
			dst[i] = BlendOver(dst[i], border[i]);
		}
	}

	outFrame.FrameBuffer = (void*)dst;
	outFrame.Width = _borderCanvasWidth;
	outFrame.Height = _borderCanvasHeight;
}

void VideoRenderer::UpdateFrame(RenderedFrame& frame)
{
	{
		auto lock = _hudLock.AcquireSafe();
		_systemHud->UpdateHud();
	}

	ProcessAviRecording(frame);

	RenderedFrame effectiveFrame;
	CompositeBorder(frame, effectiveFrame);

	{
		auto lock = _frameLock.AcquireSafe();
		_lastFrame = effectiveFrame;
	}

	if(_renderer) {
		_renderer->UpdateFrame(effectiveFrame);
		_needRedraw = true;
		_waitForRender.Signal();
	}
}

void VideoRenderer::ClearFrame()
{
	if(_renderer) {
		_renderer->ClearFrame();
	}
}

void VideoRenderer::RegisterRenderingDevice(IRenderingDevice* renderer)
{
	_renderer = renderer;
	StartThread();
}

void VideoRenderer::UnregisterRenderingDevice(IRenderingDevice* renderer)
{
	if(_renderer == renderer) {
		StopThread();
		_renderer = nullptr;
	}
}

void VideoRenderer::ProcessAviRecording(RenderedFrame& frame)
{
	shared_ptr<IVideoRecorder> recorder = _recorder.lock();
	if(recorder) {
		if(!recorder->IsRecording()) {
			recorder->StartRecording(frame.Width, frame.Height, 4, _emu->GetSettings()->GetAudioConfig().SampleRate, _emu->GetFps());
		}

		if(_recorderOptions.RecordInputHud || _recorderOptions.RecordSystemHud) {
			//Calculate the scale needed for the HUD elements
			FrameInfo originalSize = _emu->GetVideoDecoder()->GetBaseFrameInfo(true);
			double scale = (double)frame.Height / originalSize.Height;
			FrameInfo scaledFrameSize = { (uint32_t)(frame.Width / scale), (uint32_t)(frame.Height / scale) };

			//Update the surface to match the frame's size
			_aviRecorderSurface.UpdateSize(frame.Width, frame.Height);

			//Copy the game screen
			memcpy(_aviRecorderSurface.Buffer, frame.FrameBuffer, frame.Width * frame.Height * sizeof(uint32_t));

			//Draw the system/input HUDs
			DebugHud hud;
			InputHud inputHud(_emu, &hud);
			if(_recorderOptions.RecordSystemHud) {
				_systemHud->Draw(&hud, scaledFrameSize.Width, scaledFrameSize.Height);
			}
			if(_recorderOptions.RecordInputHud) {
				inputHud.DrawControllers(scaledFrameSize, frame.InputData);
			}

			FrameInfo frameSize = { frame.Width, frame.Height };
			hud.Draw((uint32_t*)_aviRecorderSurface.Buffer, frameSize, {}, frame.FrameNumber, { scale, scale });

			//Record the final result
			if(!recorder->AddFrame(_aviRecorderSurface.Buffer, frame.Width, frame.Height, _emu->GetFps())) {
				StopRecording();
			}
		} else {
			//Only record the game screen
			if(!recorder->AddFrame(frame.FrameBuffer, frame.Width, frame.Height, _emu->GetFps())) {
				StopRecording();
			}
		}
	}
}

void VideoRenderer::StartRecording(string filename, RecordAviOptions options)
{
	_recorderOptions = options;

	shared_ptr<IVideoRecorder> recorder;
	if(options.Codec == VideoCodec::GIF) {
		recorder.reset(new GifRecorder());
	} else {
		recorder.reset(new AviRecorder(options.Codec, options.CompressionLevel));
	}

	if(recorder->Init(filename)) {
		_recorder.reset(recorder);

		if(!options.RecordSystemHud) {
			//Only display message if not recording the system HUD (otherwise the message is always visible on the recording, which isn't ideal)
			MessageManager::DisplayMessage("VideoRecorder", "VideoRecorderStarted", filename);
		}
	} else {
		MessageManager::DisplayMessage("VideoRecorder", "CouldNotWriteToFile", filename);
	}
}

void VideoRenderer::AddRecordingSound(int16_t* soundBuffer, uint32_t sampleCount, uint32_t sampleRate)
{
	shared_ptr<IVideoRecorder> recorder = _recorder.lock();
	if(recorder) {
		if(!recorder->AddSound(soundBuffer, sampleCount, sampleRate)) {
			StopRecording();
		}
	}
}

void VideoRenderer::StopRecording()
{
	shared_ptr<IVideoRecorder> recorder = _recorder.lock();
	if(recorder) {
		MessageManager::DisplayMessage("VideoRecorder", "VideoRecorderStopped", recorder->GetOutputFile());
	}
	_aviRecorderSurface.UpdateSize(0, 0);
	_recorder.reset();
}

bool VideoRenderer::IsRecording()
{
	return _recorder != nullptr;
}