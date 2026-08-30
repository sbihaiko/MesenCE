namespace Mesen.Logic;

//PRD Part B §6: in Player mode the Settings page shows only the
//essentials tabs — video / audio / input — and hides the emulation, per-console
//and preferences tabs (the overlay's "Advanced GUI" button is the escape hatch
//to the full page). This is the host-free decision the ConfigWindow applies:
//the tab bar's IsVisible is bound to the window's PlayerMode flag, and the
//initial tab is clamped here so a non-essentials selection (e.g. Preferences
//from the Advanced GUI path) cannot land on a hidden tab.
public static class PlayerSettingsEssentials
{
	public static bool IsEssentials(ConfigWindowTab tab)
	{
		return tab == ConfigWindowTab.Audio || tab == ConfigWindowTab.Input || tab == ConfigWindowTab.Video;
	}

	public static ConfigWindowTab ClampToEssentials(ConfigWindowTab tab)
	{
		return IsEssentials(tab) ? tab : ConfigWindowTab.Audio;
	}
}
