#pragma once
#include "pch.h"
#include "NES/HdPacks/HdData.h"

class NesConsole;
class EmuSettings;

class BaseHdNesPack
{
protected:
	unordered_map<int32_t, int32_t> _fallbackTiles;
	HdScreenInfo* _hdScreenInfo = nullptr;

public:
	static constexpr uint32_t CurrentVersion = 109;

	virtual uint32_t GetScale() = 0;

	HdScreenInfo* GetScreenInfo() { return _hdScreenInfo; }

	int32_t GetFallbackTile(int32_t tileIndex)
	{
		auto result = _fallbackTiles.find(tileIndex);
		if(result != _fallbackTiles.end()) {
			return result->second;
		}
		return -1;
	}

	virtual void Process(HdScreenInfo* hdScreenInfo, uint32_t* outputBuffer, OverscanDimensions& overscan) = 0;

	virtual ~BaseHdNesPack() {}
};

template<uint32_t scale>
class HdNesPack final : public BaseHdNesPack
{
private:
	struct HdBgConfig
	{
		int32_t BackgroundIndex = -1;
		int32_t BgPriority = -1;
		int32_t BgScrollX = 0;
		int32_t BgScrollY = 0;
		int16_t BgMinX = -1;
		int16_t BgMaxX = -1;
	};

	static constexpr uint8_t PriorityLevelsPerLayer = 10;
	static constexpr uint8_t BehindBgSpritesPriority = 0 * PriorityLevelsPerLayer;
	static constexpr uint8_t BehindBgPriority = 1 * PriorityLevelsPerLayer;
	static constexpr uint8_t BehindFgSpritesPriority = 2 * PriorityLevelsPerLayer;
	static constexpr uint8_t ForegroundPriority = 3 * PriorityLevelsPerLayer;

	NesConsole* _console = nullptr;
	EmuSettings* _settings = nullptr;
	HdPackData* _hdData = nullptr;

	uint8_t _activeBgCount[4] = {};
	HdBgConfig _bgConfig[40] = {};

	uint32_t _palette[512] = {};
	HdPackTileInfo* _cachedTile = nullptr;
	bool _cacheEnabled = false;
	bool _useCachedTile = false;
	int32_t _scrollX = 0;

	//Diagnostic counters (issue: community pack visually indistinguishable from
	//original tiles in gameplay - measure how often GetMatchingTile actually
	//finds a tile vs falls through to the original NES tile, logged periodically).
	//ADR-0145: the match rate is also a runtime health signal - sustained low
	//coverage on an *optimistic* textures pack (applied without an exact SHA1
	//match) means the pack is probably for a different game; the MEP manager
	//warns and auto-disables it.
	uint64_t _debugBgTileLookups = 0;
	uint64_t _debugBgTileMatches = 0;
	uint64_t _debugFrameCount = 0;
	//Consecutive ~60-frame windows with a match rate below
	//kHealthSignalMinMatchRate; when this reaches kHealthSignalWindowLimit the
	//health signal fires once and is latched until the pack is reloaded
	uint32_t _lowMatchRateWindows = 0;
	bool _healthSignalFired = false;
	//ADR-0145 health-signal thresholds: <25% bg-tile match for 5 consecutive
	//one-second windows (~5s) is treated as "this textures pack is not for this
	//game" - long enough to ride out a menu/loading screen, short enough to
	//notice a wrong-game pack quickly
	static constexpr int kHealthSignalMinMatchRate = 25;
	static constexpr uint32_t kHealthSignalWindowLimit = 5;

	unordered_map<HdTileKey, vector<HdPackAdditionalSpriteInfo>> _additionalTilesByKey;

	template<HdPackBlendMode blendMode>
	__forceinline void BlendColors(uint8_t output[4], uint8_t input[4]);

	__forceinline uint32_t AdjustBrightness(uint8_t input[4], int brightness);
	__forceinline void DrawColor(uint32_t color, uint32_t* outputBuffer, uint32_t screenWidth);
	__forceinline void DrawTile(HdPpuTileInfo& tileInfo, HdPackTileInfo& hdPackTileInfo, uint32_t* outputBuffer, uint32_t screenWidth);

	__forceinline HdPackTileInfo* GetCachedMatchingTile(uint32_t x, uint32_t y, HdPpuTileInfo* tile);
	__forceinline HdPackTileInfo* GetMatchingTile(uint32_t x, uint32_t y, HdPpuTileInfo* tile, bool* disableCache = nullptr);

	__forceinline void DrawBackgroundLayer(uint8_t priority, uint32_t x, uint32_t y, uint32_t* outputBuffer, uint32_t screenWidth);

	template<HdPackBlendMode blendMode>
	__forceinline void DrawCustomBackground(HdBackgroundInfo& bgInfo, uint32_t* outputBuffer, uint32_t x, uint32_t y, uint32_t screenWidth);

	void OnLineStart(HdPpuPixelInfo& lineFirstPixel, uint8_t y);
	int32_t GetLayerIndex(uint8_t priority);
	void OnBeforeApplyFilter();

	void ProcessAdditionalSprites();
	bool DrawAdditionalTiles(int32_t x, int32_t y, HdPpuTileInfo& tile, bool checkFallbackTiles);
	void BuildAdditionalTileCache(int32_t x, int32_t y, HdPpuTileInfo& tile, bool checkFallbackTiles);
	void InsertAdditionalSprite(int32_t x, int32_t y, HdPpuTileInfo& sprite, HdPackAdditionalSpriteInfo& additionalSprite);

	__forceinline void GetPixels(uint32_t x, uint32_t y, HdPpuPixelInfo& pixelInfo, uint32_t* outputBuffer, uint32_t screenWidth);
	__forceinline void ProcessGrayscaleAndEmphasis(HdPpuPixelInfo& pixelInfo, uint32_t* outputBuffer, uint32_t hdScreenWidth);

	void CleanupInvalidRules();
	void InitializeFallbackTiles();

public:
	HdNesPack(NesConsole* console, EmuSettings* settings, HdPackData* hdData);
	virtual ~HdNesPack();

	uint32_t GetScale() override { return scale; }

	void Process(HdScreenInfo* hdScreenInfo, uint32_t* outputBuffer, OverscanDimensions& overscan) override;
};
