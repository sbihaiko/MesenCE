#pragma once
//F9.15 (PRD Part A, Phase 9): host-free validation and measurement for an
//in-memory frame capture - the pixels the harness reads instead of writing a
//PNG to Screenshots/ and reading it back.
//
//Deliberately depends on nothing beyond the standard library so
//`make core-unit-tests` can link it without the Emulator (same arrangement as
//Shared/Video/BorderLayout.h, ADR-0149). Its stateful partner is
//BaseVideoFilter (ADR-0127): that class owns the frame lock, the filter
//pipeline and the output buffer, and delegates every decision that can be
//made from plain numbers to the functions here.
#include <cstdint>

//What a capture is, apart from its pixels: the dimensions those pixels are
//in, and the emulated frame they were produced from. The pixel data itself
//lives in a caller-owned vector, never in a buffer the core hands out.
struct ScreenshotCapture
{
	uint32_t Width = 0;
	uint32_t Height = 0;
	uint32_t FrameNumber = 0;

	//A capture that failed (no frame decoded yet, or dimensions that did not
	//validate) is returned as an empty one - no exception, no partial buffer.
	bool IsEmpty() const { return Width == 0 || Height == 0; }
	uint32_t PixelCount() const { return Width * Height; }
};

//Thickness, in pixels, of the uniform bands framing a capture: what
//letterboxing (Top/Bottom) and pillarboxing (Left/Right) look like when
//measured instead of looked at. Colour is the band colour, i.e. the capture's
//top-left pixel.
struct FrameBorders
{
	uint32_t Left = 0;
	uint32_t Right = 0;
	uint32_t Top = 0;
	uint32_t Bottom = 0;
	uint32_t Colour = 0;

	//The whole capture is one colour - there is no picture to measure bands
	//around, so all four thicknesses are reported as 0. Assert on this
	//separately: a blank capture usually means the run never reached a frame.
	bool IsBlank = false;
};

namespace FrameCaptureMath
{
	//Ceiling on a capture we are willing to allocate for. A 10x prescale of a
	//256x240 frame is 6.1 Mpx, so this leaves an order of magnitude of room
	//while still rejecting a garbage width/height pair before it turns into a
	//multi-gigabyte allocation.
	constexpr uint32_t MaxCapturePixels = 64u * 1024u * 1024u;

	//Dimension validation, run *before* anything is allocated: both
	//dimensions non-zero, their product free of 32-bit overflow, within
	//MaxCapturePixels, and equal to the number of pixels the source buffer
	//actually holds. outPixelCount is written only on success.
	bool IsCaptureSizeValid(uint32_t width, uint32_t height, uint32_t bufferPixels, uint32_t& outPixelCount);

	//Uniform band thicknesses around the picture, measured against the
	//top-left pixel's colour. A row counts toward Top/Bottom only when every
	//one of its pixels is that colour, and a column toward Left/Right on the
	//same rule over the full height. Bands never overlap: a uniform capture
	//reports IsBlank instead.
	FrameBorders MeasureBorders(const uint32_t* pixels, uint32_t width, uint32_t height);

	//FNV-1a over the pixel bytes. Its only job is to answer "is this the same
	//capture as the last one" in a shell assertion, cheaply and stably.
	uint32_t Checksum(const uint32_t* pixels, uint32_t pixelCount);
}
