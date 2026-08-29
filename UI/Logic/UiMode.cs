namespace Mesen.Logic;

//PRD-player-shell §6 (P.4): the one-shot default for PreferencesConfig.UiMode.
//Consulted only while the key is absent from the settings file - once the key
//is written (first save), the stored value wins and this rule never runs
//again. An existing settings.json is an upgrade from a pre-Player build and
//keeps Advanced, so a current Mesen user is not stripped of Debug; no settings
//file is a fresh unzip and starts in Player. Player hides the chrome and
//routes a small overlay; Advanced is the classic menu/IDE GUI.
public enum UiMode
{
	//Zero value is the upgrade-safe default (existing settings.json without
	//the UiMode key, see PreferencesConfig.UiMode's initializer).
	Advanced,
	Player
}

public static class UiModeDefaultRule
{
	//settingsFileExists mirrors "was there a settings.json at startup?"
	//- false is the fresh-unzip path (CreateConfig), true is the upgrade path
	//(existing file whose key is missing, which lands on the initializer value).
	public static UiMode ForMissingKey(bool settingsFileExists)
	{
		return settingsFileExists ? UiMode.Advanced : UiMode.Player;
	}
}
