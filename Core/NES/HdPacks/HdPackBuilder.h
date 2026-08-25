#pragma once
#include "pch.h"
#include "NES/HdPacks/HdData.h"
#include "NES/NesTypes.h"
#include "Shared/SettingTypes.h"
#include <map>
#include <unordered_set>

class Emulator;
class BaseMapper;

class HdPackBuilder
{
private:
	Emulator* _emu = nullptr;

	HdPackData _hdData;
	unordered_map<HdTileKey, uint32_t> _tileUsageCount;
	unordered_map<HdTileKey, HdPackTileInfo*> _tilesByKey;
	std::map<uint32_t, std::map<uint32_t, vector<HdPackTileInfo*>>> _tilesByChrBankByPalette;
	bool _isChrRam = false;
	string _saveFolder;
	string _romName;
	HdPackBuilderOptions _options = {};
	uint32_t _palette[512] = {};

	//Used to group blank tiles together
	uint32_t _blankTileIndex = 0;
	int _blankTilePalette = 0;

	//F5.4 screen capture (bootstrap): a static screen = same background tile at
	//every pixel for N frames. Each new one is saved as backgrounds/screenNNN.png
	//(whole frame upscaled, sprites excluded) with tileAtPosition anchors, in the
	//format the most elaborate community packs use (<background> + conditions).
	struct ScreenRun
	{
		uint16_t X;
		uint16_t Y;
		HdPpuTileInfo Tile;
	};
	bool _captureScreens = false;
	vector<uint32_t> _frameBg;
	vector<ScreenRun> _frameRuns;
	HdTileKey _lastRunKey = {};
	int32_t _lastRunY = -1;
	uint32_t _frameHash = 0;
	uint32_t _prevFrameHash = 0;
	uint32_t _stableFrames = 0;
	uint32_t _bgPixels = 0;
	unordered_set<uint32_t> _screensSeen;
	static constexpr uint32_t StableFramesNeeded = 15;
	static constexpr uint32_t MaxScreensPerSession = 300;
	void CaptureScreen();

	void AddTile(HdPackTileInfo* tile, uint32_t usageCount);
	void GenerateHdTile(HdPackTileInfo* tile);
	void DrawTile(HdPackTileInfo* tile, int tileIndex, uint32_t* pngBuffer, int pageNumber, bool containsSpritesOnly);

public:
	HdPackBuilder(Emulator* emu, PpuModel ppuModel, bool isChrRam, HdPackBuilderOptions options);
	~HdPackBuilder();

	void ProcessTile(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, BaseMapper* mapper, bool isSprite, uint32_t chrBankHash, bool transparencyRequired);
	void SaveHdPack();

	//Screen capture (see above); colorIndex = the 2-bit background pixel value
	void EnableScreenCapture();
	__forceinline void ProcessBgPixel(uint32_t x, uint32_t y, HdPpuTileInfo& tile, uint8_t colorIndex)
	{
		if(!_captureScreens || x >= 256 || y >= 240) {
			return;
		}
		_frameBg[y * 256 + x] = _palette[(tile.PaletteColors >> ((3 - colorIndex) * 8)) & 0x3F] | 0xFF000000;
		_bgPixels++;
		if(x == 0 || (int32_t)y != _lastRunY || !(_lastRunKey == tile)) {
			_frameRuns.push_back({ (uint16_t)x, (uint16_t)y, tile });
			_lastRunKey = tile;
			_lastRunY = y;
			_frameHash = _frameHash * 16777619u ^ (tile.GetHashCode() + (x | (y << 8)));
		}
	}
	void OnFrameEnd();

	//Static export (no gameplay needed): every 16-byte tile of CHR ROM becomes
	//a palette-agnostic defaultTile entry drawn with a neutral gray ramp.
	//Tiles already present in the pack (recorded or previously exported) are
	//kept. Returns the number of tiles added.
	uint32_t AddRomTiles(uint8_t* chrRom, uint32_t chrRomSize);

	//static void GetChrBankList(uint32_t *banks);
	//static void GetBankPreview(uint32_t bankNumber, uint32_t pageNumber, uint32_t *rgbBuffer);
};