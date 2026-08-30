#include "pch.h"
#include <sstream>
#include "Shared/HdPacks/HdTilePack.h"
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "Shared/MessageManager.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/PNGHelper.h"
#include "Utilities/HexUtilities.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/VirtualFile.h"

static bool ParseHexBlob(const string& text, uint8_t* out, uint32_t maxSize, uint8_t& outSize)
{
	if(text.size() % 2 != 0 || text.size() / 2 > maxSize) {
		return false;
	}
	for(size_t i = 0; i < text.size(); i += 2) {
		int value = HexUtilities::FromHex(text.substr(i, 2));
		if(value < 0) {
			return false;
		}
		out[i / 2] = (uint8_t)value;
	}
	outSize = (uint8_t)(text.size() / 2);
	return true;
}

bool HdTilePack::Load(VirtualFile& romFile, string system, HdTilePack& outPack)
{
	string romName = FolderUtilities::GetFilename(romFile.GetFileName(), false);
	string definitionPath = FolderUtilities::CombinePath(FolderUtilities::CombinePath(FolderUtilities::GetHdPackFolder(), romName), "hires.txt");
	if(!ifstream(definitionPath)) {
		return false;
	}

	if(!outPack.LoadFile(definitionPath)) {
		return false;
	}

	if(outPack._system != system) {
		MessageManager::Log("[HDPack] hires.txt <system> is '" + outPack._system + "' but the current mode needs '" + system + "' - pack not loaded");
		return false;
	}

	MessageManager::Log("[HDPack] Loaded " + system + " pack: " + std::to_string(outPack._tiles.size()) + " tiles (scale " + std::to_string(outPack._scale) + ")");
	return true;
}

bool HdTilePack::LoadForRom(VirtualFile& romFile, string system, MepPackManager* mepManager, HdTilePack& outPack)
{
	string romName = FolderUtilities::GetFilename(romFile.GetFileName(), false);
	string loosePath = FolderUtilities::CombinePath(FolderUtilities::CombinePath(FolderUtilities::GetHdPackFolder(), romName), "hires.txt");
	string mepFolder = mepManager ? mepManager->GetSectionPath(MepSectionType::Textures) : "";
	string autoFolder = mepManager ? mepManager->GetSectionAutoPath(MepSectionType::Textures) : "";
	//An auto-only sibling (the F5 bootstrap's generic output, written before
	//any pack was installed) is only a base layer: it must not shadow a real
	//loose pack installed later (issue #142). The loose pack is skipped only
	//for human-authored sibling textures (ADR-0049).
	bool fromSibling = mepManager && mepManager->IsSectionFromSibling(MepSectionType::Textures) && !mepFolder.empty();

	if(ifstream(loosePath)) {
		if(fromSibling) {
			MessageManager::Log("[MEP] sibling folder beside the ROM overrides the loose HdPacks/" + romName + "/ pack");
		} else {
			if(!mepFolder.empty() || !autoFolder.empty()) {
				MessageManager::Log("[MEP] loose HD pack found in HdPacks/" + romName + "/ - it takes precedence over the pack's textures section");
			}
			return Load(romFile, system, outPack);
		}
	}

	if(mepFolder.empty() && autoFolder.empty()) {
		return false;
	}

	auto loadLayer = [&](const string& folder, HdTilePack& pack, const char* label) {
		if(!LoadFromFolder(folder, pack, false)) {
			MessageManager::Log(string("[MEP] ") + label + " has no loadable hires.txt in " + folder);
			return false;
		}
		if(pack._system != system) {
			MessageManager::Log(string("[MEP] ") + label + " hires.txt <system> is '" + pack._system + "' but the current mode needs '" + system + "' - not applied");
			return false;
		}
		return true;
	};

	bool loaded = !mepFolder.empty() && loadLayer(mepFolder, outPack, "textures section");
	if(!loaded) {
		outPack = HdTilePack();
	}
	if(!autoFolder.empty()) {
		HdTilePack autoPack;
		if(loadLayer(autoFolder, autoPack, "textures auto layer")) {
			if(outPack.MergeLowerLayer(autoPack)) {
				loaded = true;
			}
		}
	}
	if(!loaded) {
		return false;
	}
	MessageManager::Log("[MEP] textures: loaded " + system + " pack from '" + (mepFolder.empty() ? autoFolder : mepFolder) + "': " + std::to_string(outPack._tiles.size()) + " tiles (scale " + std::to_string(outPack._scale) + ")");
	return true;
}

bool HdTilePack::MergeLowerLayer(HdTilePack& lower)
{
	if(_tiles.empty()) {
		std::swap(_scale, lower._scale);
		std::swap(_system, lower._system);
		std::swap(_rawPixels, lower._rawPixels);
		std::swap(_tiles, lower._tiles);
		std::swap(_tilesByKey, lower._tilesByKey);
		std::swap(_defaultTilesByKey, lower._defaultTilesByKey);
		return true;
	}
	if(lower._scale != _scale || lower._system != _system) {
		MessageManager::Log("[HDPack] auto layer <scale>/<system> differ from the human layer - auto layer ignored");
		return false;
	}

	uint32_t added = 0;
	uint32_t skipped = 0;
	for(auto& tile : lower._tiles) {
		if(tile->DefaultTile) {
			HdCapturedTile wildcard = tile->Key;
			wildcard.PalKeySize = 1;
			memset(wildcard.PalKey + 1, 0, HdCapturedTile::MaxPalKeySize - 1);
			if(_defaultTilesByKey.find(wildcard) != _defaultTilesByKey.end()) {
				skipped++;
				continue;
			}
			_defaultTilesByKey[wildcard] = tile.get();
		} else {
			if(_tilesByKey.find(tile->Key) != _tilesByKey.end()) {
				skipped++;
				continue;
			}
			_tilesByKey[tile->Key] = tile.get();
		}
		_tiles.push_back(std::move(tile));
		added++;
	}
	lower._tiles.clear();
	lower._tilesByKey.clear();
	lower._defaultTilesByKey.clear();
	MessageManager::Log("[HDPack] auto layer merged: " + std::to_string(added) + " tiles added, " + std::to_string(skipped) + " overridden by the human layer");
	return true;
}

bool HdTilePack::LoadFromFolder(string packFolder, HdTilePack& outPack, bool rawPixels)
{
	string definitionPath = FolderUtilities::CombinePath(packFolder, "hires.txt");
	if(!ifstream(definitionPath)) {
		return false;
	}
	outPack._rawPixels = rawPixels;
	return outPack.LoadFile(definitionPath);
}

bool HdTilePack::LoadFile(string definitionPath)
{
	ifstream file(definitionPath, ios::in | ios::binary);
	if(!file) {
		return false;
	}

	string packFolder = FolderUtilities::GetFolderName(definitionPath);
	vector<SheetData> sheets;
	bool versionOk = false;
	bool unknownTagLogged = false;

	string line;
	while(std::getline(file, line)) {
		if(!line.empty() && line.back() == '\r') {
			line.pop_back();
		}
		if(line.empty() || line[0] == '#') {
			continue;
		}

		//See the matching normalization in HdPackLoader::LoadPack (NES loader).
		std::replace(line.begin(), line.end(), '\\', '/');

		if(line.substr(0, 5) == "<ver>") {
			int version = atoi(line.substr(5).c_str());
			if(version < 200 || version >= 300) {
				MessageManager::Log("[HDPack] Unsupported <ver> for GB/SMS pack: " + line.substr(5));
				return false;
			}
			versionOk = true;
		} else if(!versionOk) {
			MessageManager::Log("[HDPack] hires.txt must start with <ver>");
			return false;
		} else if(line.substr(0, 8) == "<system>") {
			_system = line.substr(8);
		} else if(line.substr(0, 7) == "<scale>") {
			_scale = std::min(10, std::max(1, atoi(line.substr(7).c_str())));
		} else if(line.substr(0, 5) == "<img>") {
			string pngPath = FolderUtilities::CombinePath(packFolder, line.substr(5));
			ifstream pngFile(pngPath, ios::in | ios::binary);
			if(!pngFile) {
				MessageManager::Log("[HDPack] Missing PNG file: " + line.substr(5));
				return false;
			}
			vector<uint8_t> fileData((std::istreambuf_iterator<char>(pngFile)), std::istreambuf_iterator<char>());
			vector<uint32_t> pixelData;
			uint32_t width = 0, height = 0;
			if(!PNGHelper::ReadPNG(fileData, pixelData, width, height)) {
				MessageManager::Log("[HDPack] Invalid PNG file: " + line.substr(5));
				return false;
			}

			SheetData sheet;
			sheet.Pixels = std::move(pixelData);
			sheet.Width = width;
			//Sheet names follow "Tiles_<bankHex>_<page>.png" - the bank is
			//PNG grouping only (ADR-0036) but the re-record merge preserves it
			string pngName = line.substr(5);
			if(pngName.substr(0, 6) == "Tiles_") {
				size_t bankEnd = pngName.find('_', 6);
				if(bankEnd != string::npos) {
					sheet.BankId = (uint32_t)strtoul(pngName.substr(6, bankEnd - 6).c_str(), nullptr, 16);
				}
			}
			sheets.push_back(std::move(sheet));
		} else if(line.substr(0, 6) == "<tile>") {
			string tileLine = line.substr(6);
			if(!ParseTileLine(tileLine, sheets)) {
				MessageManager::Log("[HDPack] Invalid <tile> line ignored: " + line);
			}
		} else if(line.substr(0, 14) == "<supportedRom>") {
			//Informational (same as the NES loader - no hard enforcement)
		} else if(!unknownTagLogged) {
			//bgm/sfx/conditions/etc. are not implemented by the v1 loader
			MessageManager::Log("[HDPack] Tag not supported by the GB/SMS loader yet, ignored: " + line.substr(0, line.find(',')));
			unknownTagLogged = true;
		}
	}

	return versionOk && !_tiles.empty();
}

bool HdTilePack::ParseTileLine(string& line, vector<SheetData>& sheets)
{
	vector<string> tokens = StringUtilities::Split(line, ',');
	if(tokens.size() < 7) {
		return false;
	}

	uint32_t sheetIndex = (uint32_t)atoi(tokens[0].c_str());
	if(sheetIndex >= sheets.size()) {
		return false;
	}

	unique_ptr<HdLoadedTile> tile(new HdLoadedTile());
	if(!ParseHexBlob(tokens[1], tile->Key.Data, HdCapturedTile::MaxDataSize, tile->Key.DataSize)) {
		return false;
	}
	if(!ParseHexBlob(tokens[2], tile->Key.PalKey, HdCapturedTile::MaxPalKeySize, tile->Key.PalKeySize)) {
		return false;
	}

	uint32_t x = (uint32_t)atoi(tokens[3].c_str());
	uint32_t y = (uint32_t)atoi(tokens[4].c_str());
	tile->Brightness = (uint32_t)(atof(tokens[5].c_str()) * 255);
	tile->DefaultTile = tokens[6] == "Y";
	tile->Key.BankId = sheets[sheetIndex].BankId;

	vector<uint32_t>& pixels = sheets[sheetIndex].Pixels;
	uint32_t sheetWidth = sheets[sheetIndex].Width;
	uint32_t tileDimension = 8 * _scale;
	if(sheetWidth == 0 || x + tileDimension > sheetWidth || (uint64_t)(y + tileDimension) * sheetWidth > pixels.size()) {
		return false;
	}

	tile->HdData.resize((size_t)tileDimension * tileDimension);
	for(uint32_t row = 0; row < tileDimension; row++) {
		memcpy(tile->HdData.data() + (size_t)row * tileDimension, pixels.data() + (size_t)(y + row) * sheetWidth + x, tileDimension * sizeof(uint32_t));
	}

	if(!_rawPixels) {
		//Premultiply alpha (same convention as the NES pack loader)
		for(uint32_t& pixel : tile->HdData) {
			if(pixel < 0xFF000000) {
				uint8_t* output = (uint8_t*)&pixel;
				uint16_t alpha = output[3] + 1;
				output[0] = (uint8_t)((alpha * output[0]) >> 8);
				output[1] = (uint8_t)((alpha * output[1]) >> 8);
				output[2] = (uint8_t)((alpha * output[2]) >> 8);
			}
		}

		if(tile->Brightness != 255) {
			for(uint32_t& pixel : tile->HdData) {
				uint8_t* output = (uint8_t*)&pixel;
				output[0] = (uint8_t)std::min<uint32_t>(255, output[0] * tile->Brightness / 255);
				output[1] = (uint8_t)std::min<uint32_t>(255, output[1] * tile->Brightness / 255);
				output[2] = (uint8_t)std::min<uint32_t>(255, output[2] * tile->Brightness / 255);
			}
		}
	}

	if(tile->DefaultTile) {
		HdCapturedTile wildcard = tile->Key;
		wildcard.PalKeySize = 1;
		memset(wildcard.PalKey + 1, 0, HdCapturedTile::MaxPalKeySize - 1);
		_defaultTilesByKey[wildcard] = tile.get();
	} else {
		_tilesByKey[tile->Key] = tile.get();
	}
	_tiles.push_back(std::move(tile));
	return true;
}
