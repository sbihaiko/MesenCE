#include "pch.h"
#include "Shared/HdPacks/HdTileVideoFilter.h"
#include "Shared/HdPacks/HdTilePack.h"
#include "Shared/ColorUtilities.h"
#include "Shared/Emulator.h"

HdTileVideoFilter::HdTileVideoFilter(Emulator* emu, HdTilePack* hdPack) : BaseVideoFilter(emu)
{
	_hdPack = hdPack;
	_scale = hdPack->GetScale();
}

FrameInfo HdTileVideoFilter::GetFrameInfo()
{
	FrameInfo frame = BaseVideoFilter::GetFrameInfo();
	frame.Width *= _scale;
	frame.Height *= _scale;
	return frame;
}

void HdTileVideoFilter::DrawTilePixel(uint32_t* hdPixels, uint32_t row, uint32_t col, uint32_t* outputBuffer, uint32_t outputWidth)
{
	uint32_t tileDimension = 8 * _scale;
	for(uint32_t dy = 0; dy < _scale; dy++) {
		uint32_t* src = hdPixels + (size_t)(row * _scale + dy) * tileDimension + col * _scale;
		uint32_t* dst = outputBuffer + (size_t)dy * outputWidth;
		for(uint32_t dx = 0; dx < _scale; dx++) {
			uint32_t pixel = src[dx];
			uint8_t alpha = (uint8_t)(pixel >> 24);
			if(alpha == 255) {
				dst[dx] = pixel;
			} else if(alpha > 0) {
				//Sources are premultiplied at load time
				uint8_t* out = (uint8_t*)(dst + dx);
				uint8_t* in = (uint8_t*)&pixel;
				uint16_t invertedAlpha = 256 - alpha;
				out[0] = (uint8_t)(in[0] + ((out[0] * invertedAlpha) >> 8));
				out[1] = (uint8_t)(in[1] + ((out[1] * invertedAlpha) >> 8));
				out[2] = (uint8_t)(in[2] + ((out[2] * invertedAlpha) >> 8));
				out[3] = 0xFF;
			}
		}
	}
}

void HdTileVideoFilter::ApplyFilter(uint16_t* ppuOutputBuffer)
{
	if(_frameData == nullptr) {
		//Can be null when loading a save state
		return;
	}

	HdTilePixelInfo* screenInfo = (HdTilePixelInfo*)_frameData;
	OverscanDimensions overscan = GetOverscan();
	uint32_t inWidth = _baseFrameInfo.Width;
	uint32_t width = inWidth - overscan.Left - overscan.Right;
	uint32_t height = _baseFrameInfo.Height - overscan.Top - overscan.Bottom;
	uint32_t visibleHeight = _inputVisibleHeight ? _inputVisibleHeight : _baseFrameInfo.Height;
	uint32_t outputWidth = width * _scale;
	uint32_t* outputBuffer = GetOutputBuffer();

	for(uint32_t y = 0; y < height; y++) {
		int32_t srcY = (int32_t)(y + overscan.Top) - (int32_t)_inputYOffset;
		if(srcY < 0 || srcY >= (int32_t)visibleHeight) {
			//Rows outside the source's viewport are blank
			for(uint32_t dy = 0; dy < _scale; dy++) {
				memset(outputBuffer + ((size_t)y * _scale + dy) * outputWidth, 0, outputWidth * sizeof(uint32_t));
			}
			continue;
		}

		for(uint32_t x = 0; x < width; x++) {
			uint32_t srcX = x + overscan.Left;
			HdTilePixelInfo& info = screenInfo[(size_t)srcY * inWidth + srcX];
			uint16_t originalColor = ppuOutputBuffer[(size_t)srcY * inWidth + srcX];
			uint32_t* out = outputBuffer + (size_t)y * _scale * outputWidth + (size_t)x * _scale;

			//Layer 1: the BG pixel (original color behind any HD replacement)
			uint32_t bgColor = ColorUtilities::Rgb555ToArgb(info.SpriteOnTop ? info.BgColor555 : originalColor);
			for(uint32_t dy = 0; dy < _scale; dy++) {
				std::fill(out + (size_t)dy * outputWidth, out + (size_t)dy * outputWidth + _scale, bgColor);
			}
			if(info.BgTile) {
				DrawTilePixel(info.BgTile->HdData.data(), info.BgRow, info.BgCol, out, outputWidth);
			}

			//Layer 2: the sprite pixel the hardware chose for this position
			if(info.SpriteOnTop) {
				if(info.SprTile) {
					DrawTilePixel(info.SprTile->HdData.data(), info.SprRow, info.SprCol, out, outputWidth);
				} else {
					uint32_t sprColor = ColorUtilities::Rgb555ToArgb(originalColor);
					for(uint32_t dy = 0; dy < _scale; dy++) {
						std::fill(out + (size_t)dy * outputWidth, out + (size_t)dy * outputWidth + _scale, sprColor);
					}
				}
			}
		}
	}
}
