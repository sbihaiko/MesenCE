#pragma once
#include "pch.h"
#include "NES/HdPacks/HdData.h"
#include "NES/NesTypes.h"
#include "Shared/SettingTypes.h"
#include <map>
#include <unordered_set>

class Emulator;
class BaseMapper;

//F5.4d: "what you played" coverage. TilesSeen = distinct tile shapes the game
//actually drew during recording (static export seeds - AddRomTiles/AddPrgScanTiles
//- sit in _tileUsageCount with usage 0 and are excluded); TilesWithArt = of those,
//how many already have a real (non-defaultTile) art entry. ScreensSeen = distinct
//stable screens captured. IsChrRam drives the builder window's CHR RAM warning
//(static export is heuristic there - ADR-0043 "the UI says so").
struct HdPackCoverageReport
{
	uint32_t TilesSeen = 0;
	uint32_t TilesWithArt = 0;
	uint32_t ScreensSeen = 0;
	bool IsChrRam = false;
};

class HdPackBuilder
{
private:
	Emulator* _emu = nullptr;

	HdPackData _hdData;
	unordered_map<HdTileKey, uint32_t> _tileUsageCount;
	unordered_map<HdTileKey, HdPackTileInfo*> _tilesByKey;
	std::map<uint32_t, std::map<uint32_t, vector<HdPackTileInfo*>>> _tilesByChrBankByPalette;

	//F5.4b: real palette variants captured so far per tile shape (shapeKey =
	//tile.GetKey(true) - same tile content, PaletteColors wildcarded). Every
	//distinct PaletteColors value ProcessTile sees for a shape already got its
	//own HdPackTileInfo even before this change: ProcessTile's old "DefaultTile
	//wildcard" fallback was dead code (GetKey(true) sentinels PaletteColors to
	//0xFFFFFFFF, a value no real PPU palette word can ever produce, so it never
	//matched anything in _tileUsageCount, which AddTile only ever populates
	//with real PaletteColors via GetKey(false)). What was genuinely unbounded
	//is per-shape growth: a mostly/fully flat tile (e.g. TileData all-zero)
	//renders identically under any background palette, so unrelated screen
	//state alone can rack up dozens of "distinct" PaletteColors sightings for
	//one shape with no artistic value. Measured on a 20s roms/Zelda.nes hdpack
	//recording pre-cap: 182 shapes, median 14 variants/shape, p95 15, p99 27,
	//and a single all-zero blank-tile shape alone reaching 71 - the long tail
	//this cap targets. MaxPaletteVariantsPerTile is set above that p99 so real
	//per-shape diversity survives intact and only the degenerate/near-blank
	//outliers get bounded. Beyond the cap, further sightings just bump usage
	//on the shape's last captured variant instead of growing the pack further.
	//Not seeded from an existing on-disk pack at construction (same gap noted
	//below for _screensSeen) - a re-record session can add up to
	//MaxPaletteVariantsPerTile more variants on top of what is already on disk.
	unordered_map<HdTileKey, vector<HdPackTileInfo*>> _paletteVariantsByShape;
	static constexpr uint32_t MaxPaletteVariantsPerTile = 32;
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
	bool _writeReferences = false; //*.orig.png next to each sheet/screen: pixel-exact, no filter
	vector<uint32_t> _origBuffer;
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

	//F5.4e: spatial co-occurrence → object grouping. During screen capture the
	//per-frame background tile grid (_frameTileGrid/_frameTileSet) accumulates,
	//in _coOccurrence, how often two tile shapes appear exactly 8 px apart (E/S
	//neighbors; B at A + (8,0) or A + (0,8)). Keys are shape hashes (GetKey(true):
	//palette wildcarded), so every palette variant of a tile collapses into one
	//shape; a rare 32-bit CHR-RAM hash collision only merges two shapes into one
	//object, acceptable for an "# inferred" heuristic. BuildObjectSheets clusters
	//those edges (union-find over edges seen ≥2×), writes one editable per-object
	//sheet textures/sheets/object<NNN>.png (the object's tiles arranged as they
	//appear in-game), documents the cell order as a hires.txt comment, and emits
	//"# inferred" tileNearby condition candidates (inert definitions the artist
	//can wire to a <tile> - never auto-attached, to avoid making a tile fail to
	//render when its inferred neighbor is absent).
	struct HdPackCoOccurrenceEdge
	{
		uint32_t ECount = 0; //times the second shape was seen 8 px east of the first
		uint32_t SCount = 0; //times it was seen 8 px south
		uint32_t Count() const { return ECount + SCount; }
	};
	HdTileKey _frameTileGrid[30][32];
	uint8_t _frameTileSet[30][32] = {}; //source of truth for which grid cells were drawn
	std::map<std::pair<uint32_t, uint32_t>, HdPackCoOccurrenceEdge> _coOccurrence;
	bool _objectsBuilt = false; //guard: build the object sheets once per session
	void AccumulateCoOccurrence();
	void BuildObjectSheets(stringstream& tileRows);
	HdPackTileInfo* FindObjectArt(uint32_t shapeHash, std::map<uint32_t, HdPackTileInfo*>& bestByShape);

	void AddTile(HdPackTileInfo* tile, uint32_t usageCount);
	void GenerateHdTile(HdPackTileInfo* tile);
	void DrawTile(HdPackTileInfo* tile, int tileIndex, uint32_t* pngBuffer, int pageNumber, bool containsSpritesOnly);

	//F5.4b: ProcessTile helpers (kept separate to stay under the per-function line/
	//complexity limits) - see _paletteVariantsByShape above for the overall design.
	void UpdateTileUsage(const HdTileKey& exactKey, unordered_map<HdTileKey, uint32_t>::iterator usage, bool transparencyRequired);
	void CaptureOrCapPaletteVariant(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, uint32_t chrBankHash, bool transparencyRequired);

public:
	HdPackBuilder(Emulator* emu, PpuModel ppuModel, bool isChrRam, HdPackBuilderOptions options);
	~HdPackBuilder();

	void ProcessTile(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, BaseMapper* mapper, bool isSprite, uint32_t chrBankHash, bool transparencyRequired);
	void SaveHdPack();

	//F5.4d: coverage report for the builder window (see HdPackCoverageReport above)
	HdPackCoverageReport GetCoverageReport() const;

	//Screen capture (see above); colorIndex = the 2-bit background pixel value
	void EnableScreenCapture();
	__forceinline void ProcessBgPixel(uint32_t x, uint32_t y, HdPpuTileInfo& tile, uint8_t colorIndex)
	{
		if(!_captureScreens || x >= 256 || y >= 240) {
			return;
		}
		//F5.4e: record the background tile shape at each 8x8 cell origin, for the
		//per-frame co-occurrence grid (AccumulateCoOccurrence, called in OnFrameEnd).
		if((x & 7) == 0 && (y & 7) == 0) {
			_frameTileGrid[y >> 3][x >> 3] = tile.GetKey(true);
			_frameTileSet[y >> 3][x >> 3] = 1;
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

	//CHR RAM games keep their tiles inside PRG ROM and copy them by code: scan
	//the PRG for runs of 16-byte blocks that look like tiles (rows change
	//little from one to the next, not flat) and export them like AddRomTiles.
	//Heuristic - a few false positives (tables that look like graphics) are
	//harmless defaultTile entries nobody ever draws. Returns the number added.
	uint32_t AddPrgScanTiles(uint8_t* prgRom, uint32_t prgRomSize);

	//static void GetChrBankList(uint32_t *banks);
	//static void GetBankPreview(uint32_t bankNumber, uint32_t pageNumber, uint32_t *rgbBuffer);
};