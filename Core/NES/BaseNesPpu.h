#pragma once
#include "pch.h"
#include "NES/INesMemoryHandler.h"
#include "Utilities/ISerializable.h"
#include "NES/NesTypes.h"

enum class ConsoleRegion;

class Emulator;
class BaseMapper;
class SnesControlManager;
class NesConsole;
class EmuSettings;

class BaseNesPpu : public INesMemoryHandler, public ISerializable
{
protected:
	uint64_t _masterClock = 0;
	uint32_t _cycle = 0;
	int16_t _scanline = 0;
	bool _emulatorBgEnabled = false;
	bool _emulatorSpritesEnabled = false;
	//16
	uint16_t _videoRamAddr = 0;
	uint16_t _tmpVideoRamAddr = 0;
	uint16_t _highBitShift = 0;
	uint16_t _lowBitShift = 0;
	uint8_t _masterClockDivider = 0;
	uint8_t _spriteRamAddr = 0;
	uint8_t _openBus = 0;
	uint8_t _xScroll = 0;
	bool _enableOamDecay = false;
	bool _needStateUpdate = false;
	bool _renderingEnabled = false;
	bool _prevRenderingEnabled = false;
	//32
	bool _sprite0Visible = false;
	uint8_t _spriteCount = 0;
	uint8_t _secondaryOamAddr = 0;
	uint8_t _oamCopybuffer = 0;
	bool _spriteInRange = false;
	bool _sprite0Added = false;
	uint8_t _overflowBugCounter = 0;
	bool _oamCopyDone = false;
	uint16_t _ppuBusAddress = 0;
	uint16_t _minimumDrawBgCycle = 0;
	uint16_t _minimumDrawSpriteCycle = 0;
	uint16_t _minimumDrawSpriteStandardCycle = 0;
	//48
	BaseMapper* _mapper = nullptr;
	uint16_t* _currentOutputBuffer = nullptr;
	////////////////////////
	//64 : end of cache line
	////////////////////////
	uint8_t _paletteRam[0x20] = {};
	uint8_t _secondarySpriteRam[0x20] = {};
	////////////////////////
	//128 : end of cache line
	////////////////////////
	TileInfo _tile = {};
	uint16_t _vblankEnd = 0;
	uint16_t _nmiScanline = 0;
	uint8_t _currentTilePalette = 0;
	uint8_t _previousTilePalette = 0;
	uint16_t _intensifyColorBits = 0;
	uint8_t _paletteRamMask = 0;
	uint8_t _updateVramAddrDelay = 0;
	//144
	uint32_t _spriteIndex = 0;
	int32_t _lastUpdatedPixel = 0;
	uint32_t _frameCount = 0;
	uint16_t _updateVramAddr = 0;
	bool _preventVblFlag = false;
	bool _writeToggle = false; //not used in rendering
	//160
	NesSpriteInfo* _lastSprite = nullptr; //used by HD ppu
	NesConsole* _console = nullptr;
	//176
	PpuControlFlags _control = {}; // 8 bytes
	PpuMaskFlags _mask = {}; // 8 bytes
	////////////////////////
	//192 : end of cache line
	////////////////////////
	uint8_t _spriteRam[0x100] = {};
	////////////////////////
	//448 : end of cache line
	////////////////////////
	NesSpriteInfo _spriteTiles[64] = {};

	static constexpr int SpriteShifterDone = 0x8000;
	uint16_t _spriteShifterList[9] = { SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone, SpriteShifterDone }; //Ordered by X coordinate.
	uint8_t _nextSpriteShifter = 0;
	uint16_t _nextSpriteShifterCycle = 0;
	uint8_t _activeSpriteShifters = 0;
	uint8_t _countingSpriteShifters = 0;
	uint8_t _expiredSpriteShifters = 0;
	uint8_t _dotSkipped = 0;
	bool _processSprites = false;

	Emulator* _emu = nullptr;
	EmuSettings* _settings = nullptr;
	uint16_t* _outputBuffers[2] = {};

	ConsoleRegion _region = {};
	uint16_t _standardVblankEnd = 0;
	uint16_t _standardNmiScanline = 0;
	uint16_t _palSpriteEvalScanline = 0;

	bool _needVideoRamIncrement = false;
	bool _allowFullPpuAccess = false;

	uint8_t _ppuMemoryDataReadStateMachine = 0;
	uint8_t _ppuMemoryDataWriteStateMachine = 0;
	uint8_t _ppuMemoryDataWriteLatch = 0;
	uint8_t _memoryReadBuffer = 0;
	PPUStatusFlags _statusFlags = {};

	uint8_t _firstVisibleSpriteAddr = 0; //For extra sprites
	uint8_t _lastVisibleSpriteAddr = 0; //For extra sprites

	uint32_t _ignoreVramRead = 0;
	int32_t _openBusDecayStamp[8] = {};

	uint64_t _oamDecayCycles[0x20] = {};

	//ADR-0169 2026-09-08 update ("mid-frame raster splits"): loopy v (bits
	//0-14), fine X (bits 15-17), plus the background pattern table select bit
	//(bit 18, PPUCTRL/$2000 bit 4 - _control.BackgroundPatternAddr != 0),
	//packed together as they stand right after cycle 257's horizontal-bits-
	//from-t copy, one entry per visible scanline (index = the scanline this
	//value governs, i.e. the copy that happens during scanline N's cycle 257
	//governs scanline N+1's rendering - see NesPpu::ProcessScanlineImpl's own
	//comment on this array). Neither fine X (loopy "x", a separate 3-bit
	//register $2005's first write sets directly) nor the pattern table select
	//(a plain PPUCTRL bit, likewise outside v/t) are part of v/t's own bits -
	//a raster effect that rewrites either mid-frame (Life Force's diagonal
	//parallax via fine X) needs it captured alongside v, not just assumed
	//constant for the whole screen the way a single end-of-frame GetState()
	//would. A single end-of-frame read only ever sees the LAST value this
	//frame held, wrong for any scanline before a mid-frame rewrite (HUD/
	//status-bar splits, raster parallax, a pattern-table split) - this array
	//is what HeadlessCaptureNesSpriteLayer/LiveFrameRecorder publish instead,
	//so the Python reconstruction can look up the row it is drawing instead
	//of assuming one scroll/pattern-table for the whole screen.
	uint32_t _scanlineVideoRamAddr[240] = {};

	//ADR-0169 2026-09-08 update ("mid-frame CHR bank splits"): the CHR-ROM
	//byte offset each 256-byte PPU-side page ($0000-$1FFF -> 32 slots)
	//resolves to, taken at the same cycle-257 point as
	//_scanlineVideoRamAddr above. Diagnosed against Gauntlet's title screen:
	//its mapper (206/Namco 108, an MMC3 derivative - CHR bank switching, no
	//scanline IRQ) rewrites CHR bank registers mid-frame via plain
	//$8000/$8001 writes (cycle-counted from NMI, no IRQ needed), splitting
	//the SAME nametable's tile indices across two different sets of actual
	//graphics for two bands of the screen (top: the logo; below: reused
	//indices repainted as border/copyright text). A single end-of-frame
	//Chr[] snapshot only ever resolves the LAST bank in effect, wrong for
	//every row drawn under the earlier bank - visible as sprite-shaped/
	//text-shaped fragments splashed across rows the mid-frame switch
	//orphaned. See BaseMapper::GetChrPageOffsets for why 256-byte
	//granularity covers every ROM-backed mapper's own bank-size scheme with
	//one accessor. 240*32*4 bytes (30KB) per publish - cheap next to the
	//CHR/nametable data already published every tick.
	uint32_t _scanlineChrBankOffsets[240][0x20] = {};

	bool IsRenderingEnabled();
	void UpdateGrayscaleAndIntensifyBits();
	void UpdateColorBitMasks();
	void UpdateMinimumDrawCycles();

public:
	virtual void Reset(bool softReset) = 0;
	virtual void Run(uint64_t runTo) = 0;

	uint32_t GetFrameCount() { return _frameCount; }
	uint32_t GetCurrentCycle() { return _cycle; }
	int32_t GetCurrentScanline() { return _scanline; }
	int32_t GetScanlineCount() { return _vblankEnd + 2; }
	uint32_t GetFrameCycle() { return ((_scanline + 1) * 341) + _cycle; }

	virtual uint16_t* GetScreenBuffer(bool previousBuffer, bool processGrayscaleEmphasisBits = false) = 0;
	virtual void UpdateTimings(ConsoleRegion region, bool overclockAllowed = true) = 0;

	void GetState(NesPpuState& state);
	void SetState(NesPpuState& state);

	//ADR-0169 2026-09-08 update ("mid-frame raster splits"): copies all 240
	//entries of _scanlineVideoRamAddr - see that field's comment.
	void GetScanlineScrollTrace(uint32_t* outValues)
	{
		memcpy(outValues, _scanlineVideoRamAddr, sizeof(_scanlineVideoRamAddr));
	}

	//ADR-0169 2026-09-08 update ("mid-frame CHR bank splits"): copies all
	//240*32 uint32 offsets of _scanlineChrBankOffsets - see that field's
	//comment.
	void GetScanlineChrBankTrace(uint32_t* outValues)
	{
		memcpy(outValues, _scanlineChrBankOffsets, sizeof(_scanlineChrBankOffsets));
	}

	uint16_t GetCurrentBgColor();

	uint8_t ReadPaletteRam(uint16_t addr);
	void WritePaletteRam(uint16_t addr, uint8_t value);

	void DebugSendFrame();

	virtual PpuModel GetPpuModel() = 0;
	virtual uint32_t GetPixelBrightness(uint8_t x, uint8_t y) = 0;

	virtual void GetMemoryRanges(MemoryRanges& ranges) override {}
	virtual uint8_t ReadRam(uint16_t addr) override { return 0; }
	virtual void WriteRam(uint16_t addr, uint8_t value) override {}

	virtual void Serialize(Serializer& s) override {}
};
