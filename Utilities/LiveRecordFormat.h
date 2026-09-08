#pragma once
#include "pch.h"

//ADR-0169 + its 2026-09-08 update: the record a live viewer/recorder pair
//agrees on, and the file format that publishes it. One shape, two producers -
//scripts/headless_record's scripted runs (Core/Shared/HeadlessInputEngine) and
//the interactive UI's LiveFrameRecorder (Core/Shared/LiveFrameRecorder) while
//a human plays - and one consumer, scripts/record_viewer.py. Nothing here
//renders or touches an Emulator; a producer fills a LiveSnapshot from
//whichever frame it just has in hand and calls the composer functions below.
struct LiveSnapshot
{
	uint32_t Width = 0;
	uint32_t Height = 0;
	uint32_t CaptureFrame = 0;
	std::vector<uint32_t> Pixels; //0xAARRGGBB - the composed frame

	bool HasSprites = false;
	uint16_t SpritePatternAddr = 0;
	bool LargeSprites = false;
	bool SpritesEnabled = true;
	bool LeftColumnClip = false;
	uint8_t Palette[0x20] = {};
	uint8_t Oam[0x100] = {};
	std::vector<uint8_t> Chr; //$0000-$1FFF pattern tables, mapper-resolved

	//The background layer as data, alongside the sprite layer above - both read
	//under the same Emulator::Lock() hold, so a viewer can multiplex them the
	//way the PPU itself does (ADR-0169's 2026-09-08 "capture every layer"
	//update) instead of drawing sprites over a plain backdrop.
	bool HasBackground = false;
	uint16_t BackgroundPatternAddr = 0;
	bool BackgroundEnabled = true;
	bool BackgroundLeftColumnClip = false;
	uint16_t TmpVideoRamAddr = 0; //loopy "t": the scroll the game wrote for the frame about to render
	// - fine Y (12-14), NT select (10-11), coarse Y (5-9), coarse X (0-4). This is
	// the reliable base-scroll source at an end-of-frame boundary: loopy "v"
	// (VideoRamAddr) has already scanned through the whole frame by then, while t
	// is only ever replaced by $2005/$2006 writes (NesPpu::WriteRam).
	uint8_t FineScrollX = 0;    //loopy "x", 0-7 - the fine X the game wrote
	std::vector<uint8_t> Nametables; //$2000-$2FFF (4KB), mapper-resolved (mirroring included)

	//ADR-0169 2026-09-08 update ("mid-frame raster splits"): loopy v (bits
	//0-14) packed with fine X (bits 15-17) and the background pattern table
	//select bit (bit 18) as they stood right after cycle 257's horizontal-
	//bits copy, one entry per visible scanline (BaseNesPpu::
	//GetScanlineScrollTrace / _scanlineVideoRamAddr's own comment).
	//TmpVideoRamAddr/FineScrollX/BackgroundPatternAddr above are only the
	//LAST value this frame held - wrong for any row drawn before a mid-frame
	//rewrite (a status-bar split, raster parallax); this is the per-row value
	//the reconstruction should use instead. Always 240 entries when
	//HasBackground is set.
	std::vector<uint32_t> ScanlineScroll;

	//ADR-0169 2026-09-08 update ("mid-frame CHR bank splits"): 240 rows * 32
	//slots (BaseNesPpu::GetScanlineChrBankTrace / _scanlineChrBankOffsets'
	//own comment) of CHR-ROM byte offsets, one per 256-byte PPU-side page. A
	//mapper whose CHR bank registers get rewritten mid-frame (Gauntlet's
	//title screen, mapper 206/Namco 108 - an MMC3 derivative with CHR bank
	//switching but no scanline IRQ) reuses the SAME nametable tile indices
	//for two different sets of actual graphics across two bands of the
	//screen - invisible to the single end-of-frame Chr[] snapshot above,
	//which only ever resolves the LAST bank in effect. Indexes into
	//ChrRomFull below, same as the CHR-latch case does. Empty whenever the
	//mapper has no CHR-ROM at all (CHR-RAM games - Chr[] already carries the
	//right content for those, nothing to add here).
	std::vector<uint32_t> ScanlineChrBank;

	//MMC2/MMC4 CHR-latch extension (BaseMapper::HasChrBankLatch, ADR-0169
	//2026-09-08 update): populated only for a mapper whose CHR bank flips
	//mid-frame via a tile-index latch. ChrRomFull is the raw, latch-independent
	//CHR-ROM (GetChrRomData()/GetChrRomSize()) - reading it needs no side
	//effects and is stable frame to frame - so the reconstruction can pick
	//either bank per half per tile, instead of trusting the one bank the
	//normal Chr[] snapshot resolved to. Also published (2026-09-08 update)
	//whenever ScanlineChrBank above is non-empty, even for a mapper without a
	//latch (Namco 108's plain bank registers) - the same raw dump backs both
	//mechanisms.
	//ADR-0169 2026-09-08 update ("HD pack substitution is not reconstructable"):
	//true when the console renders through an HD pack that replaces pixels
	//(NesConsole::IsHdPackVideoActive). The frame then shows the pack's redrawn
	//art while Chr/Nametables/Oam above still describe the original NES tiles,
	//so the two panes CANNOT agree - there is no data channel that carries the
	//substituted graphics back to a reconstruction. A consumer must say so
	//instead of reporting a meaningless match: the fix is to turn HD packs off
	//(NesConfig::EnableHdPacks, or headless_record's "hdpack-off").
	bool HdPackActive = false;

	bool HasChrLatch = false;
	std::vector<uint8_t> ChrRomFull;
	uint16_t ChrLatchPageSize = 0;
	uint8_t LeftChrFdBank = 0, LeftChrFeBank = 0;
	uint8_t RightChrFdBank = 0, RightChrFeBank = 0;
};

namespace LiveRecordFormat
{
	//Atomically replace 'finalPath': write finalPath.tmp, then rename() over
	//the target. A reader sees either the whole old file or the whole new
	//one, never a torn write - lossy-latest on purpose (ADR-0169 Decision
	//section 1).
	bool AtomicWrite(const std::string& finalPath, const void* data, size_t size);
	bool AtomicWrite(const std::string& finalPath, const std::string& text);

	std::string ComposePpm(const LiveSnapshot& snapshot);

	//The per-capture sprite record of ADR-0169 Decision section 2. ASCII only
	//(numbers, brackets, booleans), so it is composed with plain concatenation.
	std::string ComposeSpritesJson(const LiveSnapshot& snapshot, uint32_t cpuFrame);

	//The background layer's scroll/control bits (the tile+attribute bytes
	//themselves are nametables.bin, written alongside this the same way chr.bin
	//accompanies sprites.json).
	std::string ComposeBackgroundJson(const LiveSnapshot& snapshot);

	//The CHR-latch bank numbers + page size (chrfull.bin/chrlatch.bin is the
	//raw bytes, written alongside this the same way nametables.bin accompanies
	//background.json). Empty ("{}"-less nothing written) when !HasChrLatch.
	std::string ComposeChrLatchJson(const LiveSnapshot& snapshot);

	//hdPackActive publishes LiveSnapshot::HdPackActive - see its comment: a
	//consumer that compares panes must warn rather than score when it is set.
	std::string ComposeStatusJson(bool done, uint32_t frame, uint32_t targetFrames, double wallSec, bool hdPackActive);
}
