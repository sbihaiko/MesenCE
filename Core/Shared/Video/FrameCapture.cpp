#include "pch.h"
#include "Shared/Video/FrameCapture.h"

namespace FrameCaptureMath
{
	bool IsCaptureSizeValid(uint32_t width, uint32_t height, uint32_t bufferPixels, uint32_t& outPixelCount)
	{
		if(width == 0 || height == 0) {
			return false;
		}

		//64-bit product first: width * height in 32-bit arithmetic wraps, and
		//a wrapped value that happens to match bufferPixels would authorise a
		//copy of the wrong length.
		uint64_t pixelCount = (uint64_t)width * (uint64_t)height;
		if(pixelCount > MaxCapturePixels || pixelCount != (uint64_t)bufferPixels) {
			return false;
		}

		outPixelCount = (uint32_t)pixelCount;
		return true;
	}

	FrameBorders MeasureBorders(const uint32_t* pixels, uint32_t width, uint32_t height)
	{
		FrameBorders borders;
		if(!pixels || width == 0 || height == 0) {
			borders.IsBlank = true;
			return borders;
		}

		borders.Colour = pixels[0];

		auto isUniformRow = [&](uint32_t y) {
			const uint32_t* row = pixels + (size_t)y * width;
			for(uint32_t x = 0; x < width; x++) {
				if(row[x] != borders.Colour) {
					return false;
				}
			}
			return true;
		};

		auto isUniformColumn = [&](uint32_t x) {
			for(uint32_t y = 0; y < height; y++) {
				if(pixels[(size_t)y * width + x] != borders.Colour) {
					return false;
				}
			}
			return true;
		};

		uint32_t top = 0;
		while(top < height && isUniformRow(top)) {
			top++;
		}

		if(top == height) {
			//Every row matched, so the capture holds a single colour: there is
			//no picture for a band to frame.
			borders.IsBlank = true;
			return borders;
		}

		uint32_t bottom = 0;
		while(bottom < height - top - 1 && isUniformRow(height - 1 - bottom)) {
			bottom++;
		}

		uint32_t left = 0;
		while(left < width && isUniformColumn(left)) {
			left++;
		}

		uint32_t right = 0;
		//left < width is guaranteed here (a non-blank capture has at least one
		//column that differs), so the bands cannot meet.
		while(right < width - left - 1 && isUniformColumn(width - 1 - right)) {
			right++;
		}

		borders.Top = top;
		borders.Bottom = bottom;
		borders.Left = left;
		borders.Right = right;
		return borders;
	}

	uint32_t Checksum(const uint32_t* pixels, uint32_t pixelCount)
	{
		uint32_t hash = 2166136261u;
		if(!pixels) {
			return hash;
		}

		for(uint32_t i = 0; i < pixelCount; i++) {
			uint32_t pixel = pixels[i];
			for(int byte = 0; byte < 4; byte++) {
				hash ^= (pixel >> (byte * 8)) & 0xFF;
				hash *= 16777619u;
			}
		}
		return hash;
	}
}
