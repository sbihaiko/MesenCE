#pragma once
#include "pch.h"
#include "Shared/HdPacks/HdTilePackBuilder.h"
#include <unordered_map>

class VirtualFile;

//A <tile> replacement loaded from a hires.txt <ver>2xx pack
//(docs/specs/hires-gbsms-v1-draft.md; identity keys: ADR-0036/ADR-0037)
struct HdLoadedTile
{
	HdCapturedTile Key = {};
	uint32_t Brightness = 255;
	bool DefaultTile = false;

	//Premultiplied-alpha ARGB pixels, (8*scale)^2 entries
	vector<uint32_t> HdData;
};

//Per-pixel provenance filled by the GB PPU / SMS VDP while a pack is active,
//consumed by HdTileVideoFilter to compose the HD frame
struct HdTilePixelInfo
{
	HdLoadedTile* BgTile;
	HdLoadedTile* SprTile;
	uint16_t BgColor555; //BG color behind the sprite (for translucent HD sprites)
	uint8_t BgRow;
	uint8_t BgCol;
	uint8_t SprRow;
	uint8_t SprCol;
	bool SpriteOnTop;
};

//Runtime pack for the GB/SMS hires.txt extension: loads the definition +
//PNG sheets and answers tile-key lookups. The NES keeps its own HdPackData.
class HdTilePack
{
private:
	uint32_t _scale = 1;
	string _system;
	vector<unique_ptr<HdLoadedTile>> _tiles;
	std::unordered_map<HdCapturedTile, HdLoadedTile*> _tilesByKey;
	std::unordered_map<HdCapturedTile, HdLoadedTile*> _defaultTilesByKey;

	bool LoadFile(string definitionPath);
	bool ParseTileLine(string& line, vector<std::pair<vector<uint32_t>, uint32_t>>& sheets);

public:
	uint32_t GetScale() { return _scale; }
	string GetSystem() { return _system; }
	uint32_t GetTileCount() { return (uint32_t)_tiles.size(); }

	//Finds the pack for the ROM (HdPacks/<romname>/hires.txt) and loads it
	//when its <system> matches. Returns false when there is no (valid) pack.
	static bool Load(VirtualFile& romFile, string system, HdTilePack& outPack);

	HdLoadedTile* GetTile(const HdCapturedTile& key)
	{
		auto result = _tilesByKey.find(key);
		if(result != _tilesByKey.end()) {
			return result->second;
		}

		if(!_defaultTilesByKey.empty()) {
			//defaultTile entries match any palette (key reduced to data + type)
			HdCapturedTile wildcard = key;
			wildcard.PalKeySize = 1;
			memset(wildcard.PalKey + 1, 0, HdCapturedTile::MaxPalKeySize - 1);
			auto defResult = _defaultTilesByKey.find(wildcard);
			if(defResult != _defaultTilesByKey.end()) {
				return defResult->second;
			}
		}
		return nullptr;
	}
};
