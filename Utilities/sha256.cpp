/*
	sha256.cpp - self-contained SHA-256 (FIPS 180-4) implementation,
	no third-party dependency. See sha256.h for interface notes.
*/

#include "pch.h"
#include "sha256.h"
#include <sstream>
#include <iomanip>
#include <cstring>
#include <algorithm>

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

static void reset(uint32_t state[8], size_t &buffered, uint64_t &blocks)
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
	buffered = 0;
	blocks = 0;
}

static uint32_t rotr(uint32_t value, uint32_t bits)
{
	return (value >> bits) | (value << (32 - bits));
}

static void loadSchedule(const uint8_t *block, uint32_t w[64])
{
	for(size_t i = 0; i < 16; i++) {
		w[i] = (uint32_t)block[4 * i] << 24
			| (uint32_t)block[4 * i + 1] << 16
			| (uint32_t)block[4 * i + 2] << 8
			| (uint32_t)block[4 * i + 3];
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

static void transform(uint32_t state[8], const uint8_t *block, uint64_t &blocks)
{
	uint32_t w[64];
	loadSchedule(block, w);
	compress(state, w);
	blocks++;
}

SHA256::SHA256()
{
	reset(state, buffered, blocks);
}

void SHA256::update(const uint8_t* data, size_t size)
{
	if(buffered > 0) {
		//Top up the pending tail first; only a complete block is transformed
		size_t take = std::min(size, BLOCK_BYTES - buffered);
		memcpy(buffer + buffered, data, take);
		buffered += take;
		data += take;
		size -= take;
		if(buffered < BLOCK_BYTES) {
			return;
		}
		transform(state, buffer, blocks);
		buffered = 0;
	}
	while(size >= BLOCK_BYTES) {
		transform(state, data, blocks);
		data += BLOCK_BYTES;
		size -= BLOCK_BYTES;
	}
	if(size > 0) {
		memcpy(buffer, data, size);
		buffered = size;
	}
}

void SHA256::update(std::istream &is)
{
	static const size_t kChunk = 64 * 1024;
	std::vector<uint8_t> chunk(kChunk);
	while(is) {
		is.read((char*)chunk.data(), (std::streamsize)kChunk);
		std::streamsize got = is.gcount();
		if(got <= 0) {
			break;
		}
		update(chunk.data(), (size_t)got);
	}
}

/*
 * Add padding (FIPS 180-4 §5.1.1) and return the lowercase hex digest.
 */
std::string SHA256::final()
{
	uint64_t totalBits = (blocks * BLOCK_BYTES + buffered) * 8;
	size_t used = buffered;

	buffer[used++] = 0x80;
	memset(buffer + used, 0, BLOCK_BYTES - used);

	if(used > BLOCK_BYTES - 8) {
		transform(state, buffer, blocks);
		memset(buffer, 0, BLOCK_BYTES);
	}

	for(int i = 0; i < 8; i++) {
		buffer[BLOCK_BYTES - 8 + i] = (uint8_t)((totalBits >> (8 * (7 - i))) & 0xff);
	}
	transform(state, buffer, blocks);

	std::ostringstream result;
	for(size_t i = 0; i < 8; i++) {
		result << std::hex << std::setfill('0') << std::setw(8) << state[i];
	}

	/* Reset for next run */
	reset(state, buffered, blocks);

	return result.str();
}

std::string SHA256::GetHash(const uint8_t* data, size_t size)
{
	SHA256 checksum;
	checksum.update(data, size);
	return checksum.final();
}

std::string SHA256::GetHash(const std::string &filename)
{
	ifstream stream(filename, std::ios::binary);
	if(!stream) {
		//Verification callers (MepRecipeInstaller, MEP-recipe-v1 §8) must never
		//see an unopenable file as "the empty-input digest": return an empty
		//string, which can equal no declared 64-hex value.
		return "";
	}
	SHA256 checksum;
	checksum.update(stream);
	return checksum.final();
}
