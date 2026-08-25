#pragma once
#include "pch.h"

//Minimal strict JSON (RFC 8259) reader - ADR-0038. Produces an immutable
//value tree; any syntax error invalidates the whole document. No serializer,
//no comments/trailing commas/NaN. Object keys keep document order (duplicate
//keys: last one wins on lookup).
class JsonValue
{
public:
	enum class Type : uint8_t
	{
		Null,
		Bool,
		Number,
		String,
		Array,
		Object
	};

private:
	Type _type = Type::Null;
	bool _bool = false;
	double _number = 0;
	string _string;
	vector<JsonValue> _array;
	vector<std::pair<string, JsonValue>> _object;

	friend class JsonReader;

public:
	Type GetType() const { return _type; }
	bool IsNull() const { return _type == Type::Null; }
	bool IsBool() const { return _type == Type::Bool; }
	bool IsNumber() const { return _type == Type::Number; }
	bool IsString() const { return _type == Type::String; }
	bool IsArray() const { return _type == Type::Array; }
	bool IsObject() const { return _type == Type::Object; }

	bool GetBool() const { return _bool; }
	double GetNumber() const { return _number; }
	const string& GetString() const { return _string; }
	const vector<JsonValue>& GetArray() const { return _array; }
	const vector<std::pair<string, JsonValue>>& GetObject() const { return _object; }

	//Object member lookup; returns nullptr when this is not an object or the
	//key is absent
	const JsonValue* Get(const string& key) const;

	//Convenience: member as string, or defaultValue when missing/not a string
	string GetString(const string& key, const string& defaultValue = "") const;
};

class JsonReader
{
private:
	const char* _cur = nullptr;
	const char* _end = nullptr;
	string _error;

	void SkipWhitespace();
	bool Fail(const string& message);
	bool ParseValue(JsonValue& out, int depth);
	bool ParseString(string& out);
	bool ParseNumber(JsonValue& out);
	bool ParseArray(JsonValue& out, int depth);
	bool ParseObject(JsonValue& out, int depth);
	bool ParseLiteral(const char* literal, JsonValue& out);
	bool ParseHex4(uint32_t& out);
	static void AppendUtf8(string& out, uint32_t codepoint);

public:
	//Parses the whole text; returns false (and sets GetError()) on any
	//syntax error, including trailing non-whitespace content
	bool Parse(const string& text, JsonValue& out);
	const string& GetError() const { return _error; }
};
