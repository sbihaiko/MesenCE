#pragma once
#include "pch.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/StringUtilities.h"
#include <filesystem>
#include <fstream>
#include <sstream>

//ADR-0120 §4: the zip half of MepPackManager::PrepareZip, extracted whole so
//it can be driven end-to-end from scripts/core_unit_tests.cpp against real
//archive bytes (zip-slip rejection, the .mep-source cache-reuse branch, the
//wrapped-subfolder fallback) without linking MepPackManager - which pulls in
//Emulator, NesConsole and ZipReader/ArchiveReader/SevenZip. The only thing
//abstracted away is how the archive itself is read: MepPackManager keeps
//using ZipReader, the test uses miniz directly (same seam MepRecipeOps.h
//already relies on).
namespace MepZipExtract
{
	//How the caller reads the archive. Load() opens it and lists its raw
	//entry names; ExtractFile() reads one of those entries.
	class IArchive
	{
	public:
		virtual ~IArchive() {}
		virtual bool Load(const string& zipPath, vector<string>& entries, string& error) = 0;
		virtual bool ExtractFile(const string& entry, vector<uint8_t>& content) = 0;
	};

	//Zip mtime+size fingerprint (the cache-staleness check); "ec" is set (and
	//the result meaningless) when the zip cannot be stat'd
	inline string ComputeZipStamp(const std::filesystem::path& zip, std::error_code& ec)
	{
		uintmax_t zipSize = std::filesystem::file_size(zip, ec);
		if(ec) {
			return "";
		}
		auto mtime = std::filesystem::last_write_time(zip, ec).time_since_epoch().count();
		return std::to_string(zipSize) + ":" + std::to_string((long long)mtime);
	}

	//A previous extraction of the very same zip bytes is still on disk
	inline bool IsCacheCurrent(const string& outFolder, const string& stampPath, const string& stamp)
	{
		std::error_code ec;
		ifstream in(stampPath, std::ios::in | std::ios::binary);
		if(!in) {
			return false;
		}
		std::stringstream ss;
		ss << in.rdbuf();
		return StringUtilities::Trim(ss.str()) == stamp
			&& std::filesystem::exists(std::filesystem::u8path(FolderUtilities::CombinePath(outFolder, "pack.json")), ec);
	}

	//Validates every entry before writing anything (zip-slip, spec §6);
	//false with a reason when an entry escapes the pack root
	inline bool BuildExtractionPlan(const vector<string>& entries, vector<std::pair<string, string>>& plan, bool& hasPackJson, string& error)
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

	inline bool ExtractPlan(IArchive& archive, const vector<std::pair<string, string>>& plan, const string& outFolder, string& error)
	{
		namespace fs = std::filesystem;
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
			if(!archive.ExtractFile(item.first, content)) {
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
	inline string ResolveFallbackPrefix(const vector<std::pair<string, string>>& plan, const string& romName)
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
	inline void FinalizePrepared(const string& fallbackPrefix, const string& stampPath, const string& stamp, string& outFolder)
	{
		if(!fallbackPrefix.empty()) {
			string combined;
			MepPack::NormalizeRelativePath(fallbackPrefix, combined);
			outFolder = FolderUtilities::CombinePath(outFolder, combined);
		}
		ofstream stampFile(stampPath, std::ios::out | std::ios::binary);
		stampFile << stamp;
	}

	//The whole ADR-0040/ADR-0049/ADR-0120 zip pipeline for one archive:
	//list -> validate (zip-slip) -> root convention or fallback subfolder ->
	//extract -> stamp. `containerName` is the zip's base file name (the
	//ADR-0049 "zip = the folder, zipped" comparison), `romName` the loaded
	//ROM's name.
	inline bool ExtractZip(IArchive& archive, const string& zipPath, const string& containerName, const string& romName,
		string& outFolder, const string& stampPath, const string& stamp, string& error)
	{
		vector<string> entries;
		if(!archive.Load(zipPath, entries, error)) {
			return false;
		}
		if(entries.empty()) {
			error = "zip is empty";
			return false;
		}

		vector<std::pair<string, string>> plan; //entry name -> normalised relative path
		bool hasPackJson = false;
		if(!BuildExtractionPlan(entries, plan, hasPackJson, error)) {
			return false;
		}
		string fallbackPrefix;
		if(!hasPackJson && StringUtilities::ToLower(containerName) != StringUtilities::ToLower(romName)) {
			//ADR-0040/ADR-0049 both failed: last-priority fallback (ADR-0120)
			//before rejecting outright
			fallbackPrefix = ResolveFallbackPrefix(plan, romName);
			if(fallbackPrefix.empty()) {
				error = "zip has no pack.json at its root";
				return false;
			}
		}

		if(!ExtractPlan(archive, plan, outFolder, error)) {
			return false;
		}
		FinalizePrepared(fallbackPrefix, stampPath, stamp, outFolder);
		return true;
	}

	//PrepareZip itself: the cache-stamp short circuit, the wipe of any stale
	//cache (which is also what keeps a leftover symlink in the cache folder
	//from being written through) and then ExtractZip.
	inline bool PrepareZip(IArchive& archive, const string& zipPath, const string& cacheRoot, const string& romName, string& outFolder, string& error)
	{
		namespace fs = std::filesystem;
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
		return ExtractZip(archive, zipPath, name, romName, outFolder, stampPath, stamp, error);
	}
}
