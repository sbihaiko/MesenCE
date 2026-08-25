#include "pch.h"
#include <algorithm>
#include <map>
#include "Shared/HdPacks/HdTilePackBuilder.h"
#include "Shared/HdPacks/HdTilePack.h"
#include "Shared/Emulator.h"
#include "Shared/MessageManager.h"
#include "Utilities/xBRZ/xbrz.h"
#include "Utilities/HQX/hqx.h"
#include "Utilities/Scale2x/scalebit.h"
#include "Utilities/KreedSaiEagle/SaiEagle.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/PNGHelper.h"
#include "Utilities/HexUtilities.h"

HdTilePackBuilder::HdTilePackBuilder(Emulator* emu, string system, HdPackBuilderOptions options)
{
	_emu = emu;
	_system = system;
	_saveFolder = options.SaveFolder;
	_scale = std::max<uint32_t>(1, options.Scale);
	_filterType = options.FilterType;
	_sortByUsageFrequency = options.SortByUsageFrequency;
	_romSha1 = _emu->GetRomInfo().RomFile.GetSha1Hash();

	MergeExistingPack();
}

//Re-recording into a folder that already holds a pack keeps every existing
//tile - including hand-edited art, brightness and defaultTile flags - and
//only appends the newly captured ones (same behavior as the NES builder)
void HdTilePackBuilder::MergeExistingPack()
{
	HdTilePack existingPack;
	if(!HdTilePack::LoadFromFolder(_saveFolder, existingPack, true)) {
		return;
	}

	if(existingPack.GetSystem() != _system) {
		MessageManager::Log("[HDPack] Existing pack in the save folder is for '" + existingPack.GetSystem() + "' - it will be overwritten");
		return;
	}

	if(existingPack.GetScale() != _scale) {
		//The existing art wins: new captures are scaled to match it
		MessageManager::Log("[HDPack] Existing pack uses scale " + std::to_string(existingPack.GetScale()) + " - keeping it");
		_scale = existingPack.GetScale();
	}

	uint32_t index = 0;
	for(unique_ptr<HdLoadedTile>& tile : existingPack.GetTiles()) {
		TileEntry& entry = _tiles[tile->Key];
		if(entry.UsageCount != 0) {
			//Duplicate line in the existing hires.txt - first one wins
			continue;
		}
		entry.Key = tile->Key;
		entry.HdPixels = std::move(tile->HdData);
		entry.Brightness = tile->Brightness;
		entry.DefaultTile = tile->DefaultTile;
		//High usage seed preserves the existing order ahead of new captures
		entry.UsageCount = 0xFFFFFFFF - index;
		entry.Order = _nextOrder++;
		index++;
	}

	MessageManager::Log("[HDPack] Merging with existing pack: " + std::to_string(index) + " tiles kept");
}

HdTilePackBuilder::~HdTilePackBuilder()
{
	SaveHdPack();
}

void HdTilePackBuilder::ProcessTile(const HdCapturedTile& tile, const uint32_t* rgba)
{
	auto result = _tiles.find(tile);
	if(result == _tiles.end()) {
		TileEntry& entry = _tiles[tile];
		entry.Key = tile;
		entry.UsageCount = 1;
		entry.Order = _nextOrder++;
		memcpy(entry.Rgba, rgba, sizeof(entry.Rgba));
	} else if(result->second.UsageCount < 0x7FFFFFFF) {
		result->second.UsageCount++;
	}
}

uint32_t HdTilePackBuilder::AddRomTiles(const vector<uint8_t>& rom)
{
	bool fourBpp = _system == "sms" || _system == "gg";
	uint32_t tileSize = fourBpp ? 32 : 16;
	uint32_t levels = fourBpp ? 16 : 4;

	uint32_t added = 0;
	for(size_t offset = 0; offset + tileSize <= rom.size(); offset += tileSize) {
		const uint8_t* data = rom.data() + offset;

		//Decode pixel indexes + flatness test
		uint8_t pixels[64];
		bool flat = true;
		for(int row = 0; row < 8; row++) {
			for(int x = 0; x < 8; x++) {
				uint8_t value = 0;
				if(fourBpp) {
					for(int plane = 0; plane < 4; plane++) {
						value |= ((data[row * 4 + plane] >> (7 - x)) & 0x01) << plane;
					}
				} else {
					value = ((data[row * 2] >> (7 - x)) & 0x01) | (((data[row * 2 + 1] >> (7 - x)) & 0x01) << 1);
				}
				pixels[row * 8 + x] = value;
				if(value != pixels[0]) {
					flat = false;
				}
			}
		}
		if(flat) {
			continue;
		}

		//Neutral gray ramp: index 0 = white .. max = black (GB convention)
		uint32_t rgba[64];
		for(int i = 0; i < 64; i++) {
			uint8_t gray = (uint8_t)(255 - (pixels[i] * 255) / (levels - 1));
			rgba[i] = 0xFF000000 | (gray << 16) | (gray << 8) | gray;
		}

		for(uint8_t type = 0; type < 2; type++) {
			HdCapturedTile key = {};
			memcpy(key.Data, data, tileSize);
			key.DataSize = (uint8_t)tileSize;
			key.PalKeySize = 1; //defaultTile wildcard key: type only (see HdTilePack::GetTile)
			key.PalKey[0] = type;
			key.BankId = (uint32_t)(offset / 0x4000);

			if(_tiles.find(key) != _tiles.end()) {
				continue;
			}
			TileEntry& entry = _tiles[key];
			entry.Key = key;
			entry.UsageCount = 0;
			entry.Order = _nextOrder++;
			entry.DefaultTile = true;
			memcpy(entry.Rgba, rgba, sizeof(entry.Rgba));
			added++;
		}
	}
	return added;
}

vector<uint32_t> HdTilePackBuilder::ScaleTile(const uint32_t* rgba)
{
	vector<uint32_t> originalTile(rgba, rgba + 64);
	vector<uint32_t> hdTile(8 * 8 * _scale * _scale, 0);

	if(_scale == 1) {
		return originalTile;
	}

	switch(_filterType) {
		case ScaleFilterType::HQX:
			hqx(_scale, originalTile.data(), hdTile.data(), 8, 8);
			break;

		case ScaleFilterType::Scale2x:
			scale(_scale, hdTile.data(), 8 * sizeof(uint32_t) * _scale, originalTile.data(), 8 * sizeof(uint32_t), 4, 8, 8);
			break;

		case ScaleFilterType::_2xSai:
			twoxsai_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * _scale);
			break;

		case ScaleFilterType::Super2xSai:
			supertwoxsai_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * _scale);
			break;

		case ScaleFilterType::SuperEagle:
			supereagle_generic_xrgb8888(8, 8, originalTile.data(), 8, hdTile.data(), 8 * _scale);
			break;

		case ScaleFilterType::xBRZ:
			xbrz::scale(_scale, originalTile.data(), hdTile.data(), 8, 8, xbrz::ColorFormat::ARGB);
			break;

		default:
		case ScaleFilterType::Prescale:
			for(uint32_t i = 0; i < 8 * _scale; i++) {
				for(uint32_t j = 0; j < 8 * _scale; j++) {
					hdTile[i * 8 * _scale + j] = originalTile[i / _scale * 8 + j / _scale];
				}
			}
			break;
	}

	return hdTile;
}

string HdTilePackBuilder::GetTileDataText(const HdCapturedTile& key)
{
	stringstream out;
	for(uint32_t i = 0; i < key.DataSize; i++) {
		out << HexUtilities::ToHex(key.Data[i]);
	}
	return out.str();
}

string HdTilePackBuilder::GetPaletteKeyText(const HdCapturedTile& key)
{
	stringstream out;
	for(uint32_t i = 0; i < key.PalKeySize; i++) {
		out << HexUtilities::ToHex(key.PalKey[i]);
	}
	return out.str();
}

void HdTilePackBuilder::SaveHdPack()
{
	if(_saved) {
		return;
	}
	_saved = true;

	FolderUtilities::CreateFolder(_saveFolder);

	//Group tiles by bank (PNG sheet organization only - see ADR-0036)
	std::map<uint32_t, vector<TileEntry*>> tilesByBank;
	for(auto& kvp : _tiles) {
		tilesByBank[kvp.second.Key.BankId].push_back(&kvp.second);
	}

	stringstream header;
	stringstream tileRows;
	header << "<ver>200" << std::endl;
	header << "<system>" << _system << std::endl;
	header << "<scale>" << _scale << std::endl;
	header << "<supportedRom>" << _romSha1 << std::endl;

	constexpr uint32_t tilesPerRow = 16;
	constexpr uint32_t tilesPerPng = tilesPerRow * tilesPerRow;
	uint32_t tileDimension = 8 * _scale;
	uint32_t pngDimension = tilesPerRow * tileDimension;
	vector<uint32_t> pngBuffer(pngDimension * pngDimension);

	int pngIndex = 0;
	for(auto& bankKvp : tilesByBank) {
		vector<TileEntry*>& tiles = bankKvp.second;
		if(_sortByUsageFrequency) {
			std::sort(tiles.begin(), tiles.end(), [](TileEntry* a, TileEntry* b) {
				return a->UsageCount != b->UsageCount ? a->UsageCount > b->UsageCount : a->Order < b->Order;
			});
		} else {
			std::sort(tiles.begin(), tiles.end(), [](TileEntry* a, TileEntry* b) { return a->Order < b->Order; });
		}

		uint32_t pageCount = ((uint32_t)tiles.size() + tilesPerPng - 1) / tilesPerPng;
		for(uint32_t page = 0; page < pageCount; page++) {
			std::fill(pngBuffer.begin(), pngBuffer.end(), 0xFFFF00FF);

			string pngName = "Tiles_" + HexUtilities::ToHex(bankKvp.first) + "_" + std::to_string(page) + ".png";
			header << "<img>" << pngName << std::endl;
			tileRows << std::endl
						<< "#" << pngName << std::endl;

			uint32_t tileCount = std::min<uint32_t>(tilesPerPng, (uint32_t)tiles.size() - page * tilesPerPng);
			for(uint32_t i = 0; i < tileCount; i++) {
				TileEntry* tile = tiles[page * tilesPerPng + i];
				uint32_t x = (i % tilesPerRow) * tileDimension;
				uint32_t y = (i / tilesPerRow) * tileDimension;

				//Tiles merged from an existing pack keep their (possibly
				//hand-edited) pixels verbatim; new captures are scaled here
				vector<uint32_t> hdTile = tile->HdPixels.size() == (size_t)tileDimension * tileDimension ? tile->HdPixels : ScaleTile(tile->Rgba);
				for(uint32_t row = 0; row < tileDimension; row++) {
					memcpy(pngBuffer.data() + (y + row) * pngDimension + x, hdTile.data() + row * tileDimension, tileDimension * sizeof(uint32_t));
				}

				tileRows << "<tile>" << pngIndex << ",";
				tileRows << GetTileDataText(tile->Key) << ",";
				tileRows << GetPaletteKeyText(tile->Key) << ",";
				tileRows << x << "," << y << ",";
				if(tile->Brightness == 255) {
					tileRows << "1";
				} else {
					tileRows << (tile->Brightness / 255.0);
				}
				tileRows << "," << (tile->DefaultTile ? "Y" : "N") << std::endl;
			}

			PNGHelper::WritePNG(FolderUtilities::CombinePath(_saveFolder, pngName), pngBuffer.data(), pngDimension, pngDimension, 32);
			pngIndex++;
		}
	}

	ofstream hiresFile(FolderUtilities::CombinePath(_saveFolder, "hires.txt"), ios::out);
	hiresFile << header.str();
	hiresFile << tileRows.str();
	hiresFile.close();
}
