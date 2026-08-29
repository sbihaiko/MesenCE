#include "Common.h"
#include "WindowsKeyManager.h"
#include "Shared/KeyDefinitions.h"

WindowsKeyManager::WindowsKeyManager(Emulator* emu, HWND hWnd)
{
	_emu = emu;
	_hWnd = hWnd;

	ResetKeyState();

	_keyDefinitions = KeyDefinition::GetSharedKeyDefinitions();

	//Init XInput buttons
	vector<string> buttonNames = {
		"Up", "Down", "Left", "Right", "Start", "Back", "L3", "R3", "L1", "R1", "?", "?", "A", "B", "X", "Y", "L2", "R2", "RT Up", "RT Down", "RT Left", "RT Right", "LT Up", "LT Down", "LT Left", "LT Right", "LT Y", "LT X", "RT Y", "RT X", "AL", "AR"
	};

	for(int i = 0; i < 4; i++) {
		for(int j = 0; j < (int)buttonNames.size(); j++) {
			_keyDefinitions.push_back({ "Pad" + std::to_string(i + 1) + " " + buttonNames[j], (uint32_t)(WindowsKeyManager::BaseGamepadIndex + i * 0x100 + j + 1) });
		}
	}

	//Init DirectInput buttons
	vector<string> diButtonNames = {
		"Y+", "Y-", "X-", "X+", "Y2+", "Y2-", "X2-", "X2+", "Z+", "Z-", "Z2+", "Z2-", "DPad Up", "DPad Down", "DPad Right", "DPad Left"
	};
	vector<string> axisNames = {
		"Y", "X", "Y2", "X2", "Z", "Z2"
	};
	for(int i = 0; i < 16; i++) {
		for(int j = 0; j < (int)diButtonNames.size(); j++) {
			_keyDefinitions.push_back({ "Joy" + std::to_string(i + 1) + " " + diButtonNames[j], (uint32_t)(WindowsKeyManager::BaseDirectInputIndex + i * 0x100 + j) });
		}

		for(int j = 0; j < 128; j++) {
			_keyDefinitions.push_back({ "Joy" + std::to_string(i + 1) + " But" + std::to_string(j + 1), (uint32_t)(WindowsKeyManager::BaseDirectInputIndex + i * 0x100 + j + diButtonNames.size()) });
		}

		for(int j = 0; j < (int)axisNames.size(); j++) {
			_keyDefinitions.push_back({ "Joy" + std::to_string(i + 1) + " " + axisNames[j], (uint32_t)(WindowsKeyManager::BaseDirectInputIndex + i * 0x100 + j + diButtonNames.size() + 128) });
		}
	}

	for(KeyDefinition& keyDef : _keyDefinitions) {
		_keyNames[keyDef.keyCode] = keyDef.name;
		_keyCodes[keyDef.name] = keyDef.keyCode;
	}

	StartUpdateDeviceThread();
}

WindowsKeyManager::~WindowsKeyManager()
{
	_stopUpdateDeviceThread = true;
	_stopSignal.Signal();
	_updateDeviceThread.join();
}

void WindowsKeyManager::StartUpdateDeviceThread()
{
	_updateDeviceThread = std::thread([=]() {
		_xInput.reset(new XInputManager(_emu));
		_directInput.reset(new DirectInputManager(_emu, _hWnd));

		while(!_stopUpdateDeviceThread) {
			//Check for newly plugged in XInput controllers every 5 secs
			//Do not check for DirectInput controllers because this takes more time and sometimes causes issues/freezes
			if(_xInput->NeedToUpdate()) {
				_xInput->UpdateDeviceList();
			}
			_stopSignal.Wait(5000);
		}
	});
}

void WindowsKeyManager::RefreshState()
{
	if(!_xInput || !_directInput) {
		return;
	}

	_xInput->RefreshState();
	_directInput->RefreshState();
}

bool WindowsKeyManager::IsKeyPressed(uint16_t key)
{
	if(_disableAllKeys || key == 0) {
		return false;
	}

	if(key >= WindowsKeyManager::BaseGamepadIndex) {
		if(!_xInput || !_directInput) {
			return false;
		}

		if(key >= WindowsKeyManager::BaseDirectInputIndex) {
			//Directinput key
			uint8_t gamepadPort = (key - WindowsKeyManager::BaseDirectInputIndex) / 0x100;
			uint8_t gamepadButton = (key - WindowsKeyManager::BaseDirectInputIndex) % 0x100;
			return _directInput->IsPressed(gamepadPort, gamepadButton);
		} else {
			//XInput key
			uint8_t gamepadPort = (key - WindowsKeyManager::BaseGamepadIndex) / 0x100;
			uint8_t gamepadButton = (key - WindowsKeyManager::BaseGamepadIndex) % 0x100;
			return _xInput->IsPressed(gamepadPort, gamepadButton);
		}
	} else if(key < 0x205) {
		return _keyState[key] != 0;
	}
	return false;
}

optional<int16_t> WindowsKeyManager::GetAxisPosition(uint16_t key)
{
	if(key >= WindowsKeyManager::BaseGamepadIndex) {
		if(!_xInput || !_directInput) {
			return std::nullopt;
		}

		if(key >= WindowsKeyManager::BaseDirectInputIndex) {
			//Directinput key
			uint8_t port = (key - WindowsKeyManager::BaseDirectInputIndex) / 0x100;
			uint8_t button = (key - WindowsKeyManager::BaseDirectInputIndex) % 0x100;
			return _directInput->GetAxisPosition(port, button);
		} else {
			//XInput key
			uint8_t port = (key - WindowsKeyManager::BaseGamepadIndex) / 0x100;
			uint8_t button = (key - WindowsKeyManager::BaseGamepadIndex) % 0x100;
			return _xInput->GetAxisPosition(port, button);
		}
	}
	return std::nullopt;
}

bool WindowsKeyManager::IsMouseButtonPressed(MouseButton button)
{
	return _keyState[WindowsKeyManager::BaseMouseButtonIndex + (int)button];
}

vector<uint16_t> WindowsKeyManager::GetPressedKeys()
{
	vector<uint16_t> result;
	if(!_xInput || !_directInput) {
		return result;
	}

	_xInput->RefreshState();
	for(int i = 0; i < XUSER_MAX_COUNT; i++) {
		for(int j = 1; j <= 26; j++) {
			if(_xInput->IsPressed(i, j)) {
				result.push_back(WindowsKeyManager::BaseGamepadIndex + i * 0x100 + j);
			}
		}
	}

	_directInput->RefreshState();
	for(int i = _directInput->GetJoystickCount() - 1; i >= 0; i--) {
		for(int j = 0; j < 16 + 128; j++) {
			if(_directInput->IsPressed(i, j)) {
				result.push_back(WindowsKeyManager::BaseDirectInputIndex + i * 0x100 + j);
			}
		}
	}

	for(int i = 0; i < 0x205; i++) {
		if(_keyState[i]) {
			result.push_back(i);
		}
	}
	return result;
}

string WindowsKeyManager::GetKeyName(uint16_t keyCode)
{
	auto keyDef = _keyNames.find(keyCode);
	if(keyDef != _keyNames.end()) {
		return keyDef->second;
	}
	return "";
}

uint16_t WindowsKeyManager::GetKeyCode(string keyName)
{
	auto keyDef = _keyCodes.find(keyName);
	if(keyDef != _keyCodes.end()) {
		return keyDef->second;
	}
	return 0;
}

void WindowsKeyManager::UpdateDevices()
{
	if(!_xInput || !_directInput) {
		return;
	}

	_xInput->UpdateDeviceList();
	_directInput->UpdateDeviceList();
}

bool WindowsKeyManager::SetKeyState(uint16_t scanCode, bool state)
{
	if(scanCode < 0x205 && _keyState[scanCode] != state) {
		_keyState[scanCode] = state;
		return true;
	}
	return false;
}

void WindowsKeyManager::SetDisabled(bool disabled)
{
	_disableAllKeys = disabled;
}

void WindowsKeyManager::SetForceFeedback(uint16_t magnitudeRight, uint16_t magnitudeLeft)
{
	_xInput->SetForceFeedback(magnitudeRight, magnitudeLeft);
}

uint32_t WindowsKeyManager::GetConnectedGamepadCount()
{
	if(!_xInput || !_directInput) {
		return 0;
	}
	uint32_t count = 0;
	for(int i = 0; i < XUSER_MAX_COUNT; i++) {
		if(_xInput->IsConnected(i)) {
			count++;
		}
	}
	return count + _directInput->GetJoystickCount();
}

bool WindowsKeyManager::GetGamepadInfo(uint32_t index, GamepadInfo& info)
{
	if(!_xInput || !_directInput) {
		return false;
	}

	int xinputCount = 0;
	for(int i = 0; i < XUSER_MAX_COUNT; i++) {
		if(_xInput->IsConnected(i)) {
			if(xinputCount == (int)index) {
				info.Name = "XInput Pad " + std::to_string(i + 1);
				info.VendorId = 0; //XInput exposes no VID/PID
				info.ProductId = 0;
				info.Slot = (uint32_t)i;
				info.HasRumble = true;
				info.Backend = GamepadBackend::XInput;
				return true;
			}
			xinputCount++;
		}
	}

	int diIndex = (int)index - xinputCount;
	if(diIndex >= 0 && diIndex < _directInput->GetJoystickCount()) {
		info.Name = _directInput->GetName(diIndex);
		info.VendorId = _directInput->GetVendorId(diIndex);
		info.ProductId = _directInput->GetProductId(diIndex);
		info.Slot = (uint32_t)index;
		info.HasRumble = false; //DirectInput force feedback is not implemented
		info.Backend = GamepadBackend::DirectInput;
		return true;
	}
	return false;
}

bool WindowsKeyManager::GetGamepadState(uint32_t index, GamepadState& state)
{
	if(!_xInput || !_directInput) {
		return false;
	}

	int xinputCount = 0;
	int xinputPort = -1;
	for(int i = 0; i < XUSER_MAX_COUNT; i++) {
		if(_xInput->IsConnected(i)) {
			if(xinputCount == (int)index) {
				xinputPort = i;
				break;
			}
			xinputCount++;
		}
	}

	if(xinputPort >= 0) {
		for(int j = 1; j <= 26; j++) {
			if(_xInput->IsPressed(xinputPort, j)) {
				state.Buttons |= (1u << (j - 1));
			}
		}
		//XInput reports Y before X per stick; map to left X/Y, right X/Y
		optional<int16_t> lx = _xInput->GetAxisPosition(xinputPort, 28);
		optional<int16_t> ly = _xInput->GetAxisPosition(xinputPort, 27);
		optional<int16_t> rx = _xInput->GetAxisPosition(xinputPort, 30);
		optional<int16_t> ry = _xInput->GetAxisPosition(xinputPort, 29);
		state.Axes[0] = lx ? *lx : 0;
		state.Axes[1] = ly ? *ly : 0;
		state.Axes[2] = rx ? *rx : 0;
		state.Axes[3] = ry ? *ry : 0;
		return true;
	}

	int diIndex = (int)index - xinputCount;
	if(diIndex >= 0 && diIndex < _directInput->GetJoystickCount()) {
		for(int j = 0; j < 32; j++) {
			if(_directInput->IsPressed(diIndex, j)) {
				state.Buttons |= (1u << j);
			}
		}
		//DirectInput reports Y before X per stick; map to left X/Y, right X/Y
		optional<int16_t> lx = _directInput->GetAxisPosition(diIndex, 128 + 16 + 1);
		optional<int16_t> ly = _directInput->GetAxisPosition(diIndex, 128 + 16 + 0);
		optional<int16_t> rx = _directInput->GetAxisPosition(diIndex, 128 + 16 + 3);
		optional<int16_t> ry = _directInput->GetAxisPosition(diIndex, 128 + 16 + 2);
		state.Axes[0] = lx ? *lx : 0;
		state.Axes[1] = ly ? *ly : 0;
		state.Axes[2] = rx ? *rx : 0;
		state.Axes[3] = ry ? *ry : 0;
		return true;
	}
	return false;
}

void WindowsKeyManager::TestForceFeedback(uint32_t index, uint16_t magnitudeRight, uint16_t magnitudeLeft)
{
	if(!_xInput) {
		return;
	}
	int xinputCount = 0;
	for(int i = 0; i < XUSER_MAX_COUNT; i++) {
		if(_xInput->IsConnected(i)) {
			if(xinputCount == (int)index) {
				_xInput->SetForceFeedback(i, magnitudeRight, magnitudeLeft);
				return;
			}
			xinputCount++;
		}
	}
	//DirectInput pads have no force feedback implemented - nothing to do
}

void WindowsKeyManager::ResetKeyState()
{
	memset(_keyState, 0, sizeof(_keyState));
}
