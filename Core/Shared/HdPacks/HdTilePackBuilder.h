#pragma once
#include "pch.h"
#include "Shared/SettingTypes.h"
#include <unordered_map>

class Emulator;

//A tile captured by a GB PPU / SMS VDP during gameplay. The console code
//resolves everything hardware-specific (tile bytes, palette key blob, RGBA
//pixels); identity semantics per console are recorded in ADR-0036/ADR-0037
//and docs/specs/hires-gbsms-v1-draft.md §3.2.
struct HdCapturedTile
{
	static constexpr uint32_t MaxDataSize = 32;
	static constexpr uint32_t MaxPalKeySize = 36;

	uint8_t Data[HdCapturedTile::MaxDataSize] = {};
	uint8_t PalKey[HdCapturedTile::MaxPalKeySize] = {};
	uint8_t DataSize = 0;
	uint8_t PalKeySize = 0;

	//PNG sheet grouping only - NOT part of the identity key (ADR-0036)
	uint32_t BankId = 0;

	bool operator==(const HdCapturedTile& other) const
	{
		return (
			DataSize == other.DataSize && PalKeySize == other.PalKeySize &&
			memcmp(Data, other.Data, DataSize) == 0 &&
			memcmp(PalKey, other.PalKey, PalKeySize) == 0);
	}

	uint32_t GetHashCode() const
	{
		//FNV-1a over the identity fields
		uint32_t hash = 2166136261u;
		for(uint32_t i = 0; i < DataSize; i++) {
			hash = (hash ^ Data[i]) * 16777619u;
		}
		for(uint32_t i = 0; i < PalKeySize; i++) {
			hash = (hash ^ PalKey[i]) * 16777619u;
		}
		return hash;
	}
};

namespace std
{
	template<> struct hash<HdCapturedTile>
	{
		size_t operator()(const HdCapturedTile& x) const { return x.GetHashCode(); }
	};
}

//Console-agnostic HD pack recorder for the hires.txt <ver>200 extension
//(GB/GBC/SMS/GG - docs/specs/hires-gbsms-v1-draft.md). Dedups captured
//tiles, pages them into 16x16-tile PNG sheets per bank and writes the
//hires.txt skeleton on destruction. The NES keeps its own HdPackBuilder.
class HdTilePackBuilder
{
private:
	struct TileEntry
	{
		HdCapturedTile Key = {};
		uint32_t Rgba[64] = {};
		uint32_t UsageCount = 0;
		uint32_t Order = 0;

		//Carried over from an existing pack on re-record: HdPixels (already at
		//the pack's scale, possibly hand-edited) is written back verbatim
		vector<uint32_t> HdPixels;
		uint32_t Brightness = 255;
		bool DefaultTile = false;
	};

	Emulator* _emu = nullptr;
	string _system;
	string _saveFolder;
	string _romSha1;
	uint32_t _scale = 1;
	ScaleFilterType _filterType = ScaleFilterType::Prescale;
	bool _sortByUsageFrequency = false;

	std::unordered_map<HdCapturedTile, TileEntry> _tiles;
	uint32_t _nextOrder = 0;
	bool _saved = false;

	vector<uint32_t> ScaleTile(const uint32_t* rgba);
	string GetPaletteKeyText(const HdCapturedTile& key);
	string GetTileDataText(const HdCapturedTile& key);
	void MergeExistingPack();

public:
	HdTilePackBuilder(Emulator* emu, string system, HdPackBuilderOptions options);
	~HdTilePackBuilder();

	void ProcessTile(const HdCapturedTile& tile, const uint32_t* rgba);

	//Static export: scans the ROM for tile-sized blocks (16 bytes 2bpp for
	//gb/gbc, 32 bytes 4bpp planar for sms/gg) and adds each as a
	//palette-agnostic defaultTile (one BG and one OBJ entry) drawn with a
	//neutral gray ramp. Heuristic: only aligned blocks; flat blocks and
	//blocks reusing an existing key are skipped. Compressed graphics are
	//invisible to this scan - partial coverage is expected, recording fills
	//the gaps (merge on re-record). Returns the number of entries added.
	uint32_t AddRomTiles(const vector<uint8_t>& rom);
	void SaveHdPack();
};
