#pragma once
#include "pch.h"
#include "Shared/Video/BaseVideoFilter.h"

class Emulator;
class HdTilePack;
struct HdTilePixelInfo;

//Composes the HD frame for GB/SMS hires.txt packs from the per-pixel
//provenance the PPU/VDP filled in (HdTilePixelInfo). Uses the same canonical
//color pipeline as the pack recorder (raw RGB555 -> RGB888 expansion), so a
//neutral 1:1 pack reproduces the original frame exactly.
class HdTileVideoFilter : public BaseVideoFilter
{
private:
	HdTilePack* _hdPack = nullptr;
	uint32_t _scale = 1;

	__forceinline void DrawTilePixel(uint32_t* hdPixels, uint32_t row, uint32_t col, uint32_t* outputBuffer, uint32_t outputWidth);

protected:
	//Vertical position of the source's first scanline inside the base frame,
	//and how many scanlines it filled (0 = full height). The SMS subclass sets
	//these per frame to match the VDP's 192/224/240-line viewport.
	uint32_t _inputYOffset = 0;
	uint32_t _inputVisibleHeight = 0;

public:
	HdTileVideoFilter(Emulator* emu, HdTilePack* hdPack);

	FrameInfo GetFrameInfo() override;
	void ApplyFilter(uint16_t* ppuOutputBuffer) override;
};
