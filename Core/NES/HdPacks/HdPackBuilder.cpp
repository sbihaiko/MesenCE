#include "pch.h"
#include <algorithm>
#include <queue>
#include "NES/HdPacks/HdPackBuilder.h"
#include "NES/HdPacks/HdNesPack.h"
#include "NES/BaseMapper.h"
#include "NES/BaseNesPpu.h"
#include "NES/NesConstants.h"
#include "NES/HdPacks/HdPackLoader.h"
#include "NES/HdPacks/HdPackConditions.h"
#include "Shared/MessageManager.h"
#include "NES/NesDefaultVideoFilter.h"
#include "Utilities/xBRZ/xbrz.h"
#include "Utilities/HQX/hqx.h"
#include "Utilities/Scale2x/scalebit.h"
#include "Utilities/KreedSaiEagle/SaiEagle.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/PNGHelper.h"
#include "Utilities/HexUtilities.h"
#include "Utilities/VirtualFile.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"

HdPackBuilder::HdPackBuilder(Emulator* emu, PpuModel ppuModel, bool isChrRam, HdPackBuilderOptions options)
{
	_emu = emu;
	_isChrRam = isChrRam;

	_saveFolder = options.SaveFolder;
	options.SaveFolder = nullptr;

	_options = options;

	NesDefaultVideoFilter::GetFullPalette(_palette, _emu->GetSettings()->GetNesConfig(), ppuModel);

	string existingPackDefinition = FolderUtilities::CombinePath(_saveFolder, "hires.txt");
	if(ifstream(existingPackDefinition)) {
		HdPackLoader::LoadHdNesPack(existingPackDefinition, _hdData);
		_hdData.LoadAsync();
		for(auto& tile : _hdData.Tiles) {
			tile->Init();
		}

		for(unique_ptr<HdPackTileInfo>& tile : _hdData.Tiles) {
			//Mark the tiles in the first PNGs as higher usage (preserves order when adding new tiles to an existing set)
			AddTile(tile.get(), 0xFFFFFFFF - tile->BitmapIndex);
		}

		for(unique_ptr<HdPackTileInfo>& tile : _hdData.Tiles) {
			//F5.4b follow-up (b) (ADR-0132): seed the per-shape palette-variant map
			//from the on-disk pack, so the cap is a per-shape total across sessions.
			//DefaultTile neutral-ramp placeholders are excluded - they are waiting
			//for art, not real PaletteColors variants (the loader ignores their
			//PaletteColors).
			if(tile && !tile->DefaultTile) {
				_paletteVariantsByShape[tile->GetKey(true)].push_back(tile.get());
			}
		}

		if(_hdData.Scale != _options.Scale) {
			_options.FilterType = ScaleFilterType::Prescale;
		}
	} else {
		_hdData.Scale = _options.Scale;
	}

	_romName = FolderUtilities::GetFilename(_emu->GetRomInfo().RomFile.GetFileName(), false);
}

HdPackBuilder::~HdPackBuilder()
{
	SaveHdPack();
}

HdPackCoverageReport HdPackBuilder::GetCoverageReport() const
{
	HdPackCoverageReport report;
	report.IsChrRam = _isChrRam;
	report.ScreensSeen = (uint32_t)_screensSeen.size();

	//"What you played" = distinct tile shapes actually seen during recording.
	//Static export seeds (AddRomTiles/AddPrgScanTiles) land in _tileUsageCount
	//with usage 0 and are never bumped, so usage>=1 separates gameplay sightings
	//from the pre-seeded ROM dump (on-disk tiles loaded at construction get
	//0xFFFFFFFF - BitmapIndex, also >= 1). A shape is keyed by GetKey(true):
	//PaletteColors wildcarded, so every palette variant of the same tile content
	//collapses into one shape.
	unordered_set<HdTileKey, HdTileKey> shapesSeen;
	for(const auto& kv : _tileUsageCount) {
		if(kv.second == 0) {
			continue;
		}
		shapesSeen.insert(kv.first.GetKey(true));
	}
	report.TilesSeen = (uint32_t)shapesSeen.size();

	//"With art" = a non-defaultTile entry covers the shape - exact palette key
	//first, then the wildcard (GetKey(true)) default/recorded shape entry.
	unordered_set<HdTileKey, HdTileKey> shapesWithArt;
	for(const auto& kv : _tilesByKey) {
		if(kv.second && !kv.second->DefaultTile) {
			shapesWithArt.insert(kv.first.GetKey(true));
		}
	}
	for(const HdTileKey& shape : shapesSeen) {
		if(shapesWithArt.find(shape) != shapesWithArt.end()) {
			report.TilesWithArt++;
		}
	}
	return report;
}

void HdPackBuilder::AccumulateCoOccurrence()
{
	//The grid holds the background tile shape (palette-wildcarded key) per 8x8
	//cell of the last drawn frame; only E and S neighbors are examined so every
	//adjacent pair is counted once (B at A + (8,0) => ECount, A + (0,8) => SCount).
	//Runs only while capture is enabled (the grid is only filled then), so object
	//inference reflects what the captured screens actually showed.
	for(int row = 0; row < 30; row++) {
		for(int col = 0; col < 32; col++) {
			if(!_frameTileSet[row][col]) {
				continue;
			}
			uint32_t a = _frameTileGrid[row][col].GetKey(true).GetHashCode();
			if(col + 1 < 32 && _frameTileSet[row][col + 1]) {
				uint32_t b = _frameTileGrid[row][col + 1].GetKey(true).GetHashCode();
				_coOccurrence[{std::min(a, b), std::max(a, b)}].ECount++;
			}
			if(row + 1 < 30 && _frameTileSet[row + 1][col]) {
				uint32_t b = _frameTileGrid[row + 1][col].GetKey(true).GetHashCode();
				_coOccurrence[{std::min(a, b), std::max(a, b)}].SCount++;
			}
		}
	}
	std::memset(_frameTileSet, 0, sizeof(_frameTileSet));
}

HdPackTileInfo* HdPackBuilder::FindObjectArt(uint32_t shapeHash, std::map<uint32_t, HdPackTileInfo*>& bestByShape)
{
	auto it = bestByShape.find(shapeHash);
	return it != bestByShape.end() ? it->second : nullptr;
}

//F5.4e: cluster the co-occurrence graph into objects and write one editable
//per-object sheet + "# inferred" tileNearby candidates. See the header comment.
void HdPackBuilder::BuildObjectSheets(stringstream& tileRows)
{
	if(_objectsBuilt || _coOccurrence.empty()) {
		return;
	}
	_objectsBuilt = true;

	//Most-used non-default art per shape, used to draw the object sheets and as
	//the tileNearby target data.
	std::map<uint32_t, HdPackTileInfo*> bestByShape;
	for(unique_ptr<HdPackTileInfo>& tile : _hdData.Tiles) {
		if(!tile || tile->DefaultTile) {
			continue;
		}
		uint32_t shape = tile->GetKey(true).GetHashCode();
		auto it = bestByShape.find(shape);
		if(it == bestByShape.end() || _tileUsageCount[tile->GetKey(false)] > _tileUsageCount[it->second->GetKey(false)]) {
			bestByShape[shape] = tile.get();
		}
	}

	//Union-find over shapes whose edges were seen at least twice. Groups bigger
	//than 32 shapes are skipped - a huge connected component is a contiguous
	//background region, not a discrete object an artist would edit as one sheet.
	struct DisjointSet
	{
		vector<int32_t> parent;
		explicit DisjointSet(size_t n) : parent(n, -1) {}
		int32_t Find(int32_t x)
		{
			while(parent[x] >= 0) {
				if(parent[parent[x]] >= 0) {
					parent[x] = parent[parent[x]];
				}
				x = parent[x];
			}
			return x;
		}
		void Union(int32_t a, int32_t b)
		{
			a = Find(a);
			b = Find(b);
			if(a == b) {
				return;
			}
			if(parent[a] > parent[b]) {
				std::swap(a, b);
			}
			parent[a] += parent[b];
			parent[b] = a;
		}
	};

	std::vector<uint32_t> shapes;
	std::map<uint32_t, int32_t> shapeIndex;
	for(const auto& edge : _coOccurrence) {
		if(edge.second.Count() < 2) {
			continue;
		}
		for(uint32_t s : { edge.first.first, edge.first.second }) {
			if(shapeIndex.find(s) == shapeIndex.end()) {
				shapeIndex[s] = (int32_t)shapes.size();
				shapes.push_back(s);
			}
		}
	}
	if(shapes.empty()) {
		return;
	}

	DisjointSet ds(shapes.size());
	for(const auto& edge : _coOccurrence) {
		if(edge.second.Count() >= 2) {
			ds.Union(shapeIndex[edge.first.first], shapeIndex[edge.first.second]);
		}
	}

	std::map<int32_t, vector<uint32_t>> groups;
	for(uint32_t s : shapes) {
		groups[ds.Find(shapeIndex[s])].push_back(s);
	}

	int objectIndex = 0;
	for(const auto& group : groups) {
		if(group.second.size() < 2 || group.second.size() > 32) {
			continue;
		}

		//BFS layout from the most-co-occurring shape; each placed neighbor goes at
		//the dominant 8px offset of the edge that connects it (E or S relative to
		//the lower-hash endpoint, per AccumulateCoOccurrence).
		std::map<uint32_t, std::pair<int32_t, int32_t>> placed;
		std::vector<uint32_t> queue;
		int32_t minX = 0, minY = 0, maxX = 0, maxY = 0;

		uint32_t seed = group.second[0];
		uint32_t seedDegree = 0;
		for(uint32_t s : group.second) {
			uint32_t degree = 0;
			for(const auto& edge : _coOccurrence) {
				uint32_t lo = edge.first.first, hi = edge.first.second;
				if(s == lo || s == hi) {
					degree += edge.second.Count();
				}
			}
			if(degree > seedDegree) {
				seedDegree = degree;
				seed = s;
			}
		}

		std::map<uint32_t, bool> inObject;
		for(uint32_t s : group.second) {
			inObject[s] = true;
		}
		std::map<uint32_t, bool> visited;
		visited[seed] = true;
		placed[seed] = { 0, 0 };
		queue.push_back(seed);
		for(size_t qi = 0; qi < queue.size(); qi++) {
			uint32_t a = queue[qi];
			std::pair<int32_t, int32_t> aPos = placed[a];
			for(const auto& edge : _coOccurrence) {
				uint32_t lo = edge.first.first, hi = edge.first.second;
				if(a != lo && a != hi) {
					continue;
				}
				if(!inObject[lo] || !inObject[hi]) {
					continue;
				}
				bool east = edge.second.ECount >= edge.second.SCount;
				uint32_t b = (a == lo) ? hi : lo;
				if(visited[b]) {
					continue;
				}
				visited[b] = true;
				std::pair<int32_t, int32_t> offset = east ? std::pair<int32_t, int32_t>(1, 0) : std::pair<int32_t, int32_t>(0, 1);
				std::pair<int32_t, int32_t> bPos = (a == lo) ? std::make_pair(aPos.first + offset.first, aPos.second + offset.second)
				                                             : std::make_pair(aPos.first - offset.first, aPos.second - offset.second);
				placed[b] = bPos;
				minX = std::min(minX, bPos.first);
				minY = std::min(minY, bPos.second);
				maxX = std::max(maxX, bPos.first);
				maxY = std::max(maxY, bPos.second);
				queue.push_back(b);
			}
		}

		//Unreachable members (should not happen inside one connected component)
		//are appended in a fresh row so nothing silently drops.
		int nextCell = maxX + 1;
		for(uint32_t s : group.second) {
			if(!visited[s]) {
				placed[s] = { nextCell++, 0 };
				maxX = std::max(maxX, nextCell - 1);
			}
		}

		int width = maxX - minX + 1;
		int height = maxY - minY + 1;
		int tileDimension = 8 * _hdData.Scale;
		int sheetWidth = width * tileDimension;
		int sheetHeight = height * tileDimension;
		std::vector<uint32_t> sheetBuffer((size_t)sheetWidth * sheetHeight, 0xFFFF00FF);

		stringstream cellOrder;
		for(const auto& kv : placed) {
			HdPackTileInfo* art = FindObjectArt(kv.first, bestByShape);
			if(!art) {
				continue;
			}
			if(art->HdTileData.empty()) {
				GenerateHdTile(art);
				art->UpdateFlags();
			}
			int cx = kv.second.first - minX;
			int cy = kv.second.second - minY;
			for(int i = 0; i < tileDimension; i++) {
				for(int j = 0; j < tileDimension; j++) {
					sheetBuffer[(size_t)(cy * tileDimension + i) * sheetWidth + (cx * tileDimension + j)] = art->HdTileData[(size_t)i * tileDimension + j];
				}
			}
			cellOrder << "# inferred   cell " << (cy * width + cx) << " = tile " << HexUtilities::ToHex(art->TileIndex) << " palette " << HexUtilities::ToHex(art->PaletteColors, true) << std::endl;
		}

		namespace fs = std::filesystem;
		std::error_code ec;
		fs::create_directories(fs::u8path(FolderUtilities::CombinePath(_saveFolder, "textures/sheets")), ec);
		string sheetName = "object" + std::to_string(objectIndex) + ".png";
		PNGHelper::WritePNG(FolderUtilities::CombinePath(FolderUtilities::CombinePath(_saveFolder, "textures/sheets"), sheetName), sheetBuffer.data(), sheetWidth, sheetHeight, 32);

		tileRows << std::endl << "# inferred object " << objectIndex << " -> textures/sheets/" << sheetName << std::endl;
		tileRows << cellOrder.str();

		//"# inferred" tileNearby condition candidates: for every object edge seen
		//at least 3 times, define a condition that fires when the higher-hash shape
		//is at the dominant 8px offset of the lower-hash one. Inert by design - the
		//artist wires it to a <tile> ([name]<tile>) only after verifying the pair
		//really co-occurs, so a wrong inference can never make a tile fail to render.
		int edgeIndex = 0;
		for(const auto& edge : _coOccurrence) {
			uint32_t lo = edge.first.first, hi = edge.first.second;
			if(!inObject[lo] || !inObject[hi] || edge.second.Count() < 3) {
				continue;
			}
			bool east = edge.second.ECount >= edge.second.SCount;
			HdPackTileInfo* target = FindObjectArt(hi, bestByShape);
			if(!target) {
				continue;
			}
			string condName = "obj" + std::to_string(objectIndex) + "_nearby" + std::to_string(edgeIndex++);
			bool alreadyDefined = false;
			for(unique_ptr<HdPackCondition>& existing : _hdData.Conditions) {
				if(existing->Name == condName) {
					alreadyDefined = true;
					break;
				}
			}
			if(alreadyDefined) {
				continue;
			}

			HdPackTileNearbyCondition* cond = new HdPackTileNearbyCondition();
			cond->Name = condName;
			uint32_t palette = target->PaletteColors;
			string tileData;
			int32_t tileIndex = -1;
			bool ignorePalette = false;
			if(target->IsChrRamTile) {
				for(int i = 0; i < 16; i++) {
					tileData += HexUtilities::ToHex(target->TileData[i]);
				}
				ignorePalette = true;
			} else {
				tileIndex = target->TileIndex;
			}
			cond->Initialize(east ? 8 : 0, east ? 0 : 8, palette, tileIndex, tileData, ignorePalette);
			_hdData.Conditions.push_back(unique_ptr<HdPackCondition>(cond));

			tileRows << "# inferred   tileNearby: attach [" << condName << "] to tile " << HexUtilities::ToHex(FindObjectArt(lo, bestByShape)->TileIndex)
			         << " to require tile " << HexUtilities::ToHex(target->TileIndex) << " " << (east ? "8px east" : "8px south") << std::endl;
		}

		objectIndex++;
	}
}

void HdPackBuilder::AddTile(HdPackTileInfo* tile, uint32_t usageCount)
{
	bool isTileBlank = _options.GroupBlankTiles ? tile->Blank : false;

	int chrBankId = isTileBlank ? 0xFFFFFFFF : tile->ChrBankId;
	int palette = isTileBlank ? _blankTilePalette : tile->PaletteColors;

	if(_tilesByChrBankByPalette.find(chrBankId) == _tilesByChrBankByPalette.end()) {
		_tilesByChrBankByPalette[chrBankId] = std::map<uint32_t, vector<HdPackTileInfo*>>();
	}

	std::map<uint32_t, vector<HdPackTileInfo*>>& paletteMap = _tilesByChrBankByPalette[chrBankId];
	if(paletteMap.find(palette) == paletteMap.end()) {
		paletteMap[palette] = vector<HdPackTileInfo*>(256, nullptr);
	}

	if(isTileBlank) {
		paletteMap[palette][_blankTileIndex] = tile;
		_blankTileIndex++;
		if(_blankTileIndex == _options.ChrRamBankSize / 16) {
			_blankTileIndex = 0;
			_blankTilePalette++;
		}
	} else {
		if(tile->TileIndex >= 0) {
			paletteMap[palette][tile->TileIndex % 256] = tile;
		} else {
			//FIXME: This will result in data loss if more than 256 tiles of the same palette exist in the hires.txt file
			//Currently this way to prevent issues when loading a CHR RAM HD pack into the recorder (because TileIndex is -1 in that case)
			for(int i = 0; i < 256; i++) {
				if(paletteMap[palette][i] == nullptr) {
					paletteMap[palette][i] = tile;
					break;
				}
			}
		}
	}

	_tilesByKey[tile->GetKey(false)] = tile;
	_tileUsageCount[tile->GetKey(false)] = usageCount;
}

void HdPackBuilder::UpdateTileUsage(const HdTileKey& exactKey, unordered_map<HdTileKey, uint32_t>::iterator usage, bool transparencyRequired)
{
	//Already captured this exact tile shape/palette combination before
	if(transparencyRequired) {
		auto existingTile = _tilesByKey.find(exactKey);
		if(existingTile != _tilesByKey.end()) {
			existingTile->second->TransparencyRequired = true;
		}
	}

	if(usage->second < 0x7FFFFFFF) {
		//Increase usage count
		usage->second++;
	}
}

void HdPackBuilder::CaptureOrCapPaletteVariant(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, uint32_t chrBankHash, bool transparencyRequired)
{
	//New palette for this tile shape - whether never seen before, or already holding
	//a DefaultTile neutral-ramp entry (AddRomTiles/AddPrgScanTiles) and/or other real
	//palette variants. Every distinct real PaletteColors value seen for the shape gets
	//its own HdPackTileInfo, up to MaxPaletteVariantsPerTile - see the field's comment
	//in HdPackBuilder.h for why that cap exists (bounding per-shape growth, not fixing
	//a wildcard collapse: ProcessTile's old wildcard fallback was already dead code).
	vector<HdPackTileInfo*>& variants = _paletteVariantsByShape[tile.GetKey(true)];
	if(variants.size() >= MaxPaletteVariantsPerTile) {
		//Cap reached: don't grow the pack further, just bump usage on the shape's most
		//recently captured variant instead of creating a new entry.
		//F5.4b follow-up (a) (ADR-0132): log once per shape so a shape that saturates
		//the cap is visible to the artist (it needs art, not ever more palette shots)
		//without spamming the log every frame the flat tile is on screen.
		uint32_t shapeHash = tile.GetKey(true).GetHashCode();
		if(_variantCapLogged.insert(shapeHash).second) {
			MessageManager::Log("[HDPack] tile shape hit the palette-variant cap (" + std::to_string(MaxPaletteVariantsPerTile) + "); keeping the last captured variant");
		}
		HdPackTileInfo* fallbackTile = variants.back();
		fallbackTile->TransparencyRequired |= transparencyRequired;
		auto fallbackUsage = _tileUsageCount.find(fallbackTile->GetKey(false));
		if(fallbackUsage != _tileUsageCount.end() && fallbackUsage->second < 0x7FFFFFFF) {
			fallbackUsage->second++;
		}
		return;
	}

	HdPackTileInfo* hdTile = new HdPackTileInfo();
	hdTile->PaletteColors = tile.PaletteColors;
	hdTile->TileIndex = tile.TileIndex;
	hdTile->DefaultTile = false;
	hdTile->IsChrRamTile = _isChrRam;
	hdTile->Brightness = 255;
	hdTile->ChrBankId = _isChrRam ? chrBankHash : (tileAddr / 16 / 256);
	hdTile->TransparencyRequired = transparencyRequired;
	memcpy(hdTile->TileData, tile.TileData, 16);

	_hdData.Tiles.push_back(unique_ptr<HdPackTileInfo>(hdTile));
	AddTile(hdTile, 1);
	variants.push_back(hdTile);
}

void HdPackBuilder::ProcessTile(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, BaseMapper* mapper, bool isSprite, uint32_t chrBankHash, bool transparencyRequired)
{
	if(_options.IgnoreOverscan) {
		OverscanDimensions overscan = _emu->GetSettings()->GetOverscan();
		if(x < overscan.Left || y < overscan.Top || (NesConstants::ScreenWidth - x - 1) < overscan.Right || (NesConstants::ScreenHeight - y - 1) < overscan.Bottom) {
			//Ignore tiles inside overscan
			return;
		}
	}

	HdTileKey exactKey = tile.GetKey(false);
	auto result = _tileUsageCount.find(exactKey);
	if(result != _tileUsageCount.end()) {
		UpdateTileUsage(exactKey, result, transparencyRequired);
	} else {
		CaptureOrCapPaletteVariant(x, y, tileAddr, tile, chrBankHash, transparencyRequired);
	}
}

uint32_t HdPackBuilder::AddRomTiles(uint8_t* chrRom, uint32_t chrRomSize)
{
	//Neutral ramp (color 0..3 = black, dark gray, light gray, white); the
	//loader ignores PaletteColors for defaultTile entries, this only decides
	//how the tile looks in the PNG the artist edits. Byte order: see ToRgb.
	constexpr uint32_t neutralPalette = 0x0F001030;

	uint32_t added = 0;
	uint32_t tileCount = chrRomSize / 16;
	for(uint32_t i = 0; i < tileCount; i++) {
		HdTileKey key = {};
		memcpy(key.TileData, chrRom + i * 16, 16);
		key.PaletteColors = neutralPalette;
		key.TileIndex = i; //absolute CHR ROM tile index (CHR ROM keys are index-based; AddTile pages by % 256)
		key.IsChrRamTile = false;

		if(_tilesByKey.find(key.GetKey(false)) != _tilesByKey.end() || _tilesByKey.find(key.GetKey(true)) != _tilesByKey.end()) {
			continue;
		}

		HdPackTileInfo* hdTile = new HdPackTileInfo();
		hdTile->PaletteColors = neutralPalette;
		hdTile->TileIndex = key.TileIndex;
		hdTile->DefaultTile = true;
		hdTile->IsChrRamTile = false;
		hdTile->Brightness = 255;
		hdTile->ChrBankId = i / 256;
		hdTile->TransparencyRequired = false;
		memcpy(hdTile->TileData, key.TileData, 16);

		_hdData.Tiles.push_back(unique_ptr<HdPackTileInfo>(hdTile));
		AddTile(hdTile, 0);
		_tilesByKey[hdTile->GetKey(true)] = hdTile;
		added++;
	}
	return added;
}

namespace
{
	bool IsFlatBlock(const uint8_t* block)
	{
		for(int i = 1; i < 16; i++) {
			if(block[i] != block[0]) {
				return false;
			}
		}
		return true;
	}

	//Silhouette churn: bits that change between consecutive rows of the union of
	//both planes (0..56). Real tiles have smooth silhouettes; code/tables don't,
	//and - unlike per-plane churn - a block misaligned by 8 bytes (plane 1 of one
	//tile + plane 0 of the next) scores clearly worse, so it also decides alignment.
	uint32_t BitCount(uint32_t v)
	{
		uint32_t n = 0;
		for(; v; v &= v - 1) {
			n++;
		}
		return n;
	}

	uint32_t SilhouetteChurn(const uint8_t* block)
	{
		uint32_t churn = 0;
		for(int i = 0; i < 7; i++) {
			uint8_t a = block[i] | block[i + 8];
			uint8_t b = block[i + 1] | block[i + 9];
			churn += BitCount((uint32_t)(a ^ b));
		}
		return churn;
	}
}

uint32_t HdPackBuilder::AddPrgScanTiles(uint8_t* prgRom, uint32_t prgRomSize)
{
	constexpr uint32_t neutralPalette = 0x0F001030;
	constexpr uint32_t bankSize = 0x1000; //alignment is voted per 4 KB (graphics blocks are bank-sized)
	constexpr uint32_t maxChurn = 18; //calibrated on Zelda/Castlevania/Mega Man: ~90% of drawn tiles, few false positives
	constexpr uint32_t minRun = 4; //tiles come in sets (fonts, sprites, metatiles)

	uint32_t added = 0;
	auto addBlock = [&](const uint8_t* block) {
		HdTileKey key = {};
		memcpy(key.TileData, block, 16);
		key.PaletteColors = neutralPalette;
		key.TileIndex = 0;
		key.IsChrRamTile = true;
		if(_tilesByKey.find(key.GetKey(false)) != _tilesByKey.end() || _tilesByKey.find(key.GetKey(true)) != _tilesByKey.end()) {
			return;
		}
		HdPackTileInfo* hdTile = new HdPackTileInfo();
		hdTile->PaletteColors = neutralPalette;
		//Synthetic "PRG" banks of 256 tiles: SaveHdPack lays tiles out by bank/index
		hdTile->TileIndex = added % 256;
		hdTile->DefaultTile = true;
		hdTile->IsChrRamTile = true;
		hdTile->Brightness = 255;
		hdTile->ChrBankId = 0x50524700 + added / 256;
		hdTile->TransparencyRequired = false;
		memcpy(hdTile->TileData, key.TileData, 16);
		_hdData.Tiles.push_back(unique_ptr<HdPackTileInfo>(hdTile));
		AddTile(hdTile, 0);
		_tilesByKey[hdTile->GetKey(true)] = hdTile;
		added++;
	};

	for(uint32_t bankStart = 0; bankStart < prgRomSize; bankStart += bankSize) {
		uint32_t bankEnd = std::min(prgRomSize, bankStart + bankSize);

		//1) alignment: the offset whose non-flat blocks have the smoothest silhouettes
		int bestOffset = -1;
		double bestScore = 0;
		for(uint32_t offset = 0; offset < 16; offset++) {
			uint32_t sum = 0, count = 0;
			for(uint32_t pos = bankStart + offset; pos + 16 <= bankEnd; pos += 16) {
				if(!IsFlatBlock(prgRom + pos)) {
					sum += SilhouetteChurn(prgRom + pos);
					count++;
				}
			}
			if(count == 0) {
				continue;
			}
			double score = (double)sum / count;
			if(bestOffset < 0 || score < bestScore) {
				bestOffset = (int)offset;
				bestScore = score;
			}
		}
		if(bestOffset < 0) {
			continue;
		}

		//2) runs of plausible tiles at that alignment (flat blocks may sit inside a run)
		vector<const uint8_t*> run;
		uint32_t runNonFlat = 0;
		auto flush = [&]() {
			if(runNonFlat >= minRun) {
				for(const uint8_t* block : run) {
					if(!IsFlatBlock(block)) {
						addBlock(block);
					}
				}
			}
			run.clear();
			runNonFlat = 0;
		};
		for(uint32_t pos = bankStart + bestOffset; pos + 16 <= bankEnd; pos += 16) {
			const uint8_t* block = prgRom + pos;
			if(IsFlatBlock(block)) {
				run.push_back(block);
			} else if(SilhouetteChurn(block) <= maxChurn) {
				run.push_back(block);
				runNonFlat++;
			} else {
				flush();
			}
		}
		flush();
	}
	return added;
}

void HdPackBuilder::GenerateHdTile(HdPackTileInfo* tile)
{
	uint32_t hdScale = _hdData.Scale;

	vector<uint32_t> originalTile = tile->ToRgb(_palette);
	vector<uint32_t> hdTile(8 * 8 * hdScale * hdScale, 0);

	switch(_options.FilterType) {
		case ScaleFilterType::HQX:
			hqx(hdScale, originalTile.data(), hdTile.data(), 8, 8);
			break;

		case ScaleFilterType::Prescale:
			hdTile.clear();
			for(uint8_t i = 0; i < 8 * hdScale; i++) {
				for(uint8_t j = 0; j < 8 * hdScale; j++) {
					hdTile.push_back(originalTile[i / hdScale * 8 + j / hdScale]);
				}
			}
			break;

		case ScaleFilterType::Scale2x:
			scale(hdScale, hdTile.data(), 8 * sizeof(uint32_t) * hdScale, originalTile.data(), 8 * sizeof(uint32_t), 4, 8, 8);
			break;

		case ScaleFilterType::_2xSai:
			twoxsai_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * hdScale);
			break;

		case ScaleFilterType::Super2xSai:
			supertwoxsai_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * hdScale);
			break;

		case ScaleFilterType::SuperEagle:
			supereagle_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * hdScale);
			break;

		case ScaleFilterType::xBRZ:
			xbrz::scale(hdScale, originalTile.data(), hdTile.data(), 8, 8, xbrz::ColorFormat::ARGB);
			break;
	}

	tile->HdTileData = hdTile;
}

void HdPackBuilder::DrawTile(HdPackTileInfo* tile, int tileNumber, uint32_t* pngBuffer, int pageNumber, bool containsSpritesOnly)
{
	if(tile->HdTileData.empty()) {
		GenerateHdTile(tile);
		tile->UpdateFlags();
	}

	if(containsSpritesOnly && _options.UseLargeSprites) {
		int row = tileNumber / 16;
		int column = tileNumber % 16;

		int newColumn = column / 2 + ((row & 1) ? 8 : 0);
		int newRow = (row & 0xFE) + ((column & 1) ? 1 : 0);

		tileNumber = newRow * 16 + newColumn;
	}

	tileNumber += pageNumber * (256 / (0x1000 / _options.ChrRamBankSize));

	int tileDimension = 8 * _hdData.Scale;
	int x = tileNumber % 16 * tileDimension;
	int y = tileNumber / 16 * tileDimension;

	tile->X = x;
	tile->Y = y;

	int pngWidth = 128 * _hdData.Scale;
	int pngPos = y * pngWidth + x;
	int tilePos = 0;
	for(uint8_t i = 0; i < tileDimension; i++) {
		for(uint8_t j = 0; j < tileDimension; j++) {
			pngBuffer[pngPos] = tile->HdTileData[tilePos++];
			pngPos++;
		}
		pngPos += pngWidth - tileDimension;
	}

	if(_writeReferences) {
		//Unfiltered twin (nearest neighbour) for the artist's reference sheet
		if(_origBuffer.size() != (size_t)pngWidth * pngWidth) {
			_origBuffer.assign((size_t)pngWidth * pngWidth, 0xFFFF00FF);
		}
		vector<uint32_t> rgb = tile->ToRgb(_palette);
		uint32_t s = _hdData.Scale;
		for(int i = 0; i < tileDimension; i++) {
			for(int j = 0; j < tileDimension; j++) {
				_origBuffer[(size_t)(y + i) * pngWidth + x + j] = rgb[(i / s) * 8 + j / s];
			}
		}
	}
}

void HdPackBuilder::EnableScreenCapture()
{
	_captureScreens = true;
	_writeReferences = true;
	_frameBg.assign(256 * 240, 0);
	_frameRuns.reserve(4096);
	//Screens already in the pack (previous session) keep their numbering
	_screensSeen.clear();
}

void HdPackBuilder::OnFrameEnd()
{
	if(!_captureScreens) {
		return;
	}

	//F5.4e: accumulate this frame's background-tile adjacency pairs into the
	//co-occurrence graph (grid filled in ProcessBgPixel), then reset the grid.
	AccumulateCoOccurrence();

	//A screen worth keeping is mostly drawn and holds still for a while
	bool candidate = _bgPixels >= 256 * 240 / 2 && _frameRuns.size() >= 60;
	if(candidate && _frameHash == _prevFrameHash) {
		_stableFrames++;
		if(_stableFrames == StableFramesNeeded && _screensSeen.find(_frameHash) == _screensSeen.end()) {
			_screensSeen.insert(_frameHash);
			if(_hdData.BackgroundFileData.size() < MaxScreensPerSession) {
				CaptureScreen();
			}
		}
	} else {
		_stableFrames = 0;
	}
	_prevFrameHash = candidate ? _frameHash : 0;
	_frameHash = 0;
	_bgPixels = 0;
	_frameRuns.clear();
	_lastRunY = -1;
	std::fill(_frameBg.begin(), _frameBg.end(), 0);
}

void HdPackBuilder::CaptureScreen()
{
	uint32_t scale = _hdData.Scale;
	uint32_t number = (uint32_t)_hdData.BackgroundFileData.size() + 1;
	char buf[32];
	snprintf(buf, sizeof(buf), "screen%03u", number);
	string baseName = buf;
	string relPath = "backgrounds/" + baseName + ".png";

	//Whole-frame upscale: better seams than the per-tile result
	vector<uint32_t> hd(256 * 240 * scale * scale, 0);
	if(_options.FilterType == ScaleFilterType::xBRZ && scale >= 2 && scale <= 6) {
		xbrz::scale(scale, _frameBg.data(), hd.data(), 256, 240, xbrz::ColorFormat::ARGB);
	} else {
		for(uint32_t y = 0; y < 240 * scale; y++) {
			for(uint32_t x = 0; x < 256 * scale; x++) {
				hd[y * 256 * scale + x] = _frameBg[(y / scale) * 256 + x / scale];
			}
		}
	}
	FolderUtilities::CreateFolder(FolderUtilities::CombinePath(_saveFolder, "backgrounds"));
	if(!PNGHelper::WritePNG(FolderUtilities::CombinePath(_saveFolder, relPath), hd.data(), 256 * scale, 240 * scale, 32)) {
		return;
	}
	if(_writeReferences) {
		vector<uint32_t> orig(256 * 240 * scale * scale, 0);
		for(uint32_t y = 0; y < 240 * scale; y++) {
			for(uint32_t x = 0; x < 256 * scale; x++) {
				orig[y * 256 * scale + x] = _frameBg[(y / scale) * 256 + x / scale];
			}
		}
		PNGHelper::WritePNG(FolderUtilities::CombinePath(_saveFolder, "backgrounds/" + baseName + ".orig.png"), orig.data(), 256 * scale, 240 * scale, 32);
	}

	//Anchors: the rarest non-flat tiles on screen, spread apart (3 tileAtPosition
	//conditions make a false match on another screen very unlikely)
	auto isFlat = [](HdTileKey& k) {
		for(int i = 1; i < 16; i++) {
			if(k.TileData[i] != k.TileData[0]) {
				return false;
			}
		}
		return true;
	};
	vector<ScreenRun*> ranked;
	for(ScreenRun& run : _frameRuns) {
		if(!isFlat(run.Tile)) {
			ranked.push_back(&run);
		}
	}
	std::stable_sort(ranked.begin(), ranked.end(), [this](ScreenRun* a, ScreenRun* b) {
		auto ua = _tileUsageCount.find(a->Tile.GetKey(false));
		auto ub = _tileUsageCount.find(b->Tile.GetKey(false));
		uint32_t ca = ua == _tileUsageCount.end() ? 0 : ua->second;
		uint32_t cb = ub == _tileUsageCount.end() ? 0 : ub->second;
		return ca < cb;
	});
	vector<ScreenRun*> anchors;
	for(ScreenRun* run : ranked) {
		bool farEnough = true;
		for(ScreenRun* a : anchors) {
			if(std::abs((int)a->X - (int)run->X) + std::abs((int)a->Y - (int)run->Y) < 64) {
				farEnough = false;
				break;
			}
		}
		if(farEnough) {
			anchors.push_back(run);
		}
		if(anchors.size() == 3) {
			break;
		}
	}
	if(anchors.empty()) {
		return;
	}

	unique_ptr<HdPackBitmapInfo> bitmap(new HdPackBitmapInfo());
	bitmap->PngName = relPath;
	HdBackgroundInfo bg = {};
	bg.Data = bitmap.get();
	bg.Brightness = 255;
	bg.HorizontalScrollRatio = 0;
	bg.VerticalScrollRatio = 0;
	bg.Priority = 20; //BehindFgSpritesPriority: covers the tiles, stays under the sprites
	bg.Left = 0;
	bg.Top = 0;
	bg.BlendMode = HdPackBlendMode::Alpha;
	const char* suffix = "ABC";
	for(size_t i = 0; i < anchors.size(); i++) {
		HdPackTileAtPositionCondition* cond = new HdPackTileAtPositionCondition();
		cond->Name = baseName + "_" + suffix[i];
		string tileData;
		if(_isChrRam) {
			for(int j = 0; j < 16; j++) {
				tileData += HexUtilities::ToHex(anchors[i]->Tile.TileData[j]);
			}
		}
		cond->Initialize(anchors[i]->X, anchors[i]->Y, anchors[i]->Tile.PaletteColors, anchors[i]->Tile.TileIndex, tileData, false);
		bg.Conditions.push_back(cond);
		_hdData.Conditions.push_back(unique_ptr<HdPackCondition>(cond));
	}
	_hdData.BackgroundFileData.push_back(std::move(bitmap));
	_hdData.BackgroundsByPriority[bg.Priority].push_back(bg);
	MessageManager::Log("[HDPack] bootstrap: static screen captured -> " + relPath + " (" + std::to_string(anchors.size()) + " anchor tile(s))");
}

void HdPackBuilder::SaveHdPack()
{
	FolderUtilities::CreateFolder(_saveFolder);

	stringstream pngRows;
	stringstream tileRows;
	stringstream ss;
	int pngIndex = 0;
	ss << "<ver>" << std::to_string(BaseHdNesPack::CurrentVersion) << std::endl;
	ss << "<scale>" << _hdData.Scale << std::endl;
	ss << "<supportedRom>" << _emu->GetRomInfo().RomFile.GetSha1Hash() << std::endl;
	if(_options.IgnoreOverscan) {
		OverscanDimensions overscan = _emu->GetSettings()->GetOverscan();
		ss << "<overscan>" << overscan.Top << "," << overscan.Right << "," << overscan.Bottom << "," << overscan.Left << std::endl;
	}

	int tileDimension = 8 * _hdData.Scale;
	int pngDimension = 16 * tileDimension;
	int pngBufferSize = pngDimension * pngDimension;
	uint32_t* pngBuffer = new uint32_t[pngBufferSize];

	int maxPageNumber = 0x1000 / _options.ChrRamBankSize;
	int pageNumber = 0;
	bool pngEmpty = true;
	int pngNumber = 0;

	for(int i = 0; i < pngBufferSize; i++) {
		pngBuffer[i] = 0xFFFF00FF;
	}

	auto savePng = [&tileRows, &pngRows, &ss, &pngBuffer, &pngDimension, &pngIndex, &pngBufferSize, &pngEmpty, &pngNumber, this](uint32_t chrBankId) {
		if(!pngEmpty) {
			string pngName;
			if(_isChrRam) {
				pngName = "Chr_" + std::to_string(pngNumber) + ".png";
			} else {
				pngName = "Chr_" + HexUtilities::ToHex(chrBankId) + "_" + std::to_string(pngNumber) + ".png";
			}

			tileRows << std::endl;
			tileRows << "#" << pngName << std::endl;
			tileRows << pngRows.str();
			pngRows = stringstream();

			ss << "<img>" << pngName << std::endl;
			PNGHelper::WritePNG(FolderUtilities::CombinePath(_saveFolder, pngName), pngBuffer, pngDimension, pngDimension, 32);
			if(_writeReferences && !_origBuffer.empty()) {
				PNGHelper::WritePNG(FolderUtilities::CombinePath(_saveFolder, pngName.substr(0, pngName.size() - 4) + ".orig.png"), _origBuffer.data(), pngDimension, pngDimension, 32);
				std::fill(_origBuffer.begin(), _origBuffer.end(), 0xFFFF00FF);
			}
			pngNumber++;
			pngIndex++;

			for(int i = 0; i < pngBufferSize; i++) {
				pngBuffer[i] = 0xFFFF00FF;
			}
			pngEmpty = true;
		}
	};

	for(std::pair<const uint32_t, std::map<uint32_t, vector<HdPackTileInfo*>>>& kvp : _tilesByChrBankByPalette) {
		if(_options.SortByUsageFrequency) {
			for(int i = 0; i < 256; i++) {
				vector<std::pair<uint32_t, HdPackTileInfo*>> tiles;
				for(std::pair<const uint32_t, vector<HdPackTileInfo*>>& paletteMap : kvp.second) {
					if(paletteMap.second[i]) {
						tiles.push_back({ _tileUsageCount[paletteMap.second[i]->GetKey(false)], paletteMap.second[i] });
					}
				}
				std::sort(tiles.begin(), tiles.end(), [=](std::pair<uint32_t, HdPackTileInfo*>& a, std::pair<uint32_t, HdPackTileInfo*>& b) {
					return a.first > b.first;
				});

				size_t j = 0;
				for(std::pair<const uint32_t, vector<HdPackTileInfo*>>& paletteMap : kvp.second) {
					if(j < tiles.size()) {
						paletteMap.second[i] = tiles[j].second;
						j++;
					} else {
						paletteMap.second[i] = nullptr;
					}
				}
			}
		}

		if(!_isChrRam) {
			pngNumber = 0;
		}

		for(std::pair<const uint32_t, vector<HdPackTileInfo*>>& tileKvp : kvp.second) {
			bool pageEmpty = true;
			bool spritesOnly = true;
			for(HdPackTileInfo* tileInfo : tileKvp.second) {
				if(tileInfo && !tileInfo->IsSpriteTile()) {
					spritesOnly = false;
				}
			}

			for(int i = 0; i < 256; i++) {
				HdPackTileInfo* tileInfo = tileKvp.second[i];
				if(tileInfo) {
					DrawTile(tileInfo, i, pngBuffer, pageNumber, spritesOnly);

					pngRows << tileInfo->ToString(pngIndex) << std::endl;

					pageEmpty = false;
					pngEmpty = false;
				}
			}

			if(!pageEmpty) {
				pageNumber++;

				if(pageNumber == maxPageNumber) {
					savePng(kvp.first);
					pageNumber = 0;
				}
			}
		}
	}
	savePng(-1);

	//F5.4e: cluster the co-occurrence graph into per-object editable sheets and
	//emit "# inferred" tileNearby candidates. Runs before the conditions loop so
	//the inferred condition definitions serialize ahead of every <tile> line.
	BuildObjectSheets(tileRows);

	for(unique_ptr<HdPackCondition>& condition : _hdData.Conditions) {
		if(!condition->IsExcludedFromFile()) {
			ss << condition->ToString() << std::endl;
		}
	}

	for(int i = 0; i < HdPackData::BgLayerCount; i++) {
		for(HdBackgroundInfo& bgInfo : _hdData.BackgroundsByPriority[i]) {
			ss << bgInfo.ToString() << std::endl;
		}
	}

	for(auto& bgmInfo : _hdData.BgmFilesById) {
		ss << "<bgm>" << std::to_string(bgmInfo.first >> 8) << "," << std::to_string(bgmInfo.first & 0xFF) << "," << VirtualFile(bgmInfo.second.Filename).GetFileName();
		if(bgmInfo.second.LoopPosition > 0) {
			ss << "," << std::to_string(bgmInfo.second.LoopPosition);
		}
		ss << std::endl;
	}

	for(auto& sfxInfo : _hdData.SfxFilesById) {
		ss << "<sfx>" << std::to_string(sfxInfo.first >> 8) << "," << std::to_string(sfxInfo.first & 0xFF) << "," << VirtualFile(sfxInfo.second).GetFileName() << std::endl;
	}

	for(auto& patchInfo : _hdData.PatchesByHash) {
		ss << "<patch>" << VirtualFile(patchInfo.second).GetFileName() << "," << patchInfo.first << std::endl;
	}

	if(_hdData.OptionFlags != 0) {
		ss << "<options>";
		if(_hdData.OptionFlags & (int)HdPackOptions::NoSpriteLimit) {
			ss << "disableSpriteLimit,";
		}
		if(_hdData.OptionFlags & (int)HdPackOptions::AlternateRegisterRange) {
			ss << "alternateRegisterRange,";
		}
		if(_hdData.OptionFlags & (int)HdPackOptions::DisableCache) {
			ss << "disableCache,";
		}
		if(_hdData.OptionFlags & (int)HdPackOptions::DontRenderOriginalTiles) {
			ss << "disableOriginalTiles,";
		}
		if(_hdData.OptionFlags & (int)HdPackOptions::AutomaticFallbackTiles) {
			ss << "automaticFallbackTiles,";
		}
	}

	ss << tileRows.str();

	ofstream hiresFile(FolderUtilities::CombinePath(_saveFolder, "hires.txt"), ios::out);
	hiresFile << ss.str();
	hiresFile.close();

	delete[] pngBuffer;
}
/*
void HdPackBuilder::GetChrBankList(uint32_t *banks)
{
	ConsolePauseHelper helper(_instance->_console.get());
	for(std::pair<const uint32_t, std::map<uint32_t, vector<HdPackTileInfo*>>> &kvp : _instance->_tilesByChrBankByPalette) {
		*banks = kvp.first;
		banks++;
	}
	*banks = -1;
}

void HdPackBuilder::GetBankPreview(uint32_t bankNumber, uint32_t pageNumber, uint32_t *rgbBuffer)
{
	ConsolePauseHelper helper(_instance->_console.get());

	for(uint32_t i = 0; i < 128 * 128 * _instance->_hdData.Scale*_instance->_hdData.Scale; i++) {
		rgbBuffer[i] = 0xFF666666;
	}

	auto result = _instance->_tilesByChrBankByPalette.find(bankNumber);
	if(result != _instance->_tilesByChrBankByPalette.end()) {
		std::map<uint32_t, vector<HdPackTileInfo*>> bankData = result->second;

		if(_instance->_flags & HdPackRecordFlags::SortByUsageFrequency) {
			for(int i = 0; i < 256; i++) {
				vector<std::pair<uint32_t, HdPackTileInfo*>> tiles;
				for(std::pair<const uint32_t, vector<HdPackTileInfo*>> &pageData : bankData) {
					if(pageData.second[i]) {
						tiles.push_back({ _instance->_tileUsageCount[pageData.second[i]->GetKey(false)], pageData.second[i] });
					}
				}

				std::sort(tiles.begin(), tiles.end(), [=](std::pair<uint32_t, HdPackTileInfo*> &a, std::pair<uint32_t, HdPackTileInfo*> &b) {
					return a.first > b.first;
				});

				size_t j = 0;
				for(std::pair<const uint32_t, vector<HdPackTileInfo*>> &pageData : bankData) {
					if(j < tiles.size()) {
						pageData.second[i] = tiles[j].second;
						j++;
					} else {
						pageData.second[i] = nullptr;
					}
				}
			}
		}

		bool spritesOnly = true;
		for(HdPackTileInfo* tileInfo : (*bankData.begin()).second) {
			if(tileInfo && !tileInfo->IsSpriteTile()) {
				spritesOnly = false;
			}
		}

		for(int i = 0; i < 256; i++) {
			HdPackTileInfo* tileInfo = (*bankData.begin()).second[i];
			if(tileInfo) {
				_instance->DrawTile(tileInfo, i, (uint32_t*)rgbBuffer, 0, spritesOnly);
			}
		}
	}
}
*/