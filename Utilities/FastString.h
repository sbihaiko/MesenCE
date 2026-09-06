#pragma once
#include "pch.h"

class FastString
{
private:
	char _buffer[1000];
	uint16_t _pos = 0;
	bool _lowerCase = false;

	void WriteAll() {}

public:
#ifdef _MSC_VER
	#pragma warning(disable : 26495)
#endif
	FastString(bool lowerCase = false) { _lowerCase = lowerCase; }
	FastString(const char* str, int size) { Write(str, size); }
	FastString(string& str) { Write(str); }
#ifdef _MSC_VER
	#pragma warning(default : 26495)
#endif

	void WriteSafe(char c)
	{
		if(_pos < 999) {
			_buffer[_pos++] = c;
		}
	}

	void Write(char c)
	{
		if(_pos < 999) {
			if(_lowerCase) {
				_buffer[_pos++] = ::tolower(c);
			} else {
				_buffer[_pos++] = c;
			}
		}
	}

	void Write(const char* str, int size)
	{
		if(size > 999 - _pos) {
			size = 999 - _pos;
		}
		if(size <= 0) {
			return;
		}
		if(_lowerCase) {
			for(int i = 0; i < size; i++) {
				_buffer[_pos + i] = ::tolower(str[i]);
			}
		} else {
			memcpy(_buffer + _pos, str, size);
		}
		_pos += size;
	}

	void Delimiter(const char* str)
	{
		if(_pos > 0) {
			Write(str, (uint16_t)strlen(str));
		}
	}

	void Write(const char* str)
	{
		Write(str, (uint16_t)strlen(str));
	}

	void Write(string& str, bool preserveCase = false)
	{
		size_t size = str.size();
		if(size > (size_t)(999 - _pos)) {
			size = (size_t)(999 - _pos);
		}
		if(size == 0) {
			return;
		}
		if(_lowerCase && !preserveCase) {
			for(size_t i = 0; i < size; i++) {
				_buffer[_pos + i] = ::tolower(str[i]);
			}
		} else {
			memcpy(_buffer + _pos, str.c_str(), size);
		}
		_pos += (uint16_t)size;
	}

	void Write(FastString& str)
	{
		uint16_t size = str._pos;
		if(size > 999 - _pos) {
			size = (uint16_t)(999 - _pos);
		}
		if(size > 0) {
			memcpy(_buffer + _pos, str._buffer, size);
			_pos += size;
		}
	}

	const char* ToString()
	{
		_buffer[_pos] = 0;
		return _buffer;
	}

	uint16_t GetSize()
	{
		return _pos;
	}

	void Reset()
	{
		_pos = 0;
	}

	template<typename T, typename... Args>
	void WriteAll(T first, Args... args)
	{
		Write(first);
		WriteAll(args...);
	}

	const char operator[](int idx)
	{
		return _buffer[idx];
	}
};
