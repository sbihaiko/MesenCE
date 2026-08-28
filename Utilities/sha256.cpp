/*
	sha256.cpp - self-contained SHA-256 (FIPS 180-4) implementation,
	no third-party dependency. See sha256.h for interface notes.
*/

#include "pch.h"
#include "sha256.h"
#include <sstream>
#include <iomanip>
#include <fstream>

static const size_t BLOCK_BYTES = 64;

/* SHA-256 round constants (first 32 bits of the fractional parts of the
   cube roots of the first 64 primes), per FIPS 180-4 §4.2.2 */
static const uint32_t kRoundConstants[64] = {
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
	0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
	0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
	0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
	0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
	0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
	0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
	0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
	0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

static void reset(uint32_t state[8], std::string &buffer, uint64_t &blocks)
{
	/* SHA-256 initial hash values (FIPS 180-4 §5.3.3) */
	state[0] = 0x6a09e667;
	state[1] = 0xbb67ae85;
	state[2] = 0x3c6ef372;
	state[3] = 0xa54ff53a;
	state[4] = 0x510e527f;
	state[5] = 0x9b05688c;
	state[6] = 0x1f83d9ab;
	state[7] = 0x5be0cd19;
	buffer = "";
	blocks = 0;
}

static uint32_t rotr(uint32_t value, uint32_t bits)
{
	return (value >> bits) | (value << (32 - bits));
}

static void loadSchedule(const std::string &block, uint32_t w[64])
{
	for(size_t i = 0; i < 16; i++) {
		w[i] = (uint32_t)(uint8_t)block[4 * i] << 24
			| (uint32_t)(uint8_t)block[4 * i + 1] << 16
			| (uint32_t)(uint8_t)block[4 * i + 2] << 8
			| (uint32_t)(uint8_t)block[4 * i + 3];
	}
	for(size_t i = 16; i < 64; i++) {
		uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
		uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
		w[i] = w[i - 16] + s0 + w[i - 7] + s1;
	}
}

static void compress(uint32_t state[8], const uint32_t w[64])
{
	uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
	uint32_t e = state[4], f = state[5], g = state[6], h = state[7];

	for(size_t i = 0; i < 64; i++) {
		uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
		uint32_t ch = (e & f) ^ (~e & g);
		uint32_t temp1 = h + s1 + ch + kRoundConstants[i] + w[i];
		uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
		uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
		uint32_t temp2 = s0 + maj;

		h = g; g = f; f = e; e = d + temp1;
		d = c; c = b; b = a; a = temp1 + temp2;
	}

	state[0] += a; state[1] += b; state[2] += c; state[3] += d;
	state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

static void transform(uint32_t state[8], const std::string &block, uint64_t &blocks)
{
	uint32_t w[64];
	loadSchedule(block, w);
	compress(state, w);
	blocks++;
}

SHA256::SHA256()
{
	reset(state, buffer, blocks);
}

void SHA256::update(const std::string &s)
{
	std::istringstream is(s);
	update(is);
}

void SHA256::update(std::istream &is)
{
	char sbuf[BLOCK_BYTES];

	while(true) {
		is.read(sbuf, BLOCK_BYTES - buffer.size());
		buffer.append(sbuf, (size_t)is.gcount());
		if(buffer.size() != BLOCK_BYTES) {
			return;
		}

		transform(state, buffer, blocks);
		buffer.clear();
	}
}

/*
 * Add padding (FIPS 180-4 §5.1.1) and return the lowercase hex digest.
 */
std::string SHA256::final()
{
	uint64_t totalBits = (blocks * BLOCK_BYTES + buffer.size()) * 8;
	size_t buffered = buffer.size();

	buffer += (char)0x80;
	while(buffer.size() < BLOCK_BYTES) {
		buffer += (char)0x00;
	}

	if(buffered + 1 > BLOCK_BYTES - 8) {
		transform(state, buffer, blocks);
		buffer.assign(BLOCK_BYTES, (char)0x00);
	}

	for(int i = 0; i < 8; i++) {
		buffer[BLOCK_BYTES - 8 + i] = (char)((totalBits >> (8 * (7 - i))) & 0xff);
	}
	transform(state, buffer, blocks);

	std::ostringstream result;
	for(size_t i = 0; i < 8; i++) {
		result << std::hex << std::setfill('0') << std::setw(8) << state[i];
	}

	/* Reset for next run */
	reset(state, buffer, blocks);

	return result.str();
}

std::string SHA256::GetHash(vector<uint8_t> &data)
{
	std::stringstream ss;
	ss.write((char*)data.data(), data.size());
	SHA256 checksum;
	checksum.update(ss);
	return checksum.final();
}

std::string SHA256::GetHash(uint8_t* data, size_t size)
{
	std::stringstream ss;
	ss.write((char*)data, size);
	SHA256 checksum;
	checksum.update(ss);
	return checksum.final();
}

std::string SHA256::GetHash(std::istream &stream)
{
	SHA256 checksum;
	checksum.update(stream);
	return checksum.final();
}

std::string SHA256::GetHash(const std::string &filename)
{
	std::ifstream stream(filename.c_str(), std::ios::binary);
	SHA256 checksum;
	checksum.update(stream);
	return checksum.final();
}
