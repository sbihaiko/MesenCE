#pragma once
#include "pch.h"
#include <fstream>

//File-level primitives shared by the enhancement-pack pipeline
//(MepPackManager, MepZipExtract, MepRecipeOps): one whole-file reader, and
//the decompression caps every archive path enforces.
namespace MepFileIo
{
	//Decompression caps. ADR-0006 (MEI trust model) and ADR-0040 (zip
	//handling) make the archive contents untrusted input and already reject
	//path escapes (zip-slip); these two bounds extend that same trust model to
	//the *size* axis, so a small zip that declares a multi-gigabyte entry (a
	//"zip bomb") is refused before a byte is inflated. Per entry: the declared
	//uncompressed size of any single entry; per archive: the sum of every
	//entry's declared uncompressed size.
	constexpr uint64_t kMaxEntryUncompressedBytes = 1024ull * 1024 * 1024; //1 GiB
	constexpr uint64_t kMaxTotalUncompressedBytes = 2048ull * 1024 * 1024; //2 GiB

	//True when `entrySize` (one entry) and `runningTotal` (the sum so far,
	//updated in place) stay within the caps; `error` names the offender
	//otherwise.
	inline bool CheckDecompressionCaps(const string& entryName, uint64_t entrySize, uint64_t& runningTotal, string& error)
	{
		if(entrySize > kMaxEntryUncompressedBytes) {
			error = "refusing to extract '" + entryName + "': declared uncompressed size " + std::to_string(entrySize) + " bytes exceeds the 1 GiB per-entry cap";
			return false;
		}
		runningTotal += entrySize;
		if(runningTotal > kMaxTotalUncompressedBytes) {
			error = "refusing to extract the archive: total declared uncompressed size exceeds the 2 GiB cap (at entry '" + entryName + "')";
			return false;
		}
		return true;
	}

	//Reads a whole file into `out` (seekg/tellg + one read, no stringstream
	//round trip). False when the file cannot be opened or read.
	inline bool ReadWholeFile(const string& path, vector<uint8_t>& out)
	{
		ifstream in(path, std::ios::in | std::ios::binary);
		if(!in) {
			return false;
		}
		in.seekg(0, std::ios::end);
		std::streampos size = in.tellg();
		if(size < 0) {
			return false;
		}
		in.seekg(0, std::ios::beg);
		out.resize((size_t)size);
		if(size > 0 && !in.read((char*)out.data(), size)) {
			out.clear();
			return false;
		}
		return true;
	}

	inline bool ReadWholeFile(const string& path, string& out)
	{
		vector<uint8_t> bytes;
		if(!ReadWholeFile(path, bytes)) {
			return false;
		}
		out.assign(bytes.begin(), bytes.end());
		return true;
	}
}
