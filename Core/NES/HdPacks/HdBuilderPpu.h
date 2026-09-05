#pragma once
#include "pch.h"
#include "NES/HdPacks/HdNesPpu.h"
#include "NES/HdPacks/HdNesPack.h"
#include "NES/HdPacks/HdPackBuilder.h"
#include "Shared/Video/VideoDecoder.h"
#include "Shared/RewindManager.h"
#include "Utilities/BitUtilities.h"
#include "Utilities/Serializer.h"

class HdBuilderPpu final : public NesPpu<HdBuilderPpu>
{
private:
	HdPackBuilder* _hdPackBuilder = nullptr;
	bool _needChrHash = false;
	uint32_t _chrRamBankSize = 0;
	uint32_t _chrRamIndexMask = 0;
	vector<uint32_t> _bankHashes;

	NesSpriteInfoEx _exSpriteInfo[64] = {};
	NesTileInfoEx _previousTileEx = {};
	NesTileInfoEx _currentTileEx = {};
	NesTileInfoEx _nextTileEx = {};

public:
	__forceinline bool RemoveSpriteLimit() { return _console->GetNesConfig().RemoveSpriteLimit; }
	__forceinline bool UseAdaptiveSpriteLimit() { return _console->GetNesConfig().AdaptiveSpriteLimit; }

	//F9.5 (ADR-0153 §2): one OAM snapshot per frame for the sprite sheets. Read
	//from OAM rather than from DrawPixel because the sheet wants the figure the
	//game *placed*, not the pixels that survived the 8-sprite limit and the
	//background priority bit. Runs once a frame, before NesConsole closes the
	//frame on the builder, and is a no-op unless screen capture is on.
	void* OnBeforeSendFrame()
	{
		CaptureOam();
		return nullptr;
	}

	__forceinline void StoreSpriteInformation(bool horizontalMirror, bool verticalMirror, uint16_t tileAddr, uint8_t lineOffset, NesSpriteInfo& sprite)
	{
		NesSpriteInfoEx& info = _exSpriteInfo[_spriteIndex];
		info.TileAddr = tileAddr;
		info.AbsoluteTileAddr = _mapper->GetPpuAbsoluteAddress(info.TileAddr).Address;
		info.HorizontalMirror = horizontalMirror;
		info.VerticalMirror = verticalMirror;
		info.OffsetY = lineOffset;
		info.LowByte = sprite.LowByte;
		info.HighByte = sprite.HighByte;
	}

	__forceinline void PushTileInformation()
	{
		_previousTileEx = _currentTileEx;
		_currentTileEx = _nextTileEx;
	}

	__forceinline void StoreTileInformation()
	{
		uint8_t tileIndex = _mapper->DebugReadVram(GetNameTableAddr());
		uint16_t tileAddr = (tileIndex << 4) | (_videoRamAddr >> 12) | _control.BackgroundPatternAddr;

		_nextTileEx.OffsetY = _videoRamAddr >> 12;
		_nextTileEx.TileAddr = tileAddr;
		_nextTileEx.AbsoluteTileAddr = _mapper->GetPpuAbsoluteAddress(tileAddr).Address;
	}

	__forceinline void ProcessScanline()
	{
		ProcessScanlineImpl();
	}

	void DrawPixel()
	{
		if(IsRenderingEnabled() || ((_videoRamAddr & 0x3F00) != 0x3F00)) {
			BaseMapper* mapper = _console->GetMapper();
			bool isChrRam = !mapper->HasChrRom();

			_lastSprite = nullptr;
			uint32_t color = GetPixelColor();
			_currentOutputBuffer[(_scanline << 8) + _cycle - 1] = _paletteRam[color & 0x03 ? color : 0];
			uint32_t backgroundColor = 0;
			if(_mask.BackgroundEnabled && _cycle > _minimumDrawBgCycle) {
				backgroundColor = (((_lowBitShift << _xScroll) & 0x8000) >> 15) | (((_highBitShift << _xScroll) & 0x8000) >> 14);
			}

			if(_needChrHash) {
				uint16_t addr = 0;
				_bankHashes.clear();
				while(addr < 0x2000) {
					uint32_t hash = 0;
					for(uint16_t i = 0; i < _chrRamBankSize; i++) {
						hash += mapper->DebugReadVram(i + addr);
						hash = (hash << 1) | (hash >> 31);
					}
					_bankHashes.push_back(hash);
					addr += _chrRamBankSize;
				}
				_needChrHash = false;
			}

			bool hasBgSprite = false;
			if(_lastSprite && _mask.SpritesEnabled) {
				uint8_t spriteIndex = (uint8_t)(_lastSprite - _spriteTiles);
				NesSpriteInfoEx& spriteInfoEx = _exSpriteInfo[spriteIndex];

				if(backgroundColor == 0) {
					for(uint8_t i = 0; i < _spriteCount; i++) {
						if(_spriteTiles[i].BackgroundPriority) {
							hasBgSprite = true;
							break;
						}
					}
				}

				if(spriteInfoEx.AbsoluteTileAddr >= 0) {
					HdPpuTileInfo sprite = {};
					sprite.TileIndex = (isChrRam ? (spriteInfoEx.TileAddr & _chrRamIndexMask) : spriteInfoEx.AbsoluteTileAddr) / 16;
					sprite.PaletteColors = ReadPaletteRam(_lastSprite->PaletteOffset + 3) | (ReadPaletteRam(_lastSprite->PaletteOffset + 2) << 8) | (ReadPaletteRam(_lastSprite->PaletteOffset + 1) << 16) | 0xFF000000;
					sprite.IsChrRamTile = isChrRam;
					mapper->CopyChrTile(spriteInfoEx.AbsoluteTileAddr & 0xFFFFFFF0, sprite.TileData);

					_hdPackBuilder->ProcessTile(_cycle - 1, _scanline, spriteInfoEx.AbsoluteTileAddr, sprite, mapper, false, _bankHashes[spriteInfoEx.TileAddr / _chrRamBankSize], false);
				}
			}

			if(_mask.BackgroundEnabled) {
				bool usePrev = (_xScroll + ((_cycle - 1) & 0x07) < 8);
				uint8_t tilePalette = usePrev ? _previousTilePalette : _currentTilePalette;
				NesTileInfoEx& lastTileEx = usePrev ? _previousTileEx : _currentTileEx;
				//TileInfo* lastTile = &((_xScroll + ((_cycle - 1) & 0x07) < 8) ? _previousTile : _currentTile);
				if(lastTileEx.AbsoluteTileAddr >= 0) {
					HdPpuTileInfo tile = {};
					tile.TileIndex = (isChrRam ? (lastTileEx.TileAddr & _chrRamIndexMask) : lastTileEx.AbsoluteTileAddr) / 16;
					tile.PaletteColors = ReadPaletteRam(tilePalette + 3) | (ReadPaletteRam(tilePalette + 2) << 8) | (ReadPaletteRam(tilePalette + 1) << 16) | (ReadPaletteRam(0) << 24);
					tile.IsChrRamTile = isChrRam;
					mapper->CopyChrTile(lastTileEx.AbsoluteTileAddr & 0xFFFFFFF0, tile.TileData);

					_hdPackBuilder->ProcessTile(_cycle - 1, _scanline, lastTileEx.AbsoluteTileAddr, tile, mapper, false, _bankHashes[lastTileEx.TileAddr / _chrRamBankSize], hasBgSprite);
					_hdPackBuilder->ProcessBgPixel(_cycle - 1, _scanline, tile, (uint8_t)backgroundColor);
				}
			}
		} else {
			//"If the current VRAM address points in the range $3F00-$3FFF during forced blanking, the color indicated by this palette location will be shown on screen instead of the backdrop color."
			_currentOutputBuffer[(_scanline << 8) + _cycle - 1] = _paletteRam[_videoRamAddr & 0x1F];
		}
	}

private:
	//OAM flips are attribute bits, not tile data, so a mirrored half of a figure
	//shares its CHR with its twin. Baking the flip into the recorded shape is
	//what lets the two sit side by side on a sheet instead of collapsing into
	//one cell (a group cannot place the same vocabulary entry twice).
	static void ApplyFlips(uint8_t* tileData, bool horizontalMirror, bool verticalMirror)
	{
		if(verticalMirror) {
			for(int plane = 0; plane < 16; plane += 8) {
				for(int row = 0; row < 4; row++) {
					std::swap(tileData[plane + row], tileData[plane + 7 - row]);
				}
			}
		}
		if(horizontalMirror) {
			for(int i = 0; i < 16; i++) {
				tileData[i] = BitUtilities::ReverseByte(tileData[i]);
			}
		}
	}

	void CaptureOam()
	{
		BaseMapper* mapper = _console->GetMapper();
		bool isChrRam = !mapper->HasChrRom();
		uint32_t halves = _control.LargeSprites ? 2 : 1;
		for(uint32_t i = 0; i < 64; i++) {
			uint8_t spriteY = _spriteRam[i * 4];
			//239 and up is how a game parks a sprite off-screen
			if(spriteY >= 0xEF) {
				continue;
			}
			uint8_t tileIndex = _spriteRam[i * 4 + 1];
			uint8_t attributes = _spriteRam[i * 4 + 2];
			uint8_t spriteX = _spriteRam[i * 4 + 3];
			uint8_t paletteOffset = ((attributes & 0x03) << 2) | 0x10;
			bool horizontalMirror = (attributes & 0x40) != 0;
			bool verticalMirror = (attributes & 0x80) != 0;

			for(uint32_t half = 0; half < halves; half++) {
				//An 8x16 sprite is recorded as its two 8x8 halves, top half first
				//on screen whichever way the sprite is flipped.
				uint32_t part = verticalMirror ? (halves - 1 - half) : half;
				uint16_t tileAddr = _control.LargeSprites
					? (uint16_t)((((tileIndex & 0x01) << 12) | ((tileIndex & ~0x01) << 4)) + part * 16)
					: (uint16_t)(_control.SpritePatternAddr | (tileIndex << 4));
				int32_t absoluteTileAddr = mapper->GetPpuAbsoluteAddress(tileAddr).Address;
				uint32_t y = spriteY + 1 + half * 8;
				if(absoluteTileAddr < 0 || y >= 240) {
					continue;
				}

				HdPpuTileInfo sprite = {};
				sprite.TileIndex = (isChrRam ? (tileAddr & _chrRamIndexMask) : (uint32_t)absoluteTileAddr) / 16;
				sprite.PaletteColors = ReadPaletteRam(paletteOffset + 3) | (ReadPaletteRam(paletteOffset + 2) << 8) | (ReadPaletteRam(paletteOffset + 1) << 16) | 0xFF000000;
				sprite.IsChrRamTile = isChrRam;
				mapper->CopyChrTile((uint32_t)absoluteTileAddr & 0xFFFFFFF0, sprite.TileData);
				ApplyFlips(sprite.TileData, horizontalMirror, verticalMirror);

				_hdPackBuilder->RecordSprite(spriteX, (uint8_t)y, sprite);
			}
		}
	}

public:
	void WriteRAM(uint16_t addr, uint8_t value)
	{
		if(GetRegisterID(addr) == PpuRegisters::VideoMemoryData) {
			if(_videoRamAddr < 0x2000) {
				_needChrHash = true;
			}
		}
		NesPpu::WriteRam(addr, value);
	}

	void Serialize(Serializer& s)
	{
		NesPpu::Serialize(s);
		if(!s.IsSaving()) {
			_needChrHash = true;
		}
	}

public:
	HdBuilderPpu(NesConsole* console, HdPackBuilder* hdPackBuilder, uint32_t chrRamBankSize) : NesPpu(console)
	{
		_hdPackBuilder = hdPackBuilder;
		_chrRamBankSize = chrRamBankSize;
		_chrRamIndexMask = chrRamBankSize - 1;
		_needChrHash = true;
	}
};