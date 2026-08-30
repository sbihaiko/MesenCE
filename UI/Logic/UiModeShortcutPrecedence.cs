using System.Collections.Generic;

namespace Mesen.Logic;

//P.4 (PRD Part B §6): the Player-mode shortcut precedence that resolves
//the Esc collision "inside the shortcut config". The core fires every shortcut
//whose combination is pressed - two shortcuts on the identical key are not
//subsets of each other, so both would fire (Esc would pause AND open the
//overlay). In Player mode the overlay shortcut owns its key(s): any non-overlay
//binding on the same signature is suppressed. In Advanced mode nothing is
//filtered - the overlay is inert there (ShortcutHandler ignores its press).
//A signature is the ordered key codes of one KeyCombination; the UI/Config
//layer builds the bindings from PreferencesConfig.ShortcutKeys.
public sealed record ShortcutBinding(bool IsOverlayShortcut, string Signature);

public static class UiModeShortcutPrecedence
{
	//Returns the set of key signatures the overlay owns in the given mode.
	//Player: every non-empty signature the overlay shortcut is bound to.
	//Advanced: empty (no filtering - the overlay is a Player-only surface).
	public static HashSet<string> OverlayOwnedSignatures(UiMode mode, IEnumerable<ShortcutBinding> bindings)
	{
		HashSet<string> owned = new();
		if(mode != UiMode.Player) {
			return owned;
		}

		foreach(ShortcutBinding binding in bindings) {
			if(binding.IsOverlayShortcut && !string.IsNullOrEmpty(binding.Signature)) {
				owned.Add(binding.Signature);
			}
		}
		return owned;
	}
}
