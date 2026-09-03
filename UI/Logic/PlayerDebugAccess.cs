namespace Mesen.Logic;

//PRD Part B §6 (P.4): "Debugger, HD Pack Builder, Lua, netplay, movies,
//cheats, Record Music -> not in the overlay; reachable only after switching to
//Advanced". This is the host-free half of that rule for the Debug menu: the
//single predicate that says whether a Debug entry point may act in the current
//UiMode.
//
//Stateful partner (ADR-0127): MainMenuViewModel.InitDebugMenu owns the
//impure half - it reads ConfigManager.Config.Preferences.UiMode, composes this
//predicate over each Debug action's own IsEnabled condition, and hands the
//resulting list to DebugShortcutManager.RegisterActions. That registration is
//why the gate covers both ways into the debugger: the menu item (greyed out,
//and in Player the whole menu bar is hidden by PlayerChrome.IsMenuVisible
//anyway) and the debugger's registered keyboard shortcut, which
//DebugShortcutManager only fires when the action's IsEnabled returns true.
//This class never touches config or Avalonia itself.
public static class PlayerDebugAccess
{
	//Player has no Debug surface at all; Advanced is the classic GUI where
	//every Debug entry point behaves exactly as before.
	public static bool IsDebugReachable(UiMode uiMode)
	{
		return uiMode != UiMode.Player;
	}

	//Composed enablement of one Debug entry point: the mode gate AND the
	//action's own condition (IsGameRunning, console-specific checks, ...).
	//baseEnabled is null when the action declared no condition of its own,
	//which BaseMenuAction treats as "enabled".
	public static bool IsDebugEntryEnabled(UiMode uiMode, bool? baseEnabled)
	{
		return IsDebugReachable(uiMode) && (baseEnabled ?? true);
	}
}
