#pragma once
#include "pch.h"
#include "Shared/SettingTypes.h"
#include "Shared/Interfaces/IKeyManager.h"
#include <functional>

//P.4: the pure half of ShortcutKeyHandler's "a keyboard is plugged into the
//console, so keyboard shortcuts are dead keys" rule. Extracted so it can be
//asserted directly by scripts/core_unit_tests.cpp without linking the handler
//(which owns a thread, Emulator, KeyManager and SystemActionManager) - same
//extraction pattern ADR-0142's wave-1 work used, and the one UI/Logic uses on
//the C# side. ShortcutKeyHandler::IsKeyPressed is the only production caller;
//it supplies the "is this host key down right now" probe.
namespace ShortcutKeyRules
{
	//True when every keyboard key must read as "not pressed" for `shortcut`.
	//Pause is always exempt (it is how the player pauses to reach the other
	//shortcuts) and ToggleOverlay is exempt too: in Player mode the overlay is
	//the primary way to pause, so it must stay reachable inside a keyboard
	//game. The UI ignores ToggleOverlay while UiMode == Advanced, so the
	//exemption has no effect outside Player.
	inline bool ShouldBlockKeyboardKeys(EmulatorShortcut shortcut, bool isKeyboardConnected, bool isPaused)
	{
		if(shortcut == EmulatorShortcut::Pause || shortcut == EmulatorShortcut::ToggleOverlay) {
			return false;
		}
		return isKeyboardConnected && !isPaused;
	}

	//The host key probe: keyCode -> is it down. Mouse buttons and pad inputs
	//sit at or above IKeyManager::BaseMouseButtonIndex.
	typedef std::function<bool(uint16_t keyCode)> KeyDownProbe;

	inline bool IsKeyPressed(uint16_t keyCode, bool mergeCtrlAltShift, bool blockKeyboardKeys, const KeyDownProbe& isKeyDown)
	{
		if(blockKeyboardKeys && keyCode < IKeyManager::BaseMouseButtonIndex) {
			return false;
		}

		if(keyCode >= 116 && keyCode <= 121 && mergeCtrlAltShift) {
			//Left/right ctrl/alt/shift
			//Return true if either the left or right key is pressed
			return isKeyDown(keyCode | 1) || isKeyDown(keyCode & ~0x01);
		}

		return isKeyDown(keyCode);
	}

	//`anyKeyDown` is the handler's "_pressedKeys is not empty" guard: with no
	//key down at all nothing can match.
	inline bool IsCombinationPressed(KeyCombination comb, bool blockKeyboardKeys, bool anyKeyDown, const KeyDownProbe& isKeyDown)
	{
		int keyCount = (comb.Key1 ? 1 : 0) + (comb.Key2 ? 1 : 0) + (comb.Key3 ? 1 : 0);

		if(keyCount == 0 || !anyKeyDown) {
			return false;
		}

		bool mergeCtrlAltShift = keyCount > 1;

		return IsKeyPressed(comb.Key1, mergeCtrlAltShift, blockKeyboardKeys, isKeyDown) &&
			(comb.Key2 == 0 || IsKeyPressed(comb.Key2, mergeCtrlAltShift, blockKeyboardKeys, isKeyDown)) &&
			(comb.Key3 == 0 || IsKeyPressed(comb.Key3, mergeCtrlAltShift, blockKeyboardKeys, isKeyDown));
	}

	//The whole decision for one shortcut: a pressed superset shadows its
	//subset, otherwise the shortcut's own combination decides.
	inline bool IsShortcutPressed(EmulatorShortcut shortcut, KeyCombination comb, const vector<KeyCombination>& supersets,
		bool isKeyboardConnected, bool isPaused, bool anyKeyDown, const KeyDownProbe& isKeyDown)
	{
		bool blockKeyboardKeys = ShouldBlockKeyboardKeys(shortcut, isKeyboardConnected, isPaused);

		for(const KeyCombination& superset : supersets) {
			if(IsCombinationPressed(superset, blockKeyboardKeys, anyKeyDown, isKeyDown)) {
				//A superset is pressed, ignore this subset
				return false;
			}
		}

		//No supersets are pressed, check if all matching keys are pressed
		return IsCombinationPressed(comb, blockKeyboardKeys, anyKeyDown, isKeyDown);
	}
}
