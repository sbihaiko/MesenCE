#pragma once
//Planar tile-row decoders shared by the GB PPU, the SMS VDP and the GB/SMS
//static exporter (HdTilePackBuilder). One definition each, so a capture path
//and its static-export twin can never drift apart; the pixel output is
//bit-identical to the loops they replace (the ADR-0162 accuracy harness
//compares frames across builds and would flag any deviation).
#include <cstdint>

namespace HdTileDecode
{
	//Game Boy 2bpp: one row is two bytes, bit 7 = leftmost pixel, `low` is
	//the colour's bit 0 plane and `high` its bit 1 plane. Writes 8 colour
	//indexes (0..3) to `out`.
	static inline void Decode2bppRow(uint8_t low, uint8_t high, uint8_t out[8])
	{
		for(int x = 0; x < 8; x++) {
			out[x] = (uint8_t)(((low >> (7 - x)) & 0x01) | (((high >> (7 - x)) & 0x01) << 1));
		}
	}

	//SMS/GG 4bpp planar: one row is four consecutive plane bytes (plane 0
	//first), bit 7 = leftmost pixel. Writes 8 colour indexes (0..15) to `out`.
	static inline void Decode4bppPlanarRow(const uint8_t* planes, uint8_t out[8])
	{
		for(int x = 0; x < 8; x++) {
			out[x] = (uint8_t)(
				((planes[0] >> (7 - x)) & 0x01) |
				(((planes[1] >> (7 - x)) & 0x01) << 1) |
				(((planes[2] >> (7 - x)) & 0x01) << 2) |
				(((planes[3] >> (7 - x)) & 0x01) << 3));
		}
	}
}
