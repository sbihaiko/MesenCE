#include "pch.h"
#include "JsonReader.h"
#include <cstdlib>
#include <cerrno>

static constexpr int kMaxDepth = 64;

const JsonValue* JsonValue::Get(const string& key) const
{
	if(_type != Type::Object) {
		return nullptr;
	}
	const JsonValue* found = nullptr;
	for(const auto& member : _object) {
		if(member.first == key) {
			found = &member.second;
		}
	}
	return found;
}

string JsonValue::GetString(const string& key, const string& defaultValue) const
{
	const JsonValue* value = Get(key);
	if(value && value->IsString()) {
		return value->GetString();
	}
	return defaultValue;
}

bool JsonReader::Parse(const string& text, JsonValue& out)
{
	_cur = text.data();
	_end = text.data() + text.size();
	_error.clear();
	out = JsonValue();

	//Tolerate a UTF-8 BOM (common on Windows editors); the spec asks for UTF-8
	if(_end - _cur >= 3 && (uint8_t)_cur[0] == 0xEF && (uint8_t)_cur[1] == 0xBB && (uint8_t)_cur[2] == 0xBF) {
		_cur += 3;
	}

	SkipWhitespace();
	if(!ParseValue(out, 0)) {
		return false;
	}
	SkipWhitespace();
	if(_cur != _end) {
		return Fail("unexpected content after top-level value");
	}
	return true;
}

void JsonReader::SkipWhitespace()
{
	while(_cur < _end && (*_cur == ' ' || *_cur == '\t' || *_cur == '\n' || *_cur == '\r')) {
		_cur++;
	}
}

bool JsonReader::Fail(const string& message)
{
	if(_error.empty()) {
		_error = message;
	}
	return false;
}

bool JsonReader::ParseValue(JsonValue& out, int depth)
{
	if(depth > kMaxDepth) {
		return Fail("nesting too deep");
	}
	if(_cur >= _end) {
		return Fail("unexpected end of input");
	}

	switch(*_cur) {
		case '{': return ParseObject(out, depth + 1);
		case '[': return ParseArray(out, depth + 1);
		case '"':
			out._type = JsonValue::Type::String;
			return ParseString(out._string);
		case 't': return ParseLiteral("true", out);
		case 'f': return ParseLiteral("false", out);
		case 'n': return ParseLiteral("null", out);
		default:
			if(*_cur == '-' || (*_cur >= '0' && *_cur <= '9')) {
				return ParseNumber(out);
			}
			return Fail(string("unexpected character '") + *_cur + "'");
	}
}

bool JsonReader::ParseLiteral(const char* literal, JsonValue& out)
{
	size_t len = strlen(literal);
	if((size_t)(_end - _cur) < len || strncmp(_cur, literal, len) != 0) {
		return Fail(string("invalid literal, expected ") + literal);
	}
	_cur += len;
	if(literal[0] == 'n') {
		out._type = JsonValue::Type::Null;
	} else {
		out._type = JsonValue::Type::Bool;
		out._bool = literal[0] == 't';
	}
	return true;
}

bool JsonReader::ParseNumber(JsonValue& out)
{
	const char* start = _cur;
	if(*_cur == '-') {
		_cur++;
	}
	if(_cur >= _end || *_cur < '0' || *_cur > '9') {
		return Fail("invalid number");
	}
	if(*_cur == '0') {
		_cur++;
	} else {
		while(_cur < _end && *_cur >= '0' && *_cur <= '9') {
			_cur++;
		}
	}
	if(_cur < _end && *_cur == '.') {
		_cur++;
		if(_cur >= _end || *_cur < '0' || *_cur > '9') {
			return Fail("invalid number (fraction)");
		}
		while(_cur < _end && *_cur >= '0' && *_cur <= '9') {
			_cur++;
		}
	}
	if(_cur < _end && (*_cur == 'e' || *_cur == 'E')) {
		_cur++;
		if(_cur < _end && (*_cur == '+' || *_cur == '-')) {
			_cur++;
		}
		if(_cur >= _end || *_cur < '0' || *_cur > '9') {
			return Fail("invalid number (exponent)");
		}
		while(_cur < _end && *_cur >= '0' && *_cur <= '9') {
			_cur++;
		}
	}

	string text(start, _cur - start);
	errno = 0;
	char* endPtr = nullptr;
	double value = strtod(text.c_str(), &endPtr);
	if(endPtr != text.c_str() + text.size()) {
		return Fail("invalid number");
	}
	out._type = JsonValue::Type::Number;
	out._number = value;
	return true;
}

bool JsonReader::ParseHex4(uint32_t& out)
{
	if(_end - _cur < 4) {
		return Fail("truncated \\u escape");
	}
	out = 0;
	for(int i = 0; i < 4; i++) {
		char c = *_cur++;
		out <<= 4;
		if(c >= '0' && c <= '9') {
			out |= c - '0';
		} else if(c >= 'a' && c <= 'f') {
			out |= c - 'a' + 10;
		} else if(c >= 'A' && c <= 'F') {
			out |= c - 'A' + 10;
		} else {
			return Fail("invalid \\u escape");
		}
	}
	return true;
}

void JsonReader::AppendUtf8(string& out, uint32_t cp)
{
	if(cp < 0x80) {
		out += (char)cp;
	} else if(cp < 0x800) {
		out += (char)(0xC0 | (cp >> 6));
		out += (char)(0x80 | (cp & 0x3F));
	} else if(cp < 0x10000) {
		out += (char)(0xE0 | (cp >> 12));
		out += (char)(0x80 | ((cp >> 6) & 0x3F));
		out += (char)(0x80 | (cp & 0x3F));
	} else {
		out += (char)(0xF0 | (cp >> 18));
		out += (char)(0x80 | ((cp >> 12) & 0x3F));
		out += (char)(0x80 | ((cp >> 6) & 0x3F));
		out += (char)(0x80 | (cp & 0x3F));
	}
}

bool JsonReader::ParseString(string& out)
{
	//_cur points at the opening quote
	_cur++;
	out.clear();
	while(true) {
		if(_cur >= _end) {
			return Fail("unterminated string");
		}
		uint8_t c = (uint8_t)*_cur++;
		if(c == '"') {
			return true;
		}
		if(c < 0x20) {
			return Fail("control character in string");
		}
		if(c != '\\') {
			out += (char)c;
			continue;
		}

		if(_cur >= _end) {
			return Fail("unterminated escape");
		}
		char esc = *_cur++;
		switch(esc) {
			case '"': out += '"'; break;
			case '\\': out += '\\'; break;
			case '/': out += '/'; break;
			case 'b': out += '\b'; break;
			case 'f': out += '\f'; break;
			case 'n': out += '\n'; break;
			case 'r': out += '\r'; break;
			case 't': out += '\t'; break;
			case 'u': {
				uint32_t cp;
				if(!ParseHex4(cp)) {
					return false;
				}
				if(cp >= 0xD800 && cp <= 0xDBFF) {
					//High surrogate: a low surrogate escape must follow
					if(_end - _cur < 6 || _cur[0] != '\\' || _cur[1] != 'u') {
						return Fail("unpaired surrogate");
					}
					_cur += 2;
					uint32_t low;
					if(!ParseHex4(low)) {
						return false;
					}
					if(low < 0xDC00 || low > 0xDFFF) {
						return Fail("invalid low surrogate");
					}
					cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
				} else if(cp >= 0xDC00 && cp <= 0xDFFF) {
					return Fail("unpaired surrogate");
				}
				AppendUtf8(out, cp);
				break;
			}
			default:
				return Fail(string("invalid escape '\\") + esc + "'");
		}
	}
}

bool JsonReader::ParseArray(JsonValue& out, int depth)
{
	_cur++; //'['
	out._type = JsonValue::Type::Array;
	SkipWhitespace();
	if(_cur < _end && *_cur == ']') {
		_cur++;
		return true;
	}
	while(true) {
		SkipWhitespace();
		JsonValue element;
		if(!ParseValue(element, depth)) {
			return false;
		}
		out._array.push_back(std::move(element));
		SkipWhitespace();
		if(_cur >= _end) {
			return Fail("unterminated array");
		}
		if(*_cur == ',') {
			_cur++;
			continue;
		}
		if(*_cur == ']') {
			_cur++;
			return true;
		}
		return Fail("expected ',' or ']' in array");
	}
}

bool JsonReader::ParseObject(JsonValue& out, int depth)
{
	_cur++; //'{'
	out._type = JsonValue::Type::Object;
	SkipWhitespace();
	if(_cur < _end && *_cur == '}') {
		_cur++;
		return true;
	}
	while(true) {
		SkipWhitespace();
		if(_cur >= _end || *_cur != '"') {
			return Fail("expected string key in object");
		}
		string key;
		if(!ParseString(key)) {
			return false;
		}
		SkipWhitespace();
		if(_cur >= _end || *_cur != ':') {
			return Fail("expected ':' after object key");
		}
		_cur++;
		SkipWhitespace();
		JsonValue value;
		if(!ParseValue(value, depth)) {
			return false;
		}
		out._object.emplace_back(std::move(key), std::move(value));
		SkipWhitespace();
		if(_cur >= _end) {
			return Fail("unterminated object");
		}
		if(*_cur == ',') {
			_cur++;
			continue;
		}
		if(*_cur == '}') {
			_cur++;
			return true;
		}
		return Fail("expected ',' or '}' in object");
	}
}
