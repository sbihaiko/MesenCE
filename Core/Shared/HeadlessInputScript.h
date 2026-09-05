#pragma once
#include "pch.h"

//F9.14 (ADR-0157): the pure half of the headless input harness - the script
//text a person writes, turned into absolute emulated-frame ranges. No
//Emulator, no control device, no host clock: this compiles and links on its
//own, which is what lets scripts/core_unit_tests.cpp cover the parser.
//
//A script line is "<count><unit> <buttons>":
//  <count>  a positive number
//  <unit>   'f' (emulated frames) or 's' (seconds, resolved to frames here,
//           at the region's nominal frame rate, rounded to nearest)
//  <buttons> a token drawn from UDLRABST (Select / sTart), or "-" for nothing
//
//A bare count with no unit is a parse error - the pre-F9.14 scripts wrote
//bare numbers meaning seconds, and silently reading one as a frame count
//would quietly corrupt every hand-tuned sequence in the recorder library.
//
//Blank lines and lines whose first non-space character is '#' are ignored.

struct HeadlessInputStep
{
	//Absolute frame numbers, counted from the frame the script starts on.
	//The range is half-open: the step is held while StartFrame <= frame < EndFrame.
	uint32_t StartFrame = 0;
	uint32_t EndFrame = 0;

	//Lower-case device button names, matched against
	//BaseControlDevice::GetKeyNameAssociations(). A letter expands to every
	//name the product consoles use for it ("a" is also the SMS pad's "two"),
	//so one script drives NES, GB and SMS without knowing which is loaded;
	//a name the loaded device does not expose is simply never applied.
	vector<string> Buttons;
};

class HeadlessInputScript
{
public:
	//Nominal frame rates of the two regions the harness can force (the "pal"
	//flag). Used only to resolve 's' steps at parse time.
	static constexpr double NtscFrameRate = 60.0988;
	static constexpr double PalFrameRate = 50.0070;

	static uint32_t SecondsToFrames(double seconds, double frameRate);

	//Returns false and fills 'error' (en-US, naming the offending line) when
	//the text is not a valid script. 'steps' is left untouched on failure.
	static bool Parse(const string& text, double frameRate, vector<HeadlessInputStep>& steps, string& error);

	//The step covering 'frame', or nullptr past the end of the script.
	//Steps are contiguous and ordered, so this is a plain scan.
	static const HeadlessInputStep* GetStep(const vector<HeadlessInputStep>& steps, uint32_t frame);

	//Total length of the script, in frames (0 when empty).
	static uint32_t GetFrameCount(const vector<HeadlessInputStep>& steps);
};
