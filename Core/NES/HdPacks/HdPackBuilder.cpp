#include "pch.h"
#include <algorithm>
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

void HdPackBuilder::ProcessTile(uint32_t x, uint32_t y, uint16_t tileAddr, HdPpuTileInfo& tile, BaseMapper* mapper, bool isSprite, uint32_t chrBankHash, bool transparencyRequired)
{
	if(_options.IgnoreOverscan) {
		OverscanDimensions overscan = _emu->GetSettings()->GetOverscan();
		if(x < overscan.Left || y < overscan.Top || (NesConstants::ScreenWidth - x - 1) < overscan.Right || (NesConstants::ScreenHeight - y - 1) < overscan.Bottom) {
			//Ignore tiles inside overscan
			return;
		}
	}

	auto result = _tileUsageCount.find(tile.GetKey(false));
	if(result == _tileUsageCount.end()) {
		//Check to see if a default tile matches
		result = _tileUsageCount.find(tile.GetKey(true));
	}

	if(result == _tileUsageCount.end()) {
		//First time seeing this tile/palette combination, store it
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
	} else {
		if(transparencyRequired) {
			auto existingTile = _tilesByKey.find(tile.GetKey(false));
			if(existingTile != _tilesByKey.end()) {
				existingTile->second->TransparencyRequired = true;
			}
		}

		if(result->second < 0x7FFFFFFF) {
			//Increase usage count
			result->second++;
		}
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
}

void HdPackBuilder::EnableScreenCapture()
{
	_captureScreens = true;
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