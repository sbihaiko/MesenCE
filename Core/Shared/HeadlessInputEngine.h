#pragma once
#include "pch.h"
#include "Shared/HeadlessInputScript.h"
#include "Utilities/SimpleLock.h"

//H9 (ADR-0127, ADR-0157): the core-free half of the headless input harness -
//everything HeadlessInputProvider does once the Emulator and the
//BaseControlDevice are reduced to the two questions it actually asks them.
//
//Its stateful partner is Core/Shared/HeadlessInputProvider.{h,cpp}, which is
//now a thin adapter: it implements IInputProvider/INotificationListener,
//wraps the live Emulator as IHeadlessInputHost and the live control device as
//IHeadlessInputTarget, and forwards. Nothing but the wrapping lives there.
//
//The point of the split is that the interesting failures of the harness -
//applying a step one frame late, pausing one frame early, replacing physical
//input instead of overlaying it, forgetting to re-register when a game loads -
//used to be reachable only through a 40-300 s recording with a real ROM. Here
//they are reachable from scripts/core_unit_tests.cpp with a fake host and a
//fake target, in microseconds and without a core (Bloco R).
//
//HeadlessInputScript stays the pure, stateless layer below this one: it turns
//script text into absolute frame ranges and answers "which buttons on frame
//N". This class is where the state lives - the loaded script, the stop frame,
//and the once-only latch that fires it.

//A control device's named buttons, as the engine needs them. Mirrors
//DeviceButtonName without dragging in BaseControlDevice.h (and with it the
//whole console); the adapter copies the fields across.
struct HeadlessButtonName
{
	string Name;
	int ButtonId = 0;
	bool IsNumeric = false;
};

//What the engine needs from a control device.
class IHeadlessInputTarget
{
public:
	virtual ~IHeadlessInputTarget() = default;

	virtual uint8_t GetPort() = 0;
	virtual vector<HeadlessButtonName> GetButtonNames() = 0;

	//Presses a button. Never releases one: the engine overlays on top of
	//whatever the physical input already produced this frame.
	virtual void PressButton(int buttonId) = 0;
};

//What the engine needs from the emulator.
class IHeadlessInputHost
{
public:
	virtual ~IHeadlessInputHost() = default;

	//The core's own frame counter - the only clock the harness trusts.
	virtual uint32_t GetFrameCount() = 0;

	//Emulator::Pause() steps the debugger instead of setting the pause flag,
	//which is not something to do from the emulation thread.
	virtual bool IsDebugging() = 0;
	virtual void Pause() = 0;

	//A new console - and with it a new control manager, holding no providers -
	//is created on every game load, so the provider has to ask for its slot
	//back. This is the root of the "input= is silently a no-op" trap.
	virtual void RegisterInputProvider() = 0;

	//Developer-facing log line (en-US). Split out so the tests can read what
	//the engine decided without linking MessageManager's global state.
	virtual void Log(const string& message) = 0;
};

class HeadlessInputEngine
{
private:
	IHeadlessInputHost* _host = nullptr;
	SimpleLock _lock;

	vector<HeadlessInputStep> _steps;
	uint32_t _pauseFrame = UINT32_MAX;
	bool _pauseRequested = false;

	void ApplyToTarget(IHeadlessInputTarget& target, const HeadlessInputStep& step);

public:
	HeadlessInputEngine(IHeadlessInputHost* host);

	//Replaces the script. Returns false with an en-US 'error' when the text
	//does not parse (see HeadlessInputScript::Parse); the previously loaded
	//script is left in place in that case.
	bool LoadScript(const string& text, double frameRate, string& error);

	//Pause the host from inside the first frame whose number reaches 'frame'.
	//UINT32_MAX (the default) never pauses. Re-arms the latch, so setting a
	//new stop frame after a run has already stopped works.
	void SetPauseFrame(uint32_t frame);

	//Length of the loaded script in frames.
	uint32_t GetScriptFrameCount();

	//Runs one frame of the script against 'target'. Returns the value
	//IInputProvider::SetInput must return: always false, i.e. overlay on top
	//of the physical input rather than replace it.
	bool ApplyFrame(IHeadlessInputTarget& target);

	//Re-registers with the freshly created control manager.
	void OnGameLoaded();
};
