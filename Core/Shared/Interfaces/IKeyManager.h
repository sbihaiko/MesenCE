#pragma once
#include "pch.h"

enum class MouseButton
{
	LeftButton = 0,
	RightButton = 1,
	MiddleButton = 2,
	Button4 = 3,
	Button5 = 4
};

struct MousePosition
{
	int16_t X;
	int16_t Y;
	double RelativeX;
	double RelativeY;
};

struct MouseMovement
{
	int16_t dx;
	int16_t dy;
};

enum class GamepadBackend : uint8_t
{
	None = 0,
	XInput = 1,
	DirectInput = 2,
	Evdev = 3,
	GameController = 4
};

//Host input tester (PRD slice I.0): one connected pad as the host OS sees it,
//independent of the emulated PadN mapping - name, which input backend it came
//through, its slot, VID/PID (0 when the backend does not expose them) and
//whether it can rumble.
struct GamepadInfo
{
	std::string Name;
	uint32_t VendorId = 0;
	uint32_t ProductId = 0;
	uint32_t Slot = 0;
	bool HasRumble = false;
	GamepadBackend Backend = GamepadBackend::None;
};

//Host input tester (PRD slice I.0): the pad's raw state - a bitmask of its
//pressed buttons (bit i = button i, same numbering as the PadN key space) and
//its analog axes (raw int16, centered at 0: left X/Y then right X/Y).
struct GamepadState
{
	uint32_t Buttons = 0;
	int16_t Axes[4] = {};
};

class IKeyManager
{
public:
	static constexpr int BaseMouseButtonIndex = 0x200;
	static constexpr int BaseGamepadIndex = 0x1000;

	virtual ~IKeyManager() {}

	virtual void RefreshState() = 0;
	virtual void UpdateDevices() = 0;
	virtual bool IsMouseButtonPressed(MouseButton button) = 0;
	virtual bool IsKeyPressed(uint16_t keyCode) = 0;
	virtual optional<int16_t> GetAxisPosition(uint16_t keyCode) { return std::nullopt; }
	virtual vector<uint16_t> GetPressedKeys() = 0;
	virtual string GetKeyName(uint16_t keyCode) = 0;
	virtual uint16_t GetKeyCode(string keyName) = 0;

	virtual bool SetKeyState(uint16_t scanCode, bool state) = 0;
	virtual void ResetKeyState() = 0;
	virtual void SetDisabled(bool disabled) = 0;

	virtual void SetForceFeedback(uint16_t magnitudeRight, uint16_t magnitudeLeft) {}

	//Host input tester (PRD slice I.0). Defaults are no-ops so a platform that
	//has not implemented the tester still builds; the Input tester tab only
	//lists pads the active backend actually reports.
	virtual uint32_t GetConnectedGamepadCount() { return 0; }
	virtual bool GetGamepadInfo(uint32_t index, GamepadInfo& info) { return false; }
	virtual bool GetGamepadState(uint32_t index, GamepadState& state) { return false; }
	virtual void TestForceFeedback(uint32_t index, uint16_t magnitudeRight, uint16_t magnitudeLeft) {}
};