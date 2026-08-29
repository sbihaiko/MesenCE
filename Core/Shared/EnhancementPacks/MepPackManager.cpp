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
#include "Utilities/JsonReader.h"
#include "Utilities/sha1.h"
#include "Shared/Interfaces/IConsole.h"
#include "Shared/Interfaces/INotificationListener.h"
#include "NES/NesConsole.h"

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

	//Zip mtime+size fingerprint (PrepareZip's cache-staleness check); "ec" is
	//set (and the result meaningless) when the zip cannot be stat'd
	string ComputeZipStamp(const fs::path& zip, std::error_code& ec)
	{
		uintmax_t zipSize = fs::file_size(zip, ec);
		if(ec) {
			return "";
		}
		auto mtime = fs::last_write_time(zip, ec).time_since_epoch().count();
		return std::to_string(zipSize) + ":" + std::to_string((long long)mtime);
	}

	bool ReadZipBytes(const string& zipPath, vector<uint8_t>& out)
	{
		ifstream in(zipPath, std::ios::in | std::ios::binary);
		if(!in) {
			return false;
		}
		std::stringstream ss;
		ss << in.rdbuf();
		string s = ss.str();
		out.assign(s.begin(), s.end());
		return true;
	}

	//Reads+opens the archive and lists its entries; "reader" stays loaded so
	//the caller can extract from it afterwards
	bool LoadZipEntries(const string& zipPath, ZipReader& reader, vector<string>& entries, string& error)
	{
		vector<uint8_t> zipData;
		if(!ReadZipBytes(zipPath, zipData)) {
			error = "cannot open zip";
			return false;
		}
		if(!reader.LoadArchive(zipData)) {
			error = "not a valid zip archive";
			return false;
		}
		entries = reader.GetFileList();
		if(entries.empty()) {
			error = "zip is empty";
			return false;
		}
		return true;
	}

	//Validates every entry before writing anything (zip-slip, spec §6);
	//false with a reason when an entry escapes the pack root
	bool BuildExtractionPlan(const vector<string>& entries, vector<std::pair<string, string>>& plan, bool& hasPackJson, string& error)
	{
		hasPackJson = false;
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
		return true;
	}

	bool ExtractPlan(ZipReader& reader, const vector<std::pair<string, string>>& plan, const string& outFolder, string& error)
	{
		std::error_code ec;
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
		return true;
	}

	//ADR-0120: last-priority fallback, consulted only when the pack.json-root
	//and zip-name-equals-ROM conventions (ADR-0040/ADR-0049) both fail; ""
	//(none, or ambiguous) keeps the caller's existing reject path
	string ResolveFallbackPrefix(const vector<std::pair<string, string>>& plan, const string& romName)
	{
		vector<string> normalizedEntries;
		normalizedEntries.reserve(plan.size());
		for(const auto& item : plan) {
			normalizedEntries.push_back(item.second);
		}
		return MepPack::FindFallbackSubfolder(normalizedEntries, romName);
	}

	//Combines the discovered fallback prefix into outFolder (ADR-0120, no
	//other output changes) and (re)writes the cache stamp
	void FinalizePreparedZip(const string& fallbackPrefix, const string& stampPath, const string& stamp, string& outFolder)
	{
		if(!fallbackPrefix.empty()) {
			string combined;
			MepPack::NormalizeRelativePath(fallbackPrefix, combined);
			outFolder = FolderUtilities::CombinePath(outFolder, combined);
		}
		ofstream stampFile(stampPath, std::ios::out | std::ios::binary);
		stampFile << stamp;
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
			//ADR-0044: hash only the PRG+CHR the header declares, so a dump
			//with trailing garbage still matches its clean No-Intro entry
			size_t prgUnits = data[4];
			size_t chrUnits = data[5];
			if((data[7] & 0x0C) == 0x08 && (data[9] & 0x0F) != 0x0F && (data[9] >> 4) != 0x0F) {
				//NES 2.0 size MSBs (exponent-multiplier form left alone)
				prgUnits |= (size_t)(data[9] & 0x0F) << 8;
				chrUnits |= (size_t)(data[9] >> 4) << 8;
			}
			size_t declared = offset + prgUnits * 0x4000 + chrUnits * 0x2000;
			if(declared > offset && declared < size) {
				size = declared;
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

string MepPackManager::GetSiblingFolder() const
{
	if(_romFolder.empty() || _romName.empty()) {
		return "";
	}
	return FolderUtilities::CombinePath(_romFolder, _romName);
}

void MepPackManager::StartBootstrapIfNeeded()
{
	_bootstrapping = false;
	EnhancementPackConfig& cfg = _emu->GetSettings()->GetEnhancementPackConfig();
	if(!cfg.EnableMepPacks || !cfg.BootstrapEnhancementFolder || _romName.empty()) {
		return;
	}

	shared_ptr<IConsole> console = _emu->GetConsole();
	if(!console) {
		return;
	}
	ConsoleType type = console->GetConsoleType();
	if(type != ConsoleType::Nes && type != ConsoleType::Gameboy && type != ConsoleType::Sms) {
		return; //no HD pack builder for this system
	}

	//Something already dresses this ROM: the bootstrap is only a first draft
	bool needTextures = !GetPackForSection(MepSectionType::Textures);
	std::error_code ec;
	if(fs::exists(fs::u8path(FolderUtilities::CombinePath(FolderUtilities::CombinePath(FolderUtilities::GetHdPackFolder(), _romName), "hires.txt")), ec)) {
		needTextures = false;
	}
	//Audio fingerprints (ADR-0047) are NES-only for now (ADR-0041 scope)
	bool needAudio = type == ConsoleType::Nes && !GetPackForSection(MepSectionType::Audio);
	if(!needTextures && !needAudio) {
		return;
	}

	//Sibling folder, or the central folder when the ROM's directory is read-only
	//Only the sections that will be generated get a folder (an empty auto/textures
	//next to an artist's pack would just confuse)
	string root = GetSiblingFolder();
	string autoRoot = FolderUtilities::CombinePath(root, MepPack::AutoFolderName);
	string autoTextures = FolderUtilities::CombinePath(autoRoot, MepPack::GetConventionPath(MepSectionType::Textures));
	fs::create_directories(fs::u8path(autoRoot), ec);
	if(ec || !fs::is_directory(fs::u8path(autoRoot), ec)) {
		root = FolderUtilities::CombinePath(GetPacksFolder(), _romName);
		autoRoot = FolderUtilities::CombinePath(root, MepPack::AutoFolderName);
		autoTextures = FolderUtilities::CombinePath(autoRoot, MepPack::GetConventionPath(MepSectionType::Textures));
		ec.clear();
		fs::create_directories(fs::u8path(autoRoot), ec);
		if(ec) {
			Log("bootstrap: cannot create '" + autoRoot + "' - skipped");
			return;
		}
		Log("bootstrap: ROM folder is not writable - using '" + root + "' instead (matched by name on the next load)");
	}

	//Stamp: generator version + ROM identity (never touches anything outside auto/)
	{
		ofstream stamp(FolderUtilities::CombinePath(root, ".bootstrap"), std::ios::out | std::ios::binary);
		stamp << "generator=mesence-bootstrap/1\nsha1=" << _romSha1 << "\nrom=" << _romName << "\nfilter=xBRZ\nscale=4\n";
	}

	if(needAudio) {
		string autoAudio = FolderUtilities::CombinePath(FolderUtilities::CombinePath(root, MepPack::AutoFolderName), MepPack::GetConventionPath(MepSectionType::Audio));
		fs::create_directories(fs::u8path(autoAudio), ec);
		if(NesConsole* nes = dynamic_cast<NesConsole*>(console.get())) {
			nes->StartAudioBootstrap(autoAudio);
			_bootstrapping = true;
			Log("bootstrap: recording music fingerprints + MIDI into '" + autoAudio + "'");
		}
	}
	if(!needTextures) {
		return;
	}

	fs::create_directories(fs::u8path(autoTextures), ec);
	if(ec) {
		Log("bootstrap: cannot create '" + autoTextures + "' - skipped");
		return;
	}
	_bootstrapSaveFolder = autoTextures;
	HdPackBuilderOptions options = {};
	options.SaveFolder = (char*)_bootstrapSaveFolder.c_str();
	options.FilterType = ScaleFilterType::xBRZ;
	options.Scale = 4;
	options.ChrRamBankSize = 0x1000;
	options.UseLargeSprites = false;
	options.SortByUsageFrequency = true;
	options.GroupBlankTiles = true;
	options.IgnoreOverscan = true;

	//Static pass first (ADR-0043; refused for CHR RAM games), then record what
	//is actually drawn while playing - the builder merges both in the folder
	ExecuteShortcutParams exportParams = { EmulatorShortcut::ExportRomTilesHdPack, 0, &options };
	console->ProcessNotification(ConsoleNotificationType::ExecuteShortcut, &exportParams);
	ExecuteShortcutParams recordParams = { EmulatorShortcut::StartRecordHdPack, 0, &options };
	console->ProcessNotification(ConsoleNotificationType::ExecuteShortcut, &recordParams);
	if(NesConsole* nes = dynamic_cast<NesConsole*>(console.get())) {
		//Static screens as whole-frame <background> PNGs with tileAtPosition anchors (F5.4)
		nes->EnableBootstrapScreenCapture();
	}
	_bootstrapping = true;
	Log("bootstrap: recording played tiles (xBRZ 4x) into '" + autoTextures + "' - the next load of this ROM plays with the auto layer");
}

void MepPackManager::Clear()
{
	_bootstrapping = false;
	_romSha1.clear();
	_romExtension.clear();
	_romName.clear();
	_romFolder.clear();
	_packs.clear();
	_rejected.clear();
	_packIdentityByContainer.clear();
}

string MepPackManager::GetSiblingFolder(VirtualFile& romFile)
{
	string romPath = romFile.GetFilePath();
	if(romPath.empty()) {
		return "";
	}
	string name = FolderUtilities::GetFilename(romPath, false);
	return FolderUtilities::CombinePath(FolderUtilities::GetFolderName(romPath), name);
}

string MepPackManager::SystemFromExtension(const string& lowerExt)
{
	if(lowerExt == ".nes" || lowerExt == ".fds" || lowerExt == ".unf" || lowerExt == ".unif" || lowerExt == ".nsf" || lowerExt == ".nsfe") {
		return "nes";
	} else if(lowerExt == ".gb") {
		return "gb";
	} else if(lowerExt == ".gbc" || lowerExt == ".gbx") {
		return "gbc";
	} else if(lowerExt == ".sms") {
		return "sms";
	} else if(lowerExt == ".gg") {
		return "gg";
	} else if(lowerExt == ".sg") {
		return "sg1000";
	} else if(lowerExt == ".sfc" || lowerExt == ".smc" || lowerExt == ".swc" || lowerExt == ".fig" || lowerExt == ".bs" || lowerExt == ".st") {
		return "snes";
	}
	return "";
}

bool MepPackManager::LoadConventionPack(const string& rootFolder, const string& containerName, MepPackOrigin origin, MepPack& outPack)
{
	outPack = MepPack();
	outPack.RootFolder = rootFolder;
	outPack.ContainerName = containerName;
	outPack.Origin = origin;
	outPack.FromZip = origin == MepPackOrigin::Zip;
	if(!outPack.DetectConventionLayout()) {
		return false;
	}
	outPack.Synthetic = true;
	outPack.SpecVersion = "1.1.0";
	outPack.Name = _romName;
	outPack.Version = "0.0.0";
	outPack.License = "unspecified";
	MepTarget target;
	target.System = SystemFromExtension(_romExtension);
	target.Sha1 = _romSha1;
	target.Name = _romName;
	outPack.Targets.push_back(target);
	return true;
}

void MepPackManager::ScanSiblingFolder()
{
	if(_romFolder.empty() || _romName.empty()) {
		return;
	}
	string sibling = FolderUtilities::CombinePath(_romFolder, _romName);
	std::error_code ec;
	if(!fs::is_directory(fs::u8path(sibling), ec)) {
		return;
	}

	MepPack pack;
	string error;
	string json;
	if(ReadTextFile(FolderUtilities::CombinePath(sibling, "pack.json"), json)) {
		//Explicit metadata beside the ROM: parsed for name/author/license/
		//patches, but location is identity - targets are not required to match
		if(!MepPack::Parse(json, pack, error)) {
			_rejected.push_back(_romName + "/ (sibling): " + error);
			Log("rejected sibling folder '" + sibling + "': " + error);
			return;
		}
		pack.RootFolder = sibling;
		pack.ContainerName = _romName;
		pack.Origin = MepPackOrigin::Sibling;
		//auto/ layers still come from the convention
		MepPack layout;
		layout.RootFolder = sibling;
		if(layout.DetectConventionLayout()) {
			for(int i = 0; i < 3; i++) {
				if(!layout.Sections[i].AutoPath.empty()) {
					pack.Sections[i].Present = true;
					pack.Sections[i].AutoPath = layout.Sections[i].AutoPath;
				}
			}
		}
	} else if(!LoadConventionPack(sibling, _romName, MepPackOrigin::Sibling, pack)) {
		Log("sibling folder '" + sibling + "' has no textures/, audio/ or synth/ layer - ignored");
		return;
	}
	_packs.push_back(std::move(pack));
}

void MepPackManager::LoadForRom(VirtualFile& romFile)
{
	Clear();
	if(!romFile.IsValid()) {
		return;
	}

	_romSha1 = ComputeNoIntroSha1(romFile);
	_romExtension = StringUtilities::ToLower(romFile.GetFileExtension());
	string romPath = romFile.GetFilePath();
	_romName = FolderUtilities::GetFilename(romPath, false);
	_romFolder = FolderUtilities::GetFolderName(romPath);
	if(!_emu->GetSettings()->GetEnhancementPackConfig().EnableMepPacks) {
		Log("enhancement packs disabled in settings - folder not scanned");
		return;
	}
	//ADR-0049: the folder beside the ROM always comes first
	ScanSiblingFolder();
	ScanAndMatch();

	//P.3: fill each pack's identity (pack_id/content_id) from its
	//.mep-install.json stamp, for the preferred-pack lookup below and the
	//pack-list columns the UI resolver reads
	for(MepPack& pack : _packs) {
		ReadInstallIdentity(pack);
	}

	if(!_packs.empty()) {
		for(const MepPack& pack : _packs) {
			string sections;
			for(int i = 0; i < 3; i++) {
				if(pack.Sections[i].Present) {
					sections += (sections.empty() ? "" : ",") + string(MepPack::GetSectionName((MepSectionType)i));
				}
			}
			string origin = pack.Origin == MepPackOrigin::Sibling ? "sibling folder" : pack.FromZip ? "zip" :
																																	"folder";
			Log("pack '" + pack.Name + "' v" + pack.Version + (pack.Synthetic ? " [folder convention]" : "") + " matches ROM sha1 " + _romSha1 + " (" + origin + " '" + pack.ContainerName + "', sections: " + sections + (IsPackEnabled(pack.ContainerName) ? ")" : ") - disabled by user"));
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

void MepPackManager::ReadInstallIdentity(MepPack& pack)
{
	//P.3: the .mep-install.json a MEP Recipe install writes at the container
	//root (MepRecipeInstaller::WriteInstallStamp) carries the ADR-0140 pack_id
	//and ADR-0139 content_id. Missing/malformed stamp -> an empty identity
	//(the UI derives `local:<container>` and never content-merges it, PRD §5).
	MepPackIdentity identity;
	string text;
	if(ReadTextFile(FolderUtilities::CombinePath(pack.RootFolder, ".mep-install.json"), text)) {
		JsonValue root;
		JsonReader reader;
		if(reader.Parse(text, root) && root.IsObject()) {
			identity.PackId = root.GetString("pack_id");
			identity.ContentId = root.GetString("content_id");
		}
	}
	_packIdentityByContainer[StringUtilities::ToLower(pack.ContainerName)] = std::move(identity);
}

string MepPackManager::EffectivePackId(const MepPack& pack) const
{
	//P.3: a stamped pack_id wins; a stamp-less container is the ADR-0140 rule-4
	//`local:<container>` fallback. Lower-cased so the preference comparison is
	//case-insensitive on both sides.
	auto it = _packIdentityByContainer.find(StringUtilities::ToLower(pack.ContainerName));
	if(it != _packIdentityByContainer.end() && !it->second.PackId.empty()) {
		return StringUtilities::ToLower(it->second.PackId);
	}
	return "local:" + StringUtilities::ToLower(pack.ContainerName);
}

bool MepPackManager::IsCacheCurrent(const string& outFolder, const string& stampPath, const string& stamp)
{
	std::error_code ec;
	string existing;
	return ReadTextFile(stampPath, existing) && StringUtilities::Trim(existing) == stamp && fs::exists(fs::u8path(FolderUtilities::CombinePath(outFolder, "pack.json")), ec);
}

bool MepPackManager::PrepareZip(const string& zipPath, const string& cacheRoot, string& outFolder, string& error)
{
	std::error_code ec;
	string stamp = ComputeZipStamp(fs::u8path(zipPath), ec);
	if(ec) {
		error = "cannot stat zip";
		return false;
	}

	string name = FolderUtilities::GetFilename(zipPath, false);
	outFolder = FolderUtilities::CombinePath(cacheRoot, name);
	string stampPath = FolderUtilities::CombinePath(outFolder, ".mep-source");
	if(IsCacheCurrent(outFolder, stampPath, stamp)) {
		return true;
	}

	fs::remove_all(fs::u8path(outFolder), ec); //(Re)extract: wipe any stale cache first
	return ExtractZip(zipPath, name, outFolder, stampPath, stamp, error);
}

bool MepPackManager::ExtractZip(const string& zipPath, const string& name, string& outFolder, const string& stampPath, const string& stamp, string& error)
{
	ZipReader reader;
	vector<string> entries;
	if(!LoadZipEntries(zipPath, reader, entries, error)) {
		return false;
	}

	vector<std::pair<string, string>> plan; //entry name -> normalised relative path
	bool hasPackJson = false;
	if(!BuildExtractionPlan(entries, plan, hasPackJson, error)) {
		return false;
	}
	string fallbackPrefix;
	if(!hasPackJson && StringUtilities::ToLower(name) != StringUtilities::ToLower(_romName)) {
		//ADR-0040/ADR-0049 both failed: last-priority fallback (ADR-0120)
		//before rejecting outright
		fallbackPrefix = ResolveFallbackPrefix(plan, _romName);
		if(fallbackPrefix.empty()) {
			error = "zip has no pack.json at its root";
			return false;
		}
	}

	if(!ExtractPlan(reader, plan, outFolder, error)) {
		return false;
	}
	FinalizePreparedZip(fallbackPrefix, stampPath, stamp, outFolder);
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
	outPack.Origin = fromZip ? MepPackOrigin::Zip : MepPackOrigin::Folder;
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
			if(error == "no pack.json") {
				//ADR-0049: a container named like the ROM is "the folder, zipped"
				//(or the fallback location when the ROM's folder is read-only).
				//ADR-0120: when PrepareZip resolved a fallback subfolder,
				//rootFolder's own last segment - not the zip's file name in
				//"name" - is the one guaranteed to match the ROM, so the gate
				//has to look there for the recovery to ever be reachable.
				string rootLeaf = FolderUtilities::GetFilename(rootFolder, true);
				if(StringUtilities::ToLower(rootLeaf) == StringUtilities::ToLower(_romName) && LoadConventionPack(rootFolder, name, fromZip ? MepPackOrigin::Zip : MepPackOrigin::Folder, pack)) {
					candidates.emplace_back(StringUtilities::ToLower(name), std::move(pack));
				} else if(fromZip) {
					_rejected.push_back(name + ": " + error);
					Log("rejected '" + name + "': " + error);
				}
			} else {
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

void MepPackManager::SetPreferredMepPack(const string& romSha1, const string& packId)
{
	//P.3: per-ROM preferred pack_id pushed by the UI at config-apply time.
	//An empty packId removes the entry; the key stays the ROM's No-Intro sha1
	//so GetPackForSection can look it up per loaded ROM. Stale keys (a pack
	//removed) are harmless: FindPreferredPack just finds no match.
	string sha1 = StringUtilities::Trim(romSha1);
	string id = StringUtilities::Trim(packId);
	if(sha1.empty()) {
		return;
	}
	if(id.empty()) {
		_preferredPackIdByRomSha1.erase(sha1);
	} else {
		_preferredPackIdByRomSha1[sha1] = StringUtilities::ToLower(id);
	}
}

void MepPackManager::ClearPreferredMepPacks()
{
	_preferredPackIdByRomSha1.clear();
}

const MepPack* MepPackManager::FindPreferredPack(MepSectionType type) const
{
	auto it = _preferredPackIdByRomSha1.find(_romSha1);
	if(it == _preferredPackIdByRomSha1.end() || it->second.empty()) {
		return nullptr;
	}
	for(const MepPack& pack : _packs) {
		if(pack.HasSection(type) && IsPackEnabled(pack.ContainerName) && EffectivePackId(pack) == it->second) {
			return &pack;
		}
	}
	return nullptr;
}

const MepPack* MepPackManager::GetPackForSection(MepSectionType type) const
{
	EnhancementPackConfig& cfg = _emu->GetSettings()->GetEnhancementPackConfig();
	bool sectionEnabled = cfg.EnableMepPacks && (type == MepSectionType::Textures ? cfg.EnableTextures : type == MepSectionType::Audio ? cfg.EnableAudio :
																																													 cfg.EnableSynth);
	if(!sectionEnabled) {
		return nullptr;
	}
	//P.3: the per-ROM preference overrides the ADR-0040 lexicographic order;
	//the default stays "first enabled pack in precedence order" when there is
	//no stored preference or the preferred pack_id does not match a candidate.
	if(const MepPack* preferred = FindPreferredPack(type)) {
		return preferred;
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
		MepPackIdentity identity;
		auto identityIt = _packIdentityByContainer.find(StringUtilities::ToLower(pack.ContainerName));
		if(identityIt != _packIdentityByContainer.end()) {
			identity = identityIt->second;
		}
		out += pack.ContainerName + "\t" + pack.Name + "\t" + pack.Version + "\t" + pack.Author + "\t" + pack.License + "\t" + sections + "\t" + (IsPackEnabled(pack.ContainerName) ? "1" : "0") + "\t" + std::to_string((int)pack.Origin) + "\t" + identity.PackId + "\t" + identity.ContentId + "\n";
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

string MepPackManager::GetSectionAutoPath(MepSectionType type) const
{
	const MepPack* pack = GetPackForSection(type);
	return pack ? pack->GetSectionAutoPath(type) : "";
}

vector<string> MepPackManager::GetSynthPresetPaths() const
{
	vector<string> paths;
	string autoPath = GetSectionAutoPath(MepSectionType::Synth);
	string humanPath = GetSectionPath(MepSectionType::Synth);
	if(!autoPath.empty()) {
		paths.push_back(autoPath);
	}
	if(!humanPath.empty()) {
		paths.push_back(humanPath);
	}
	return paths;
}

bool MepPackManager::IsSectionFromSibling(MepSectionType type) const
{
	const MepPack* pack = GetPackForSection(type);
	return pack && pack->Origin == MepPackOrigin::Sibling;
}

bool MepPackManager::ApplyPatches(VirtualFile& romFile)
{
	EnhancementPackConfig& cfg = _emu->GetSettings()->GetEnhancementPackConfig();
	if(!cfg.EnableMepPacks || !cfg.EnablePatches) {
		return false;
	}
	for(const MepPack& pack : _packs) {
		if(pack.Patches.empty() || !IsPackEnabled(pack.ContainerName)) {
			continue;
		}
		const MepPatch* patch = pack.FindPatch(_romSha1);
		if(!patch) {
			if(_emu->GetSettings()->GetEnhancementPackConfig().ApplyPatchOnHashMismatch) {
				patch = &pack.Patches[0];
				MessageManager::DisplayMessage("MEP", "Applying patch made for another ROM revision (hash override enabled)");
				Log("pack '" + pack.Name + "': no patch for sha1 " + _romSha1 + " - applying '" + patch->File + "' anyway (ApplyPatchOnHashMismatch)");
			} else {
				Log("pack '" + pack.Name + "': patch skipped - none of its " + std::to_string(pack.Patches.size()) + " patches[] entries matches sha1 " + _romSha1);
				continue;
			}
		}
		VirtualFile patchFile(FolderUtilities::CombinePath(pack.RootFolder, patch->File));
		if(!patchFile.IsValid()) {
			Log("pack '" + pack.Name + "': patch file not found: " + patch->File);
			continue;
		}
		if(romFile.ApplyPatch(patchFile)) {
			Log("pack '" + pack.Name + "': applied patch '" + patch->File + "'");
			return true;
		}
		Log("pack '" + pack.Name + "': failed to apply patch '" + patch->File + "'");
	}
	return false;
}
