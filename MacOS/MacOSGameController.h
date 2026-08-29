#pragma once

#import <Foundation/Foundation.h>
#import <Cocoa/Cocoa.h>
#import <GameController/GameController.h>
#import <CoreHaptics/CoreHaptics.h>

#include <optional>

class Emulator;

class MacOSGameController
{
private:
	Emulator* _emu;

	GCController* _controller;
	GCExtendedGamepad* _input;
	CHHapticEngine* _haptics;
	id<CHHapticPatternPlayer> _player;

	bool _buttonState[24] = {};
	int16_t _axisState[4] = {};

	void HandleDpad(GCControllerDirectionPad* dpad);
	void HandleThumbstick(GCControllerDirectionPad* stick, int stickNumber);

public:
	MacOSGameController(Emulator* emu, GCController* controller);
	~MacOSGameController();

	bool IsGameController(GCController* controller);

	bool IsButtonPressed(int buttonNumber);
	std::optional<int16_t> GetAxisPosition(int axis);

	void SetForceFeedback(uint16_t magnitudeRight, uint16_t magnitudeLeft);

	//Host input tester (PRD slice I.0): the controller's product name as the
	//GameController framework reports it, and whether a haptic engine is
	//available for force feedback.
	std::string GetName();
	bool HasRumble();
};
