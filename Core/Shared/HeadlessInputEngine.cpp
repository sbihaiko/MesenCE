#include "pch.h"
#include "Shared/HeadlessInputEngine.h"

HeadlessInputEngine::HeadlessInputEngine(IHeadlessInputHost* host)
{
	_host = host;
}

bool HeadlessInputEngine::LoadScript(const string& text, double frameRate, string& error)
{
	vector<HeadlessInputStep> steps;
	if(!HeadlessInputScript::Parse(text, frameRate, steps, error)) {
		return false;
	}

	auto lock = _lock.AcquireSafe();
	_steps = std::move(steps);
	return true;
}

void HeadlessInputEngine::SetPauseFrame(uint32_t frame)
{
	auto lock = _lock.AcquireSafe();
	_pauseFrame = frame;
	_pauseRequested = false;
}

void HeadlessInputEngine::SetScriptStartFrame(uint32_t frame)
{
	auto lock = _lock.AcquireSafe();
	_scriptStartFrame = frame;
}

uint32_t HeadlessInputEngine::GetScriptFrameCount()
{
	auto lock = _lock.AcquireSafe();
	return HeadlessInputScript::GetFrameCount(_steps);
}

void HeadlessInputEngine::ApplyToTarget(IHeadlessInputTarget& target, const HeadlessInputStep& step)
{
	if(step.Buttons.empty()) {
		return;
	}

	//Resolved by name rather than by bit index: the same script letter is a
	//different bit on a NES pad, a GB pad and a SMS pad, and a name the loaded
	//device does not expose simply never matches.
	for(HeadlessButtonName& button : target.GetButtonNames()) {
		if(button.IsNumeric) {
			continue;
		}
		for(const string& name : step.Buttons) {
			if(name == button.Name) {
				target.PressButton(button.ButtonId);
				break;
			}
		}
	}
}

bool HeadlessInputEngine::ApplyFrame(IHeadlessInputTarget& target)
{
	uint32_t frame = _host->GetFrameCount();

	auto lock = _lock.AcquireSafe();

	//The harness drives port 1 only (it forces a standard controller there -
	//without a control device the whole provider chain is never consulted).
	if(target.GetPort() == 0 && frame >= _scriptStartFrame) {
		const HeadlessInputStep* step = HeadlessInputScript::GetStep(_steps, frame - _scriptStartFrame);
		if(step) {
			ApplyToTarget(target, *step);
		}
	}

	//The run's end, decided inside the frame it lands on rather than by a host
	//timer that fires whenever the OS gets round to it. Pause() only sets a
	//flag; the emulation thread parks after finishing this frame, so the run
	//covers exactly [0, _pauseFrame) frames on every host.
	if(!_pauseRequested && frame >= _pauseFrame) {
		_pauseRequested = true;
		if(_host->IsDebugging()) {
			_host->Log("[Headless] frame " + std::to_string(frame) + " reached, but the debugger is attached - not pausing");
		} else {
			_host->Pause();
		}
	}

	//Overlay on top of whatever the physical input produced, never replace it
	return false;
}

void HeadlessInputEngine::OnGameLoaded()
{
	_host->RegisterInputProvider();
}
