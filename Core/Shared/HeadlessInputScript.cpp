#include "pch.h"
#include "Shared/HeadlessInputScript.h"

namespace
{
	//One script letter -> every device button name that means it across the
	//product consoles (NesController/GbController use "a"/"b"/"start", the
	//SMS pad calls the same buttons "two"/"one"/"pause").
	struct ButtonAlias
	{
		char Letter;
		const char* Names[3];
	};

	constexpr ButtonAlias kButtonAliases[] = {
		{ 'U', { "up", nullptr, nullptr } },
		{ 'D', { "down", nullptr, nullptr } },
		{ 'L', { "left", nullptr, nullptr } },
		{ 'R', { "right", nullptr, nullptr } },
		{ 'A', { "a", "two", nullptr } },
		{ 'B', { "b", "one", nullptr } },
		{ 'S', { "select", nullptr, nullptr } },
		{ 'T', { "start", "pause", nullptr } },
	};

	string Trim(const string& value)
	{
		size_t first = value.find_first_not_of(" \t\r\n");
		if(first == string::npos) {
			return "";
		}
		size_t last = value.find_last_not_of(" \t\r\n");
		return value.substr(first, last - first + 1);
	}
}

uint32_t HeadlessInputScript::SecondsToFrames(double seconds, double frameRate)
{
	if(seconds <= 0 || frameRate <= 0) {
		return 0;
	}
	double frames = std::round(seconds * frameRate);
	if(frames > (double)UINT32_MAX) {
		return UINT32_MAX;
	}
	return (uint32_t)frames;
}

bool HeadlessInputScript::Parse(const string& text, double frameRate, vector<HeadlessInputStep>& steps, string& error)
{
	vector<HeadlessInputStep> parsed;
	error = "";

	size_t lineNumber = 0;
	size_t pos = 0;
	uint32_t nextFrame = 0;

	while(pos <= text.size()) {
		size_t end = text.find('\n', pos);
		string line = text.substr(pos, end == string::npos ? string::npos : end - pos);
		pos = end == string::npos ? text.size() + 1 : end + 1;
		lineNumber++;

		string trimmed = Trim(line);
		if(trimmed.empty() || trimmed[0] == '#') {
			continue;
		}

		auto fail = [&](const string& reason) {
			error = "input script line " + std::to_string(lineNumber) + ": " + reason + " (line reads \"" + trimmed + "\")";
			return false;
		};

		//<count><unit>
		size_t sep = trimmed.find_first_of(" \t");
		if(sep == string::npos) {
			return fail("missing the buttons field - expected \"<count>f <buttons>\" or \"<count>s <buttons>\"");
		}
		string count = trimmed.substr(0, sep);
		string buttons = Trim(trimmed.substr(sep));

		char unit = count.empty() ? 0 : count[count.size() - 1];
		if(unit != 'f' && unit != 's') {
			return fail("the duration needs an explicit unit - \"" + count + "f\" for frames or \"" + count + "s\" for seconds (a bare number is not accepted)");
		}

		string number = count.substr(0, count.size() - 1);
		if(number.empty()) {
			return fail("the duration has a unit but no number");
		}
		char* parseEnd = nullptr;
		double value = strtod(number.c_str(), &parseEnd);
		if(parseEnd != number.c_str() + number.size() || value <= 0) {
			return fail("\"" + number + "\" is not a positive number");
		}

		uint32_t frames;
		if(unit == 'f') {
			if(value != std::floor(value)) {
				return fail("a frame count must be a whole number - write \"" + number + "s\" to declare seconds");
			}
			if(value > (double)UINT32_MAX) {
				return fail("\"" + number + "f\" is more frames than a script can address");
			}
			frames = (uint32_t)value;
		} else {
			frames = SecondsToFrames(value, frameRate);
			if(frames == 0) {
				return fail("\"" + number + "s\" rounds to zero frames at " + std::to_string(frameRate) + " fps");
			}
		}

		if(frames > UINT32_MAX - nextFrame) {
			return fail("the script's total length overflows the frame counter");
		}

		HeadlessInputStep step;
		step.StartFrame = nextFrame;
		step.EndFrame = nextFrame + frames;
		nextFrame = step.EndFrame;

		if(buttons != "-") {
			for(char c : buttons) {
				const ButtonAlias* alias = nullptr;
				for(const ButtonAlias& candidate : kButtonAliases) {
					if(candidate.Letter == c) {
						alias = &candidate;
						break;
					}
				}
				if(!alias) {
					return fail(string("\"") + c + "\" is not a known button - expected letters from UDLRABST (Select, sTart) or \"-\" for nothing held");
				}
				for(const char* name : alias->Names) {
					if(name) {
						step.Buttons.push_back(name);
					}
				}
			}
		}

		parsed.push_back(std::move(step));
	}

	steps = std::move(parsed);
	return true;
}

const HeadlessInputStep* HeadlessInputScript::GetStep(const vector<HeadlessInputStep>& steps, uint32_t frame)
{
	for(const HeadlessInputStep& step : steps) {
		if(frame < step.StartFrame) {
			break;
		}
		if(frame < step.EndFrame) {
			return &step;
		}
	}
	return nullptr;
}

uint32_t HeadlessInputScript::GetFrameCount(const vector<HeadlessInputStep>& steps)
{
	return steps.empty() ? 0 : steps[steps.size() - 1].EndFrame;
}
