#include "pch.h"
#include "Shared/EnhancementPacks/MepRecipeSource.h"
#include "Shared/EnhancementPacks/MepPack.h"
#include "Utilities/StringUtilities.h"
#include <algorithm>

MepRecipeSource::~MepRecipeSource()
{
	Close();
}

void MepRecipeSource::Close()
{
	if(_loaded) {
		mz_zip_reader_end(&_zip);
	}
	_loaded = false;
	_normalizedToOriginal.clear();
}

bool MepRecipeSource::LoadFile(const string& path, string& error)
{
	ifstream in(path, std::ios::in | std::ios::binary);
	if(!in) {
		error = "cannot open: " + path;
		return false;
	}
	std::ostringstream ss;
	ss << in.rdbuf();
	string content = ss.str();
	return LoadBytes(vector<uint8_t>(content.begin(), content.end()), error);
}

bool MepRecipeSource::LoadBytes(vector<uint8_t> bytes, string& error)
{
	Close();
	_bytes = std::move(bytes);
	memset(&_zip, 0, sizeof(mz_zip_archive));
	if(!mz_zip_reader_init_mem(&_zip, _bytes.data(), _bytes.size(), 0)) {
		error = "not a valid zip archive";
		return false;
	}
	_loaded = true;
	for(mz_uint i = 0, len = mz_zip_reader_get_num_files(&_zip); i < len; i++) {
		if(mz_zip_reader_is_file_a_directory(&_zip, i)) {
			continue;
		}
		mz_zip_archive_file_stat stat;
		if(!mz_zip_reader_file_stat(&_zip, i, &stat)) {
			continue;
		}
		string original = stat.m_filename;
		string normalized = original;
		std::replace(normalized.begin(), normalized.end(), '\\', '/');
		_normalizedToOriginal[normalized] = original;
	}
	return true;
}

bool MepRecipeSource::Exists(const string& rel) const
{
	return _normalizedToOriginal.count(_rootPrefix + rel) > 0;
}

bool MepRecipeSource::Read(const string& rel, vector<uint8_t>& out) const
{
	auto it = _normalizedToOriginal.find(_rootPrefix + rel);
	if(it == _normalizedToOriginal.end()) {
		return false;
	}
	size_t size = 0;
	void* data = mz_zip_reader_extract_file_to_heap(const_cast<mz_zip_archive*>(&_zip), it->second.c_str(), &size, 0);
	if(!data) {
		return false;
	}
	out.assign((uint8_t*)data, (uint8_t*)data + size);
	mz_free(data);
	return true;
}

vector<string> MepRecipeSource::ListRelative() const
{
	vector<string> result;
	for(const auto& entry : _normalizedToOriginal) {
		const string& name = entry.first;
		if(name.compare(0, _rootPrefix.size(), _rootPrefix) != 0) {
			continue;
		}
		string rel = name.substr(_rootPrefix.size());
		if(!rel.empty()) {
			result.push_back(rel);
		}
	}
	return result;
}

vector<string> MepRecipeSource::RawEntries() const
{
	vector<string> result;
	for(const auto& entry : _normalizedToOriginal) {
		result.push_back(entry.first);
	}
	return result;
}

namespace
{
	bool HasEntry(const vector<string>& entries, const char* name)
	{
		return std::find(entries.begin(), entries.end(), string(name)) != entries.end();
	}

	//MEP-recipe-v1 §7 root-hit probes (mep_lint.py's PROBES/AUDIO_ALT_PROBE, plus pack.json)
	bool HasRootHit(const vector<string>& entries)
	{
		static const char* kProbes[] = { "pack.json", "hires.txt", "textures/hires.txt",
			"audio/hires.txt", "synth/preset.cfg", "audio/fingerprints.json" };
		for(const char* probe : kProbes) {
			if(HasEntry(entries, probe)) {
				return true;
			}
		}
		return false;
	}

	//find_top_level_nested_zip (mep_lint.py): exactly one root-level (no '/') ".zip" entry
	string FindTopLevelNestedZip(const vector<string>& entries)
	{
		string candidate;
		int count = 0;
		for(const string& name : entries) {
			if(name.find('/') == string::npos && StringUtilities::EndsWith(StringUtilities::ToLower(name), ".zip")) {
				candidate = name;
				count++;
			}
		}
		return count == 1 ? candidate : "";
	}

	//Re-runs the root-hit + fallback checks (shared by the direct pass and
	//the post-nested-zip retry below)
	bool TryDiscover(MepRecipeSource& src, const vector<string>& entries, const string& romName, string& prefix)
	{
		if(HasRootHit(entries)) {
			prefix = "";
			return true;
		}
		string fallback = MepPack::FindFallbackSubfolder(entries, romName);
		if(!fallback.empty()) {
			prefix = fallback + "/";
			return true;
		}
		return false;
	}
}

string DiscoverPrimaryRoot(MepRecipeSource& src, const string& romName)
{
	string prefix;
	if(TryDiscover(src, src.RawEntries(), romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	string nested = FindTopLevelNestedZip(src.RawEntries());
	vector<uint8_t> bytes;
	string loadError;
	if(!nested.empty() && src.Read(nested, bytes) && src.LoadBytes(bytes, loadError)
		&& TryDiscover(src, src.RawEntries(), romName, prefix)) {
		src.SetRootPrefix(prefix);
		return prefix;
	}
	src.SetRootPrefix("");
	return "";
}
