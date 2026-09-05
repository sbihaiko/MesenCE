#include "pch.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/RewindManager.h"
#include "Shared/Video/BaseVideoFilter.h"

const static double PI = 3.14159265358979323846;

BaseVideoFilter::BaseVideoFilter(Emulator* emu)
{
	_emu = emu;
	_overscan = _emu->GetSettings()->GetOverscan();
}

BaseVideoFilter::~BaseVideoFilter()
{
	auto lock = _frameLock.AcquireSafe();
	delete[] _outputBuffer;
}

void BaseVideoFilter::SetBaseFrameInfo(FrameInfo frameInfo)
{
	_baseFrameInfo = frameInfo;
}

FrameInfo BaseVideoFilter::GetFrameInfo()
{
	FrameInfo frameInfo = _baseFrameInfo;
	OverscanDimensions overscan = GetOverscan();
	frameInfo.Width -= overscan.Left + overscan.Right;
	frameInfo.Height -= overscan.Top + overscan.Bottom;
	return frameInfo;
}

void BaseVideoFilter::UpdateBufferSize()
{
	uint32_t newBufferSize = _frameInfo.Width * _frameInfo.Height;
	if(_bufferSize != newBufferSize) {
		//Allocate first, then take the lock and swap: allocating from inside
		//the lock meant a throwing `new` unwound with _outputBuffer already
		//deleted, leaving every other holder of the lock - the screenshot and
		//capture paths - reading freed memory (F9.15).
		uint32_t* newBuffer = newBufferSize > 0 ? new uint32_t[newBufferSize] : nullptr;
		uint32_t* oldBuffer = nullptr;
		{
			auto lock = _frameLock.AcquireSafe();
			oldBuffer = _outputBuffer;
			_outputBuffer = newBuffer;
			_bufferSize = newBufferSize;
		}
		delete[] oldBuffer;
	}
}

OverscanDimensions BaseVideoFilter::GetOverscan()
{
	return _overscan;
}

void BaseVideoFilter::SetOverscan(OverscanDimensions overscan)
{
	_overscan = overscan;
}

void BaseVideoFilter::OnBeforeApplyFilter()
{
}

bool BaseVideoFilter::IsOddFrame()
{
	return _isOddFrame;
}

uint32_t BaseVideoFilter::GetVideoPhase()
{
	return _videoPhase;
}

uint32_t BaseVideoFilter::GetBufferSize()
{
	return _bufferSize * sizeof(uint32_t);
}

FrameInfo BaseVideoFilter::GetFrameInfo(uint16_t* ppuOutputBuffer, bool enableOverscan)
{
	_overscan = enableOverscan ? _emu->GetSettings()->GetOverscan() : OverscanDimensions {};
	_ppuOutputBuffer = ppuOutputBuffer;
	OnBeforeApplyFilter();
	FrameInfo frameInfo = GetFrameInfo();
	_frameInfo = frameInfo;
	_ppuOutputBuffer = nullptr;
	return frameInfo;
}

FrameInfo BaseVideoFilter::SendFrame(uint16_t* ppuOutputBuffer, uint32_t frameNumber, uint32_t videoPhase, void* frameData, bool enableOverscan, RenderedFrame frame)
{
	auto lock = _frameLock.AcquireSafe();
	_overscan = enableOverscan ? _emu->GetSettings()->GetOverscan() : OverscanDimensions {};
	_isOddFrame = frameNumber % 2;
	_videoPhase = videoPhase;
	_frameData = frameData;
	_ppuOutputBuffer = ppuOutputBuffer;
	_frame = frame;

	//Reset blend flag, specific filter must set each each frame when blending is needed
	_blendFilter.SetEnabled(false);

	OnBeforeApplyFilter();
	FrameInfo frameInfo = GetFrameInfo();
	_frameInfo = frameInfo;
	UpdateBufferSize();
	ApplyFilter(ppuOutputBuffer);

	if(_blendFilter.IsEnabled() && !_emu->GetRewindManager()->IsRewinding() && !_emu->IsPaused()) {
		_blendFilter.ApplyFilter(_outputBuffer, _bufferSize, _frame.FrameNumber);
	}

	_ppuOutputBuffer = nullptr;
	return frameInfo;
}

uint32_t* BaseVideoFilter::GetOutputBuffer()
{
	return _outputBuffer;
}

void BaseVideoFilter::InitConversionMatrix(double hueShift, double saturationShift)
{
	double hue = hueShift * PI;
	double sat = saturationShift + 1;

	double baseValues[6] = { 0.956f, 0.621f, -0.272f, -0.647f, -1.105f, 1.702f };

	double s = sin(hue) * sat;
	double c = cos(hue) * sat;

	double* output = _yiqToRgbMatrix;
	double* input = baseValues;
	for(int n = 0; n < 3; n++) {
		double i = *input++;
		double q = *input++;
		*output++ = i * c - q * s;
		*output++ = i * s + q * c;
	}
}

void BaseVideoFilter::ApplyColorOptions(uint8_t& r, uint8_t& g, uint8_t& b, double brightness, double contrast)
{
	double redChannel = r / 255.0;
	double greenChannel = g / 255.0;
	double blueChannel = b / 255.0;

	//Apply brightness, contrast, hue & saturation
	double y, i, q;
	RgbToYiq(redChannel, greenChannel, blueChannel, y, i, q);
	y *= contrast * 0.5f + 1;
	y += brightness * 0.5f;
	YiqToRgb(y, i, q, redChannel, greenChannel, blueChannel);

	r = (uint8_t)std::min(255, (int)std::round(redChannel * 255));
	g = (uint8_t)std::min(255, (int)std::round(greenChannel * 255));
	b = (uint8_t)std::min(255, (int)std::round(blueChannel * 255));
}

void BaseVideoFilter::RgbToYiq(double r, double g, double b, double& y, double& i, double& q)
{
	y = r * 0.299f + g * 0.587f + b * 0.114f;
	i = r * 0.596f - g * 0.275f - b * 0.321f;
	q = r * 0.212f - g * 0.523f + b * 0.311f;
}

void BaseVideoFilter::YiqToRgb(double y, double i, double q, double& r, double& g, double& b)
{
	r = std::max(0.0, std::min(1.0, (y + _yiqToRgbMatrix[0] * i + _yiqToRgbMatrix[1] * q)));
	g = std::max(0.0, std::min(1.0, (y + _yiqToRgbMatrix[2] * i + _yiqToRgbMatrix[3] * q)));
	b = std::max(0.0, std::min(1.0, (y + _yiqToRgbMatrix[4] * i + _yiqToRgbMatrix[5] * q)));
}
