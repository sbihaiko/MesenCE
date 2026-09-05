#include "pch.h"
#include "Shared/HeadlessInputProvider.h"
#include "Shared/BaseControlDevice.h"
#include "Shared/Emulator.h"
#include "Shared/MessageManager.h"
#include "Shared/NotificationManager.h"

HeadlessInputProvider::HeadlessInputProvider(Emulator* emu)
{
	_emu = emu;
}

void HeadlessInputProvider::Init()
{
	_emu->GetNotificationManager()->RegisterNotificationListener(shared_from_this());
	_emu->RegisterInputProvider(this);
}

bool HeadlessInputProvider::LoadScript(const string& text, double frameRate, string& error)
{
	vector<HeadlessInputStep> steps;
	if(!HeadlessInputScript::Parse(text, frameRate, steps, error)) {
		return false;
	}

	auto lock = _lock.AcquireSafe();
	_steps = steps;
	return true;
}

void HeadlessInputProvider::SetPauseFrame(uint32_t frame)
{
	auto lock = _lock.AcquireSafe();
	_pauseFrame = frame;
	_pauseRequested = false;
}

uint32_t HeadlessInputProvider::GetScriptFrameCount()
{
	auto lock = _lock.AcquireSafe();
	return HeadlessInputScript::GetFrameCount(_steps);
}

void HeadlessInputProvider::ApplyToDevice(BaseControlDevice* device, const HeadlessInputStep& step)
{
	if(step.Buttons.empty()) {
		return;
	}

	//Resolved by name rather than by bit index: the same script letter is a
	//different bit on a NES pad, a GB pad and a SMS pad, and a name the loaded
	//device does not expose simply never matches.
	for(DeviceButtonName& button : device->GetKeyNameAssociations()) {
		if(button.IsNumeric) {
			continue;
		}
		for(const string& name : step.Buttons) {
			if(name == button.Name) {
				device->SetBitValue((uint8_t)button.ButtonId, true);
				break;
			}
		}
	}
}

bool HeadlessInputProvider::SetInput(BaseControlDevice* device)
{
	uint32_t frame = _emu->GetFrameCount();

	auto lock = _lock.AcquireSafe();

	//The harness drives port 1 only (it forces a standard controller there -
	//without a control device the whole provider chain is never consulted).
	if(device->GetPort() == 0) {
		const HeadlessInputStep* step = HeadlessInputScript::GetStep(_steps, frame);
		if(step) {
			ApplyToDevice(device, *step);
		}
	}

	//The run's end, decided inside the frame it lands on rather than by a host
	//timer that fires whenever the OS gets round to it. Pause() only sets a
	//flag; the emulation thread parks after finishing this frame, so the run
	//covers exactly [0, _pauseFrame) frames on every host.
	if(!_pauseRequested && frame >= _pauseFrame) {
		_pauseRequested = true;
		if(_emu->IsDebugging()) {
			//Emulator::Pause() steps the debugger instead of setting the flag,
			//which is not something to do from the emulation thread.
			MessageManager::Log("[Headless] frame " + std::to_string(frame) + " reached, but the debugger is attached - not pausing");
		} else {
			_emu->Pause();
		}
	}

	//Overlay on top of whatever the physical input produced, never replace it
	return false;
}

void HeadlessInputProvider::ProcessNotification(ConsoleNotificationType type, void* parameter)
{
	if(type == ConsoleNotificationType::GameLoaded) {
		//A new console - and with it a new control manager, holding no
		//providers - is created on every game load. This is the root of the
		//"input= is silently a no-op" trap the harness used to work around.
		_emu->RegisterInputProvider(this);
	}
}
