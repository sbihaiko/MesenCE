#include "pch.h"
#include "Utilities/LiveRecordFormat.h"
#include <cstdio>

bool LiveRecordFormat::AtomicWrite(const std::string& finalPath, const void* data, size_t size)
{
	std::string tmpPath = finalPath + ".tmp";
	FILE* f = fopen(tmpPath.c_str(), "wb");
	if(!f) {
		return false;
	}
	bool ok = fwrite(data, 1, size, f) == size;
	if(fclose(f) != 0) {
		ok = false;
	}
	if(!ok) {
		std::remove(tmpPath.c_str());
		return false;
	}
	return std::rename(tmpPath.c_str(), finalPath.c_str()) == 0;
}

bool LiveRecordFormat::AtomicWrite(const std::string& finalPath, const std::string& text)
{
	return AtomicWrite(finalPath, text.data(), text.size());
}

std::string LiveRecordFormat::ComposePpm(const LiveSnapshot& snapshot)
{
	std::string ppm = "P6\n" + std::to_string(snapshot.Width) + " " + std::to_string(snapshot.Height) + "\n255\n";
	ppm.reserve(ppm.size() + snapshot.Pixels.size() * 3);
	for(uint32_t px : snapshot.Pixels) {
		ppm += (char)((px >> 16) & 0xFF);
		ppm += (char)((px >> 8) & 0xFF);
		ppm += (char)(px & 0xFF);
	}
	return ppm;
}

std::string LiveRecordFormat::ComposeSpritesJson(const LiveSnapshot& s, uint32_t cpuFrame)
{
	std::string j = "{\n";
	j += "  \"frame\": " + std::to_string(cpuFrame) + ",\n";
	j += "  \"captureFrame\": " + std::to_string(s.CaptureFrame) + ",\n";
	j += "  \"patternAddr\": " + std::to_string(s.SpritePatternAddr) + ",\n";
	j += std::string("  \"largeSprites\": ") + (s.LargeSprites ? "true" : "false") + ",\n";
	j += std::string("  \"spritesEnabled\": ") + (s.SpritesEnabled ? "true" : "false") + ",\n";
	j += std::string("  \"leftColumnClip\": ") + (s.LeftColumnClip ? "true" : "false") + ",\n";
	j += "  \"palette\": [";
	for(int i = 0; i < 0x20; i++) {
		if(i) j += ",";
		j += std::to_string(s.Palette[i]);
	}
	j += "],\n  \"oam\": [";
	for(int i = 0; i < 64; i++) {
		if(i) j += ",";
		j += "[" + std::to_string(s.Oam[i * 4]) + "," + std::to_string(s.Oam[i * 4 + 1]) + "," + std::to_string(s.Oam[i * 4 + 2]) + "," + std::to_string(s.Oam[i * 4 + 3]) + "]";
	}
	j += "]\n}\n";
	return j;
}

std::string LiveRecordFormat::ComposeBackgroundJson(const LiveSnapshot& s)
{
	std::string j = "{\n";
	j += "  \"patternAddr\": " + std::to_string(s.BackgroundPatternAddr) + ",\n";
	j += std::string("  \"enabled\": ") + (s.BackgroundEnabled ? "true" : "false") + ",\n";
	j += std::string("  \"leftColumnClip\": ") + (s.BackgroundLeftColumnClip ? "true" : "false") + ",\n";
	j += "  \"tmpScroll\": " + std::to_string(s.TmpVideoRamAddr) + ",\n";
	j += "  \"fineScrollX\": " + std::to_string(s.FineScrollX) + "\n";
	j += "}\n";
	return j;
}

std::string LiveRecordFormat::ComposeChrLatchJson(const LiveSnapshot& s)
{
	if(!s.HasChrLatch) {
		return "";
	}
	std::string j = "{\n";
	j += "  \"pageSize\": " + std::to_string(s.ChrLatchPageSize) + ",\n";
	j += "  \"leftFdBank\": " + std::to_string(s.LeftChrFdBank) + ",\n";
	j += "  \"leftFeBank\": " + std::to_string(s.LeftChrFeBank) + ",\n";
	j += "  \"rightFdBank\": " + std::to_string(s.RightChrFdBank) + ",\n";
	j += "  \"rightFeBank\": " + std::to_string(s.RightChrFeBank) + "\n";
	j += "}\n";
	return j;
}

std::string LiveRecordFormat::ComposeJsonString(const std::string& text)
{
	//Only what JSON requires: the two escapes, plus the control range as \uXXXX.
	//Anything else (UTF-8 bytes of an accented ROM name included) goes through
	//untouched - the file is written as UTF-8 and read as UTF-8.
	std::string out = "\"";
	for(char c : text) {
		unsigned char u = (unsigned char)c;
		if(c == '"' || c == '\\') {
			out += '\\';
			out += c;
		} else if(u < 0x20) {
			char esc[8];
			snprintf(esc, sizeof(esc), "\\u%04X", u);
			out += esc;
		} else {
			out += c;
		}
	}
	out += "\"";
	return out;
}

std::string LiveRecordFormat::ComposeStatusJson(bool done, uint32_t frame, uint32_t targetFrames, double wallSec, bool hdPackActive, const std::string& romName)
{
	char wall[32];
	snprintf(wall, sizeof(wall), "%.1f", wallSec);
	std::string s = "{\n";
	s += "  \"frame\": " + std::to_string(frame) + ",\n";
	s += "  \"targetFrames\": " + std::to_string(targetFrames) + ",\n";
	s += std::string("  \"elapsedWallSec\": ") + wall + ",\n";
	s += std::string("  \"hdPackActive\": ") + (hdPackActive ? "true" : "false") + ",\n";
	s += "  \"rom\": " + ComposeJsonString(romName) + ",\n";
	s += std::string("  \"done\": ") + (done ? "true" : "false") + "\n";
	s += "}\n";
	return s;
}
