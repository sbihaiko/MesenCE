#include "pch.h"
#include <filesystem>
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "Shared/MessageManager.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Utilities/VirtualFile.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/StringUtilities.h"
#include "Utilities/ZipReader.h"
#include "Utilities/sha1.h"

namespace fs = std::filesystem;

namespace
{
	void Log(const string& message)
	{
		MessageManager::Log("[MEP] " + message);
	}

	bool HasExtension(const string& lowerExt, std::initializer_list<const char*> candidates)
	{
		for(const char* c : candidates) {
			if(lowerExt == c) {
				return true;
			}
		}
		return false;
	}
}

MepPackManager::MepPackManager(Emulator* emu)
{
	_emu = emu;
}

string MepPackManager::GetPacksFolder()
{
	string folder = FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), FolderName);
	FolderUtilities::CreateFolder(folder);
	return folder;
}

string MepPackManager::ComputeNoIntroSha1(VirtualFile& romFile)
{
	vector<uint8_t>& data = romFile.GetData();
	size_t offset = 0;
	size_t size = data.size();

	string ext = StringUtilities::ToLower(romFile.GetFileExtension());
	if(ext == ".nes") {
		//iNES: 16-byte header, optional 512-byte trainer (flags6 bit 2)
		if(size >= 16 && memcmp(data.data(), "NES\x1A", 4) == 0) {
			offset = 16;
			if(data[6] & 0x04) {
				offset += 512;
			}
		}
	} else if(HasExtension(ext, { ".sfc", ".smc", ".swc", ".fig", ".bs", ".st" })) {
		//SNES copier header
		if(size % 1024 == 512) {
			offset = 512;
		}
	}

	if(offset > size) {
		offset = size;
	}
	return SHA1::GetHash(data.data() + offset, size - offset);
}

void MepPackManager::Clear()
{
	_romSha1.clear();
	_romExtension.clear();
	_packs.clear();
	_rejected.clear();
}

void MepPackManager::LoadForRom(VirtualFile& romFile)
{
	Clear();
	if(!romFile.IsValid()) {
		return;
	}

	_romSha1 = ComputeNoIntroSha1(romFile);
	_romExtension = StringUtilities::ToLower(romFile.GetFileExtension());
	if(!_emu->GetSettings()->GetEnhancementPackConfig().EnableMepPacks) {
		Log("enhancement packs disabled in settings - folder not scanned");
		return;
	}
	ScanAndMatch();

	if(!_packs.empty()) {
		for(const MepPack& pack : _packs) {
			string sections;
			for(int i = 0; i < 3; i++) {
				if(pack.Sections[i].Present) {
					sections += (sections.empty() ? "" : ",") + string(MepPack::GetSectionName((MepSectionType)i));
				}
			}
			Log("pack '" + pack.Name + "' v" + pack.Version + " matches ROM sha1 " + _romSha1 + " (container '" + pack.ContainerName + "', sections: " + sections + (IsPackEnabled(pack.ContainerName) ? ")" : ") - disabled by user"));
		}
	}
}

bool MepPackManager::ReadTextFile(const string& path, string& out)
{
	ifstream file(path, std::ios::in | std::ios::binary);
	if(!file) {
		return false;
	}
	std::stringstream ss;
	ss << file.rdbuf();
	out = ss.str();
	return true;
}

bool MepPackManager::PrepareZip(const string& zipPath, const string& cacheRoot, string& outFolder, string& error)
{
	std::error_code ec;
	fs::path zip = fs::u8path(zipPath);
	uintmax_t zipSize = fs::file_size(zip, ec);
	if(ec) {
		error = "cannot stat zip";
		return false;
	}
	auto mtime = fs::last_write_time(zip, ec).time_since_epoch().count();
	string stamp = std::to_string(zipSize) + ":" + std::to_string((long long)mtime);

	string name = FolderUtilities::GetFilename(zipPath, false);
	outFolder = FolderUtilities::CombinePath(cacheRoot, name);
	string stampPath = FolderUtilities::CombinePath(outFolder, ".mep-source");

	string existing;
	if(ReadTextFile(stampPath, existing) && StringUtilities::Trim(existing) == stamp && fs::exists(fs::u8path(FolderUtilities::CombinePath(outFolder, "pack.json")), ec)) {
		//Cache is current
		return true;
	}

	//(Re)extract: wipe any stale cache first
	fs::remove_all(fs::u8path(outFolder), ec);

	vector<uint8_t> zipData;
	{
		ifstream in(zipPath, std::ios::in | std::ios::binary);
		if(!in) {
			error = "cannot open zip";
			return false;
		}
		std::stringstream ss;
		ss << in.rdbuf();
		string s = ss.str();
		zipData.assign(s.begin(), s.end());
	}

	ZipReader reader;
	if(!reader.LoadArchive(zipData)) {
		error = "not a valid zip archive";
		return false;
	}

	vector<string> entries = reader.GetFileList();
	if(entries.empty()) {
		error = "zip is empty";
		return false;
	}

	//Validate every entry before writing anything (zip-slip, spec §6)
	vector<std::pair<string, string>> plan; //entry name -> normalised relative path
	bool hasPackJson = false;
	for(const string& entry : entries) {
		string normalized;
		if(!MepPack::NormalizeRelativePath(entry, normalized)) {
			error = "zip entry escapes the pack root: '" + entry + "'";
			return false;
		}
		if(normalized.empty()) {
			continue;
		}
		if(normalized == "pack.json") {
			hasPackJson = true;
		}
		plan.emplace_back(entry, normalized);
	}
	if(!hasPackJson) {
		error = "zip has no pack.json at its root";
		return false;
	}

	FolderUtilities::CreateFolder(outFolder);
	for(const auto& item : plan) {
		bool isDir = !item.first.empty() && (item.first.back() == '/' || item.first.back() == '\\');
		string dest = FolderUtilities::CombinePath(outFolder, item.second);
		if(isDir) {
			fs::create_directories(fs::u8path(dest), ec);
			continue;
		}
		fs::create_directories(fs::u8path(dest).parent_path(), ec);

		vector<uint8_t> content;
		if(!reader.ExtractFile(item.first, content)) {
			error = "cannot extract '" + item.first + "'";
			fs::remove_all(fs::u8path(outFolder), ec);
			return false;
		}
		ofstream out(dest, std::ios::out | std::ios::binary);
		if(!out) {
			error = "cannot write '" + dest + "'";
			fs::remove_all(fs::u8path(outFolder), ec);
			return false;
		}
		out.write((const char*)content.data(), content.size());
	}

	ofstream stampFile(stampPath, std::ios::out | std::ios::binary);
	stampFile << stamp;
	return true;
}

bool MepPackManager::LoadContainer(const string& rootFolder, const string& containerName, bool fromZip, MepPack& outPack, string& error)
{
	string json;
	if(!ReadTextFile(FolderUtilities::CombinePath(rootFolder, "pack.json"), json)) {
		error = "no pack.json";
		return false;
	}
	if(!MepPack::Parse(json, outPack, error)) {
		return false;
	}
	outPack.ContainerName = containerName;
	outPack.RootFolder = rootFolder;
	outPack.FromZip = fromZip;
	return true;
}

void MepPackManager::ScanAndMatch()
{
	string packsFolder = GetPacksFolder();
	string cacheRoot = FolderUtilities::CombinePath(packsFolder, CacheFolderName);

	std::error_code ec;
	vector<std::pair<string, MepPack>> candidates; //lower-cased name -> pack
	for(fs::directory_iterator it(fs::u8path(packsFolder), ec), end; !ec && it != end; it.increment(ec)) {
		const fs::directory_entry& entry = *it;
		string name = entry.path().filename().u8string();
		if(name.empty() || name[0] == '.') {
			continue; //includes .cache
		}

		string rootFolder;
		bool fromZip = false;
		string error;
		if(entry.is_directory(ec)) {
			rootFolder = entry.path().u8string();
		} else if(entry.is_regular_file(ec) && StringUtilities::ToLower(FolderUtilities::GetExtension(name)) == ".zip") {
			fromZip = true;
			if(!PrepareZip(entry.path().u8string(), cacheRoot, rootFolder, error)) {
				_rejected.push_back(name + ": " + error);
				Log("rejected '" + name + "': " + error);
				continue;
			}
			name = FolderUtilities::GetFilename(name, false);
		} else {
			continue;
		}

		MepPack pack;
		if(!LoadContainer(rootFolder, name, fromZip, pack, error)) {
			if(error != "no pack.json" || fromZip) {
				_rejected.push_back(name + ": " + error);
				Log("rejected '" + name + "': " + error);
			}
			continue;
		}

		if(!pack.MatchesSha1(_romSha1)) {
			continue;
		}
		candidates.emplace_back(StringUtilities::ToLower(name), std::move(pack));
	}

	//Deterministic precedence: case-insensitive lexicographic container name
	//(ADR-0040); ties (same lower-cased name) fall back to the exact name
	std::sort(candidates.begin(), candidates.end(), [](const auto& a, const auto& b) {
		if(a.first != b.first) {
			return a.first < b.first;
		}
		return a.second.ContainerName < b.second.ContainerName;
	});

	for(auto& candidate : candidates) {
		_packs.push_back(std::move(candidate.second));
	}
}

void MepPackManager::SetPackEnabled(const string& containerName, bool enabled)
{
	string key = StringUtilities::ToLower(containerName);
	if(enabled) {
		_disabledContainers.erase(key);
	} else {
		_disabledContainers.insert(key);
	}
}

bool MepPackManager::IsPackEnabled(const string& containerName) const
{
	return _disabledContainers.find(StringUtilities::ToLower(containerName)) == _disabledContainers.end();
}

const MepPack* MepPackManager::GetPackForSection(MepSectionType type) const
{
	EnhancementPackConfig& cfg = _emu->GetSettings()->GetEnhancementPackConfig();
	bool sectionEnabled = cfg.EnableMepPacks && (type == MepSectionType::Textures ? cfg.EnableTextures : type == MepSectionType::Audio ? cfg.EnableAudio :
																																													 cfg.EnableSynth);
	if(!sectionEnabled) {
		return nullptr;
	}
	for(const MepPack& pack : _packs) {
		if(pack.HasSection(type) && IsPackEnabled(pack.ContainerName)) {
			return &pack;
		}
	}
	return nullptr;
}

string MepPackManager::GetPackListText() const
{
	string out;
	for(const MepPack& pack : _packs) {
		string sections;
		for(int i = 0; i < 3; i++) {
			if(pack.Sections[i].Present) {
				sections += (sections.empty() ? "" : ",") + string(MepPack::GetSectionName((MepSectionType)i));
			}
		}
		out += pack.ContainerName + "\t" + pack.Name + "\t" + pack.Version + "\t" + pack.Author + "\t" + pack.License + "\t" + sections + "\t" + (IsPackEnabled(pack.ContainerName) ? "1" : "0") + "\t" + (pack.FromZip ? "1" : "0") + "\n";
	}
	for(const string& rejected : _rejected) {
		out += "!" + rejected + "\n";
	}
	return out;
}

string MepPackManager::GetSectionPath(MepSectionType type) const
{
	const MepPack* pack = GetPackForSection(type);
	return pack ? pack->GetSectionPath(type) : "";
}
