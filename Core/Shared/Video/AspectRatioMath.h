#pragma once
#include "pch.h"
#include "Shared/SettingTypes.h"
#include <cmath>

//P.7 ("16:9 stretch"): the pure geometry behind the aspect-ratio setting,
//extracted out of EmuSettings::GetAspectRatio so it can be asserted directly
//in scripts/core_unit_tests.cpp without an Emulator, a window or a display.
//This is the *geometry only* - the number the display size is derived from,
//not the pixels the user ends up seeing; the on-screen pass stays manual.
namespace AspectRatioMath
{
	//Everything the ratio depends on, resolved by the caller from the console
	//and the ROM (EmuSettings does that from Emulator/RomInfo).
	struct Inputs
	{
		VideoAspectRatio Setting = VideoAspectRatio::NoStretching;
		uint32_t BaseWidth = 0;
		uint32_t BaseHeight = 0;
		ConsoleRegion Region = ConsoleRegion::Ntsc;
		//GB/GBA/WS: square pixels, so Auto must not apply a NTSC/PAL PAR
		bool SquarePixelInAuto = false;
		//Game Gear: 6:5 PAR in Auto
		bool GameGearPar = false;
		double CustomRatio = 0.0;
	};

	//The screen aspect ratio to render at, or 0.0 for an unknown setting.
	//Auto/NTSC/PAL are pixel aspect ratios, so they multiply the base screen's
	//own ratio; Standard/Widescreen/Custom are absolute screen ratios.
	inline double ComputeAspectRatio(const Inputs& in)
	{
		double screenAspectRatio = (double)in.BaseWidth / in.BaseHeight;

		switch(in.Setting) {
			case VideoAspectRatio::NoStretching: return screenAspectRatio;

			case VideoAspectRatio::Auto:
				if(in.SquarePixelInAuto) {
					return screenAspectRatio;
				} else if(in.GameGearPar) {
					return screenAspectRatio * (6.0 / 5.0);
				}
				return screenAspectRatio * ((in.Region == ConsoleRegion::Pal || in.Region == ConsoleRegion::Dendy) ? (11.0 / 8.0) : (8.0 / 7.0));

			case VideoAspectRatio::NTSC: return screenAspectRatio * 8.0 / 7.0;
			case VideoAspectRatio::PAL: return screenAspectRatio * 11.0 / 8.0;

			case VideoAspectRatio::Standard: return 4.0 / 3.0;
			case VideoAspectRatio::Widescreen: return 16.0 / 9.0;
			case VideoAspectRatio::Custom: return in.CustomRatio;
		}
		return 0.0;
	}

	//The stretched size the aspect ratio implies for a frame of `baseHeight`
	//rows: height is preserved, width is the ratio applied to it. This is the
	//shape VideoRenderer::GetEmuHudSize draws the scaled HUD at, and the same
	//width the host window sizes itself to (round(height * ratio)).
	struct Size
	{
		uint32_t Width = 0;
		uint32_t Height = 0;
	};

	inline Size ComputeStretchedSize(uint32_t baseHeight, double aspectRatio)
	{
		Size size = {};
		size.Width = (uint32_t)std::round(baseHeight * aspectRatio);
		size.Height = baseHeight;
		return size;
	}
}
