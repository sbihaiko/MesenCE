#include "pch.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/MessageManager.h"
#include "Shared/Video/BaseVideoFilter.h"
#include "Shared/Video/RotateFilter.h"
#include "Shared/Video/ScaleFilter.h"
#include "Shared/Video/ScanlineFilter.h"
#include "Utilities/PNGHelper.h"
#include "Utilities/FolderUtilities.h"

//F9.15: the capture half of BaseVideoFilter, split off from
//BaseVideoFilter.cpp (which was already at the ~200-line guardrail, ADR-0127)
//when the in-memory path was added. Same class, one pipeline: the pixels are
//produced once by CaptureScreenshot and either handed to the caller or
//encoded as a PNG, so a harness assertion and a saved screenshot can never
//disagree. The pure geometry lives in Shared/Video/FrameCapture.h.

ScreenshotCapture BaseVideoFilter::CopyOutputBuffer(vector<uint32_t>& out)
{
	ScreenshotCapture capture;
	auto lock = _frameLock.AcquireSafe();

	uint32_t pixelCount = 0;
	if(!_outputBuffer || !FrameCaptureMath::IsCaptureSizeValid(_frameInfo.Width, _frameInfo.Height, _bufferSize, pixelCount)) {
		//No frame decoded yet, or a width/height pair that does not describe
		//the buffer we are about to read - refuse before allocating anything.
		out.clear();
		return capture;
	}

	out.resize(pixelCount);
	memcpy(out.data(), _outputBuffer, (size_t)pixelCount * sizeof(uint32_t));

	capture.Width = _frameInfo.Width;
	capture.Height = _frameInfo.Height;
	capture.FrameNumber = _frame.FrameNumber;
	return capture;
}

ScreenshotCapture BaseVideoFilter::CaptureScreenshot(VideoFilterType filterType, vector<uint32_t>& out)
{
	ScreenshotCapture capture = CopyOutputBuffer(out);
	if(capture.IsEmpty()) {
		return capture;
	}

	FrameInfo frameInfo = { capture.Width, capture.Height };
	uint32_t* pngBuffer = out.data();

	uint8_t scale = 1;

	uint32_t screenRotation = _emu->GetSettings()->GetVideoConfig().ScreenRotation;
	_emu->GetScreenRotationOverride(screenRotation);

	unique_ptr<RotateFilter> rotateFilter(new RotateFilter(screenRotation));
	if(screenRotation != 0) {
		pngBuffer = rotateFilter->ApplyFilter(pngBuffer, frameInfo.Width, frameInfo.Height);
		frameInfo = rotateFilter->GetFrameInfo(frameInfo);
	}

	unique_ptr<ScaleFilter> scaleFilter = ScaleFilter::GetScaleFilter(_emu, filterType);
	if(scaleFilter) {
		pngBuffer = scaleFilter->ApplyFilter(pngBuffer, frameInfo.Width, frameInfo.Height);
		frameInfo = scaleFilter->GetFrameInfo(frameInfo);
		scale = scaleFilter->GetScale();
	}

	ScanlineFilter::ApplyFilter(pngBuffer, frameInfo.Width, frameInfo.Height, _emu->GetSettings()->GetVideoConfig().ScanlineIntensity, scale);

	if(pngBuffer != out.data()) {
		//The rotate and scale filters render into buffers they own and that
		//die with this call, so the result has to come back into the vector
		//the caller owns before we return.
		out.assign(pngBuffer, pngBuffer + (size_t)frameInfo.Width * frameInfo.Height);
	}

	capture.Width = frameInfo.Width;
	capture.Height = frameInfo.Height;
	return capture;
}

void BaseVideoFilter::TakeScreenshot(VideoFilterType filterType, string filename, std::stringstream* stream)
{
	//The PNG path is the capture path plus an encoder: one pipeline, so an
	//in-memory assertion and a saved screenshot can never disagree (F9.15).
	vector<uint32_t> pixels;
	ScreenshotCapture capture = CaptureScreenshot(filterType, pixels);
	if(capture.IsEmpty()) {
		return;
	}

	if(!filename.empty()) {
		PNGHelper::WritePNG(filename, pixels.data(), capture.Width, capture.Height);
	} else {
		PNGHelper::WritePNG(*stream, pixels.data(), capture.Width, capture.Height);
	}
}

void BaseVideoFilter::TakeScreenshot(string romName, VideoFilterType filterType)
{
	string romFilename = FolderUtilities::GetFilename(romName, false);

	int counter = 0;
	string baseFilename = FolderUtilities::CombinePath(FolderUtilities::GetScreenshotFolder(), romFilename);
	string ssFilename;
	while(true) {
		string counterStr = std::to_string(counter);
		while(counterStr.length() < 3) {
			counterStr = "0" + counterStr;
		}
		ssFilename = baseFilename + "_" + counterStr + ".png";
		ifstream file(ssFilename, ios::in);
		if(file) {
			file.close();
		} else {
			break;
		}
		counter++;
	}

	TakeScreenshot(filterType, ssFilename);

	MessageManager::DisplayMessage("ScreenshotSaved", FolderUtilities::GetFilename(ssFilename, true));
}
