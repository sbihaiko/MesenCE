#pragma once
#include "pch.h"
#include "SMS/SmsConsole.h"
#include "SMS/SmsVdp.h"
#include "Shared/HdPacks/HdTileVideoFilter.h"

//SMS/GG variant of the HD tile filter - the VDP renders 192/224/240 visible
//scanlines into the top of the 256x240 buffer, so the viewport offset has to
//be re-read every frame (the display mode can change at runtime)
class SmsHdTileVideoFilter final : public HdTileVideoFilter
{
private:
	SmsConsole* _console = nullptr;

protected:
	void OnBeforeApplyFilter() override
	{
		_inputYOffset = _console->GetVdp()->GetViewportYOffset();
		_inputVisibleHeight = _console->GetVdp()->GetState().VisibleScanlineCount;
	}

public:
	SmsHdTileVideoFilter(Emulator* emu, SmsConsole* console, HdTilePack* hdPack) : HdTileVideoFilter(emu, hdPack)
	{
		_console = console;
	}
};
