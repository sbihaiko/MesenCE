#include "pch.h"
#include <filesystem>
#include <algorithm>
#include <queue>
#include "NES/HdPacks/HdPackBuilder.h"
#include "NES/HdPacks/HdNesPack.h"
#include "NES/BaseMapper.h"
#include "NES/BaseNesPpu.h"
#include "NES/NesConstants.h"
#include "NES/HdPacks/HdPackLoader.h"
#include "NES/HdPacks/HdPackConditions.h"
#include "NES/HdPacks/MetatileVocabulary.h"
#include "NES/HdPacks/ScreenStitcher.h"
#include "NES/HdPacks/SheetGrouping.h"
#include "NES/HdPacks/SheetRender.h"
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

//ADR-0153 retires F5.4e's clustering (union-find over pairs seen adjacent >= 2
//times): on every real game it collapsed the whole scene into one component,
//so no object sheet was ever emitted. The sheets now come from the metatile
//pipeline (BuildSheets / WriteObjectSheets). What survives here, unchanged, is
//F5.4e's *inert* contract: for a pair of shapes that a real object is made of,
//define a tileNearby condition the artist may wire to a <tile> by hand. Never
//auto-attached - a wrong inference must not make a tile fail to render.
void HdPackBuilder::BuildObjectSheets(stringstream& tileRows)
{
	if(_objectsBuilt || _coOccurrence.empty() || _sheetObjectShapes.empty()) {
		return;
	}
	_objectsBuilt = true;

	//Most-used non-default art per shape, the tileNearby target data.
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

	tileRows << std::endl << "# inferred " << _sheetObjectCount << " object sheet(s) -> sheets/objNNN.png" << std::endl;

	int edgeIndex = 0;
	for(const auto& edge : _coOccurrence) {
		uint32_t lo = edge.first.first, hi = edge.first.second;
		if(edge.second.Count() < 3) {
			continue;
		}
		if(_sheetObjectShapes.find(lo) == _sheetObjectShapes.end() || _sheetObjectShapes.find(hi) == _sheetObjectShapes.end()) {
			continue;
		}
		HdPackTileInfo* source = FindObjectArt(lo, bestByShape);
		HdPackTileInfo* target = FindObjectArt(hi, bestByShape);
		if(!source || !target) {
			continue;
		}

		string condName = "obj_nearby" + std::to_string(edgeIndex++);
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

		bool east = edge.second.ECount >= edge.second.SCount;
		HdPackTileNearbyCondition* cond = new HdPackTileNearbyCondition();
		cond->Name = condName;
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
		cond->Initialize(east ? 8 : 0, east ? 0 : 8, target->PaletteColors, tileIndex, tileData, ignorePalette);
		_hdData.Conditions.push_back(unique_ptr<HdPackCondition>(cond));

		tileRows << "# inferred   tileNearby: attach [" << condName << "] to tile " << HexUtilities::ToHex(source->TileIndex)
		         << " to require tile " << HexUtilities::ToHex(target->TileIndex) << " " << (east ? "8px east" : "8px south") << std::endl;
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

	//F9.1 (ADR-0153): keep this frame's background grid for the sheet inference
	//that runs once at save time.
	RecordGridFrame();

	//F9.5: close the OAM snapshot HdBuilderPpu filled in during this frame.
	RecordOamFrame();

	//A screen worth keeping is mostly drawn and holds still for a while
	bool candidate = _bgPixels >= 256 * 240 / 2 && _frameRuns.size() >= 60;
	if(candidate && _frameHash == _prevFrameHash) {
		_stableFrames++;
		if(_stableFrames == StableFramesNeeded && _screensSeen.find(_frameHash) == _screensSeen.end()) {
			_screensSeen.insert(_frameHash);
			if(_hdData.BackgroundFileData.size() < MaxScreensPerSession) {
				size_t before = _hdData.BackgroundFileData.size();
				CaptureScreen();
				//F9.9 (ADR-0156): tie the screen that was just written back to
				//the grid frame it was written from, so the inference can tell
				//"a <background> covers this" from "this only ever showed as
				//tiles". Only on a real write - CaptureScreen bails out when
				//the PNG fails or the screen has no usable anchor, and a screen
				//that was never written covers nothing.
				if(_gridFrameLive && _hdData.BackgroundFileData.size() > before) {
					_gridFrames.back().Captured = true;
				}
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

//F9.1 (ADR-0153 §5): turn this frame's background runs into a compact
//GridFrame. Ported from the spike's frame_grid (scripts/spike_tile_sheets.py):
//run starts sit on tile boundaries, so the most common (x % 8) among non-zero
//run starts is the frame's fine x scroll, and cells are laid out relative to
//it - two frames of the same screen at different sub-tile offsets then compare
//equal. Consecutive duplicates collapse into RepeatCount and the stream is
//capped at kMaxSheetFrames, so a long session costs late-game vocabulary,
//never correctness.
void HdPackBuilder::RecordGridFrame()
{
	//Set again below once this frame really is _gridFrames.back(); a dropped
	//frame (empty runs, or the retention cap) must never let CaptureScreen
	//flag some older frame as the one it just wrote out.
	_gridFrameLive = false;
	if(_frameRuns.empty() || _gridFrames.size() >= MesenSheets::kMaxSheetFrames) {
		return;
	}

	uint32_t fineCounts[8] = {};
	for(const ScreenRun& run : _frameRuns) {
		if(run.X != 0) {
			fineCounts[run.X & 7]++;
		}
	}
	uint8_t fine = 0;
	for(uint8_t i = 1; i < 8; i++) {
		if(fineCounts[i] > fineCounts[fine]) {
			fine = i;
		}
	}

	MesenSheets::GridFrame frame;
	frame.FineX = fine;
	for(size_t i = 0; i < _frameRuns.size(); i++) {
		const ScreenRun& run = _frameRuns[i];
		if((run.Y & 7) != 0) {
			continue;
		}
		uint32_t row = (uint32_t)run.Y >> 3;
		if(row >= MesenSheets::kGridRows) {
			continue;
		}
		//The run ends where the next run on the same scanline starts
		uint32_t xEnd = (i + 1 < _frameRuns.size() && _frameRuns[i + 1].Y == run.Y) ? _frameRuns[i + 1].X : 256;
		int32_t offset = ((int32_t)run.X - (int32_t)fine) % 8;
		if(offset < 0) {
			offset += 8;
		}
		uint32_t cx = offset == 0 ? run.X : run.X + (8 - offset);
		MesenSheets::ShapeId shape = ShapeIdFor(run.Tile);
		if(shape == MesenSheets::kEmptyCell) {
			continue;
		}
		for(; cx + 8 <= 256 && cx < xEnd; cx += 8) {
			int32_t col = ((int32_t)cx - (int32_t)fine) / 8;
			if(col >= 0 && col < (int32_t)MesenSheets::kGridCols) {
				frame.Cells[row][col] = shape;
			}
		}
	}

	if(!_gridFrames.empty() && _gridFrames.back().FineX == frame.FineX && _gridFrames.back().SameCells(frame)) {
		_gridFrames.back().RepeatCount++;
		_gridFrameLive = true;
		return;
	}
	frame.FrameNumber = (uint32_t)_gridFrames.size();
	_gridFrames.push_back(frame);
	_gridFrameLive = true;
}

//F9.5 (ADR-0153 §2): one on-screen sprite. The shape id comes from the same
//space as the background grid's, so a single TileLookup serves every sheet -
//and because HdBuilderPpu applies the OAM flip bits to TileData before calling
//in, the left and right halves of a mirrored figure are distinct shapes and can
//sit side by side on the sheet instead of collapsing into one cell.
void HdPackBuilder::RecordSprite(uint8_t x, uint8_t y, HdPpuTileInfo& tile)
{
	if(!_captureScreens || _oamFrames.size() >= MesenSheets::kMaxSheetFrames || _frameOam.Entries.size() >= 128) {
		return;
	}
	MesenSheets::ShapeId shape = ShapeIdFor(tile);
	if(shape == MesenSheets::kEmptyCell) {
		return;
	}
	MesenSheets::OamEntry entry;
	entry.Shape = shape;
	entry.X = x;
	entry.Y = y;
	_frameOam.Entries.push_back(entry);
}

//De-duplication mirrors RecordGridFrame: a screen that holds still must not
//manufacture the evidence the grouping criterion asks for.
void HdPackBuilder::RecordOamFrame()
{
	if(_frameOam.Entries.empty()) {
		return;
	}
	if(_oamFrames.size() >= MesenSheets::kMaxSheetFrames) {
		_frameOam.Entries.clear();
		return;
	}
	if(!_oamFrames.empty() && _oamFrames.back().SameEntries(_frameOam)) {
		_oamFrames.back().RepeatCount++;
	} else {
		_frameOam.FrameNumber = (uint32_t)_oamFrames.size();
		_frameOam.RepeatCount = 1;
		_oamFrames.push_back(_frameOam);
	}
	_frameOam.Entries.clear();
}

//Shape id (palette wildcarded, first-sight order) for a recorded tile; the
//first exact variant seen becomes the shape's drawable art.
MesenSheets::ShapeId HdPackBuilder::ShapeIdFor(const HdPpuTileInfo& tile)
{
	HdTileKey shapeKey = tile.GetKey(true);
	auto it = _shapeIds.find(shapeKey);
	if(it != _shapeIds.end()) {
		return it->second;
	}
	if(_shapeTiles.size() >= MesenSheets::kEmptyCell) {
		return MesenSheets::kEmptyCell;
	}
	MesenSheets::SheetTileKey art;
	memcpy(art.TileData, tile.TileData, 16);
	art.PaletteColors = tile.PaletteColors;
	MesenSheets::ShapeId id = (MesenSheets::ShapeId)_shapeTiles.size();
	_shapeTiles.push_back(art);
	_shapeHashes.push_back(shapeKey.GetHashCode());
	_shapeIds[shapeKey] = id;
	return id;
}

//ADR-0153 §7: the recorded grid stream in the text format
//scripts/spike_tile_sheets.py parses, written once at save time so threshold
//tuning can iterate offline without rebuilding the core.
void HdPackBuilder::WriteGridDump(const string& path) const
{
	ofstream dump(path, ios::out);
	if(!dump) {
		return;
	}
	std::vector<bool> emitted(_shapeTiles.size(), false);
	for(const MesenSheets::GridFrame& frame : _gridFrames) {
		for(uint32_t repeat = 0; repeat < frame.RepeatCount; repeat++) {
			dump << "F " << frame.FrameNumber << std::endl;
			for(uint32_t row = 0; row < MesenSheets::kGridRows; row++) {
				for(uint32_t col = 0; col < MesenSheets::kGridCols; col++) {
					MesenSheets::ShapeId id = frame.Cells[row][col];
					if(id == MesenSheets::kEmptyCell || id >= _shapeTiles.size()) {
						continue;
					}
					if(!emitted[id]) {
						emitted[id] = true;
						dump << "K " << id << " ";
						for(int b = 0; b < 16; b++) {
							dump << HexUtilities::ToHex(_shapeTiles[id].TileData[b]);
						}
						dump << " " << HexUtilities::ToHex(_shapeTiles[id].PaletteColors) << std::endl;
					}
					dump << (col * 8 + frame.FineX) << " " << (row * 8) << " " << id << std::endl;
				}
			}
		}
	}
}

void HdPackBuilder::WriteSheetFiles(const string& folder, const string& baseName, const MesenSheets::SheetImage& image, MesenSheets::SheetJsonDoc& doc, const MesenSheets::TileLookup& lookup)
{
	if(image.Width == 0 || image.Height == 0) {
		return;
	}
	doc.SheetFile = baseName + ".png";
	doc.ReferenceFile = _writeReferences ? baseName + ".orig.png" : "";

	//The .png ships at the pack scale (the canvas the artist paints on); the
	//F5.4d .orig.png twin stays 1:1, and the sidecar JSON keeps 1x logical
	//coordinates so mep_build.py can slice either one.
	MesenSheets::SheetImage scaled = MesenSheets::Upscale(image, _hdData.Scale);
	PNGHelper::WritePNG(FolderUtilities::CombinePath(folder, doc.SheetFile), scaled.Pixels.data(), scaled.Width, scaled.Height, 32);
	if(_writeReferences) {
		MesenSheets::SheetImage reference = image;
		PNGHelper::WritePNG(FolderUtilities::CombinePath(folder, doc.ReferenceFile), reference.Pixels.data(), reference.Width, reference.Height, 32);
	}

	ofstream json(FolderUtilities::CombinePath(folder, baseName + ".json"), ios::out);
	json << MesenSheets::SerializeSheet(doc, lookup);
}

//F9.1-F9.3 (ADR-0153): the whole sheet inference, once, at save time.
void HdPackBuilder::BuildSheets()
{
	if(_sheetsBuilt || _gridFrames.empty()) {
		return;
	}
	_sheetsBuilt = true;

	const char* dumpPath = std::getenv("MESEN_SHEET_GRID_DUMP");
	if(dumpPath && *dumpPath) {
		WriteGridDump(dumpPath);
	}

	MesenSheets::TileLookup lookup = [this](MesenSheets::ShapeId id) -> const MesenSheets::SheetTileKey* {
		return id < _shapeTiles.size() ? &_shapeTiles[id] : nullptr;
	};

	MesenSheets::Vocabulary vocab = MesenSheets::BuildVocabulary(_gridFrames, lookup);
	if(vocab.Entries.empty()) {
		return;
	}

	string folder = FolderUtilities::CombinePath(_saveFolder, "sheets");
	FolderUtilities::CreateFolder(folder);

	WriteContextSheets(folder, vocab, lookup);
	WriteMapSheets(folder, vocab, lookup);
	WriteObjectSheets(folder, vocab, lookup);
	WriteSpriteSheets(folder, lookup);

	MessageManager::Log("[HD Pack Builder] sheets: grid unit " + std::to_string(vocab.Grid.Unit) +
		" (phase " + std::to_string(vocab.Grid.PhaseX) + "," + std::to_string(vocab.Grid.PhaseY) +
		", consistency " + std::to_string(vocab.Grid.ChosenConsistency) + " vs 8x8 " + std::to_string(vocab.Grid.Alt8x8) +
		"), " + std::to_string(vocab.Entries.size()) + " metatiles from " + std::to_string(vocab.DistinctScreens) +
		" distinct screens, HUD rows " + std::to_string(vocab.HudRows) + "/" + std::to_string(vocab.HudBottomRows) +
		", " + std::to_string(_spriteSheetCount) + " sprite groups from " + std::to_string(_oamFrames.size()) + " OAM frames" +
		", " + std::to_string(_screenResidentCells) + " cells routed to the captured screens");
}

//metatiles / hud / font / misc, split by context so a rupee counter never
//sits between two trees (ADR-0153 §3).
void HdPackBuilder::WriteContextSheets(const string& folder, const MesenSheets::Vocabulary& vocab, const MesenSheets::TileLookup& lookup)
{
	static const std::pair<MesenSheets::SheetContext, const char*> kSheets[] = {
		{ MesenSheets::SheetContext::Scene, "metatiles" },
		{ MesenSheets::SheetContext::Hud, "hud" },
		{ MesenSheets::SheetContext::Font, "font" },
		{ MesenSheets::SheetContext::Misc, "misc" },
	};

	_screenResidentCells = 0;
	for(const auto& sheet : kSheets) {
		vector<uint32_t> indexes;
		for(uint32_t i = 0; i < vocab.Entries.size(); i++) {
			if(vocab.Entries[i].Context != sheet.first) {
				continue;
			}
			//F9.9 (ADR-0156): a cell the captured screens already account for
			//everywhere it was ever seen is not spent a second time as a loose
			//fragment. It stays in the vocabulary - maps, objects and sprites
			//address entries by index - and the artist meets it whole, on
			//backgrounds/screenNNN.png, which is the only positional surface
			//the format has.
			if(vocab.Entries[i].ScreenResident) {
				_screenResidentCells++;
				continue;
			}
			indexes.push_back(i);
		}
		if(indexes.empty()) {
			continue;
		}
		//One subject, one cell (ADR-0153 §3, F9.7): entries that render to the
		//same pixels are the same drawing under a bank-swapped key, and paying
		//for them twice is what made half of some sheets redundant.
		vector<vector<uint32_t>> aliases;
		indexes = MesenSheets::CollapseAliases(vocab, indexes, lookup, _palette, MesenSheets::kSheetAliasTolerance, aliases);
		if(indexes.empty()) {
			continue;
		}
		//Cell order is the vocabulary's own (count descending, ADR-0153 §3), so
		//an artist reading the sheet cold meets the blocks the game is actually
		//built out of before the one-off title-screen art.
		uint32_t columns = MesenSheets::PreferredColumns(indexes.size());
		MesenSheets::SheetJsonDoc doc;
		MesenSheets::SheetImage image = MesenSheets::BuildContactSheet(vocab, indexes, lookup, _palette, columns, doc.Cells);
		for(size_t i = 0; i < doc.Cells.size() && i < aliases.size(); i++) {
			doc.Cells[i].Aliases = aliases[i];
			for(uint32_t alias : aliases[i]) {
				doc.Cells[i].AliasKeys.push_back(vocab.Entries[alias].Key);
			}
		}
		doc.Kind = sheet.second;
		doc.Grid = vocab.Grid;
		doc.CellWidth = doc.CellHeight = vocab.Grid.Unit;
		doc.Columns = columns;
		WriteSheetFiles(folder, sheet.second, image, doc, lookup);
	}
}

//Stitched maps: paint surfaces, never a runtime layer (ADR-0153 §6).
void HdPackBuilder::WriteMapSheets(const string& folder, const MesenSheets::Vocabulary& vocab, const MesenSheets::TileLookup& lookup)
{
	uint32_t distinct = 0;
	vector<const MesenSheets::GridFrame*> screens = MesenSheets::SelectStableScreens(_gridFrames, StableFramesNeeded, distinct);
	vector<MesenSheets::StitchedMap> maps = MesenSheets::BuildMaps(_gridFrames, screens, vocab);

	uint32_t index = 0;
	for(const MesenSheets::StitchedMap& map : maps) {
		if(map.Placements.empty()) {
			continue;
		}
		MesenSheets::SheetImage image = MesenSheets::RenderMap(map, vocab, lookup, _palette);
		char buf[32];
		snprintf(buf, sizeof(buf), "map-%03u", index++);
		MesenSheets::SheetJsonDoc doc;
		doc.Kind = "map";
		doc.Grid = vocab.Grid;
		doc.CellWidth = doc.CellHeight = vocab.Grid.Unit;
		doc.Gutter = 0;
		doc.Columns = map.Width / std::max(1u, vocab.Grid.Unit);
		doc.IsMap = true;
		doc.Mode = map.Mode;
		doc.HudRows = map.HudRows;
		doc.Placements = map.Placements;
		WriteSheetFiles(folder, buf, image, doc, lookup);
		for(const string& line : map.Log) {
			MessageManager::Log("[HD Pack Builder] " + string(buf) + ": " + line);
		}
	}
}

//Objects: mutual predictability, not raw counts (ADR-0153 §2).
void HdPackBuilder::WriteObjectSheets(const string& folder, const MesenSheets::Vocabulary& vocab, const MesenSheets::TileLookup& lookup)
{
	vector<MesenSheets::SheetGroup> groups = MesenSheets::BuildObjects(vocab);
	uint32_t index = 0;
	for(const MesenSheets::SheetGroup& group : groups) {
		MesenSheets::SheetJsonDoc doc;
		MesenSheets::SheetImage image = MesenSheets::RenderGroup(group, vocab, lookup, _palette, doc.Cells);
		if(image.Width == 0) {
			continue;
		}
		char buf[32];
		snprintf(buf, sizeof(buf), "obj%03u", index++);
		doc.Kind = "object";
		doc.Grid = vocab.Grid;
		doc.CellWidth = doc.CellHeight = vocab.Grid.Unit;
		doc.Columns = group.Columns;
		doc.Edges = group.Edges;
		WriteSheetFiles(folder, buf, image, doc, lookup);

		//The shapes an object is made of are the only ones that still earn an
		//inert "# inferred" tileNearby candidate (see BuildObjectSheets).
		for(const MesenSheets::SheetCell& cell : doc.Cells) {
			for(MesenSheets::ShapeId shape : cell.Key.Tiles) {
				if(shape != MesenSheets::kEmptyCell && shape < _shapeHashes.size()) {
					_sheetObjectShapes.insert(_shapeHashes[shape]);
				}
			}
		}
	}
	_sheetObjectCount = index;
}

//Sprites: the same mutual-predictability test over OAM offsets (ADR-0153 §2,
//F9.5). Its vocabulary is its own - one 8x8 OAM shape per cell at grid unit 8 -
//so a sprite cell never competes with a background metatile for an index.
void HdPackBuilder::WriteSpriteSheets(const string& folder, const MesenSheets::TileLookup& lookup)
{
	_spriteSheetCount = 0;
	if(_oamFrames.empty()) {
		return;
	}
	MesenSheets::Vocabulary vocab = MesenSheets::BuildSpriteVocabulary(_oamFrames);
	vector<MesenSheets::SheetGroup> groups = MesenSheets::BuildSprites(_oamFrames, vocab);
	for(const MesenSheets::SheetGroup& group : groups) {
		MesenSheets::SheetJsonDoc doc;
		//OAM colour 0 is the backdrop, so a sprite cell is drawn with it punched
		//out - the figure ships on transparency, per ADR-0153 §3.
		MesenSheets::SheetImage image = MesenSheets::RenderGroup(group, vocab, lookup, _palette, doc.Cells, true);
		if(image.Width == 0) {
			continue;
		}
		char buf[32];
		snprintf(buf, sizeof(buf), "spr%03u", _spriteSheetCount++);
		doc.Kind = "sprite";
		doc.Grid = vocab.Grid;
		doc.CellWidth = doc.CellHeight = vocab.Grid.Unit;
		doc.Columns = group.Columns;
		doc.Edges = group.Edges;
		WriteSheetFiles(folder, buf, image, doc, lookup);
	}
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

	//F9.1-F9.3 (ADR-0153): metatile vocabulary, stitched maps and objects, all
	//written under textures/sheets/ - the artist surface this pack is edited from.
	BuildSheets();

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