/*
	sha256.h - header of

	==============
	SHA-256 in C++
	==============

	Self-contained SHA-256 (FIPS 180-4) implementation. No third-party
	dependency (ADR-0038 precedent) — sibling to sha1.h/.cpp and mirrors
	its public interface (streaming update()/final() plus static
	GetHash() helpers) so callers can use either hash primitive the
	same way. `sha1.h` only implements SHA-1; this fills the SHA-256
	gap needed for MEP-recipe-v1 §8 artifact hash verification.

	Original implementation written for this project against the
	published FIPS 180-4 specification.
*/

#pragma once

#include <cstdint>
#include <iostream>
#include <string>

class SHA256
{
public:
	SHA256();
	void update(const std::string &s);
	void update(std::istream &is);
	std::string final();
	static std::string GetHash(const std::string &filename);
	static std::string GetHash(std::istream &stream);
	static std::string GetHash(vector<uint8_t> &data);
	static std::string GetHash(uint8_t* data, size_t size);

private:
	uint32_t state[8];
	std::string buffer;
	uint64_t blocks;
};
