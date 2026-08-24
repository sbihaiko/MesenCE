#include "pch.h"
#include <sstream>
#include "Shared/HdPacks/HdTilePack.h"
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

bool HdTilePack::LoadFile(string definitionPath)
{
	ifstream file(definitionPath, ios::in | ios::binary);
	if(!file) {
		return false;
	}

	string packFolder = FolderUtilities::GetFolderName(definitionPath);
	vector<std::pair<vector<uint32_t>, uint32_t>> sheets;
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
			sheets.push_back({ std::move(pixelData), width });
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

bool HdTilePack::ParseTileLine(string& line, vector<std::pair<vector<uint32_t>, uint32_t>>& sheets)
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

	vector<uint32_t>& pixels = sheets[sheetIndex].first;
	uint32_t sheetWidth = sheets[sheetIndex].second;
	uint32_t tileDimension = 8 * _scale;
	if(sheetWidth == 0 || x + tileDimension > sheetWidth || (uint64_t)(y + tileDimension) * sheetWidth > pixels.size()) {
		return false;
	}

	tile->HdData.resize((size_t)tileDimension * tileDimension);
	for(uint32_t row = 0; row < tileDimension; row++) {
		memcpy(tile->HdData.data() + (size_t)row * tileDimension, pixels.data() + (size_t)(y + row) * sheetWidth + x, tileDimension * sizeof(uint32_t));
	}

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
