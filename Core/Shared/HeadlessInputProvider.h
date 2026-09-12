#pragma once
#include "pch.h"
#include "Shared/HeadlessInputEngine.h"
#include "Shared/Interfaces/IInputProvider.h"
#include "Shared/Interfaces/INotificationListener.h"

class BaseControlDevice;
class Emulator;

//F9.14 (ADR-0157): plays a whole headless input script, expressed in absolute
//emulated frames, from inside the frame.
//
//The point is determinism. IInputProvider::SetInput runs on the emulation
//thread, once per frame (NesPpu at InputScanline, SmsConsole/Gameboy at end of
//frame), so what is pressed on frame N is resolved against the core's own
//frame counter and never against the host clock. Nothing outside the core has
//to wake up on time, or at all: the provider owns the entire script, so a
//loaded machine changes how long a recording takes and not what it contains.
//
//The same hook carries the run's end. A recording that stops when a host timer
//expires has covered a host-dependent number of frames; one that pauses the
//emulator from inside the frame it was told to stop on has covered exactly the
//frames the script declares, which is what makes two runs byte-identical
//(ADR-0157 section 4).
//
//H9 (ADR-0127): the decisions above no longer live here. This class is the
//stateful partner of Core/Shared/HeadlessInputEngine.{h,cpp} - it binds the
//live Emulator and the live BaseControlDevice to the engine's two narrow
//interfaces and forwards. Everything the engine decides is covered without a
//ROM by scripts/core_unit_tests.cpp (Bloco R); what is left here is the
//binding itself, which only a real core can exercise.
//
//Prior art: zerkz/MesenCE's Core/Shared/InputOverrideProvider.{h,cpp} (GPLv3,
//same licence as this tree) - the IInputProvider shape, resolving buttons by
//name through GetKeyNameAssociations(), overlaying instead of replacing, and
//the GameLoaded re-registration. This version differs where it matters for
//F9.14: it holds the whole script in absolute frame numbers rather than one
//override expiring N frames from "now", which is what makes it reproducible.
//The fake-core test model is prior art too: lusid/MesenCE's UI.Tests/Mcp/
//(GPLv3), which drives an automation surface through a faked emulator API.
class HeadlessInputProvider : public IInputProvider, public INotificationListener, private IHeadlessInputHost, public std::enable_shared_from_this<HeadlessInputProvider>
{
private:
	Emulator* _emu = nullptr;
	HeadlessInputEngine _engine;

	//IHeadlessInputHost - the Emulator, reduced to what the engine asks of it.
	uint32_t GetFrameCount() override;
	bool IsDebugging() override;
	void Pause() override;
	void RegisterInputProvider() override;
	void Log(const string& message) override;

public:
	HeadlessInputProvider(Emulator* emu);

	//Registers as a notification listener and, if a game is already loaded, as
	//an input provider. Must be called on a shared_ptr-owned instance.
	void Init();

	//Replaces the script. Returns false with an en-US 'error' when the text
	//does not parse (see HeadlessInputScript::Parse).
	bool LoadScript(const string& text, double frameRate, string& error);

	//Pause the emulator from inside the first frame whose number reaches
	//'frame'. UINT32_MAX (the default) never pauses.
	void SetPauseFrame(uint32_t frame);
	void SetScriptStartFrame(uint32_t frame);

	//Length of the loaded script in frames.
	uint32_t GetScriptFrameCount();

	bool SetInput(BaseControlDevice* device) override;
	void ProcessNotification(ConsoleNotificationType type, void* parameter) override;
};
