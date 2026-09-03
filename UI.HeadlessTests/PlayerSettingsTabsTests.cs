using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Mesen.Logic;
using Mesen.Windows;
using Xunit;

namespace Mesen.HeadlessTests;

//P.4 / PRD Part B §6, plan subsection 2B: "the Player Settings reduced tab set
//rendering". `PlayerSettingsEssentials` (which tab counts as essential) is
//covered host-free in UI.Tests; what is covered here is the step after it -
//that ConfigWindow.axaml's per-tab IsVisible="{Binding !PlayerMode}" really
//leaves exactly the video / audio / input tabs on screen.
public class PlayerSettingsTabsTests
{
	//ConfigWindow.axaml's TabControl, in markup order. The two unnamed separator
	//rows are TabItems too, and are part of what Player mode must hide.
	private const int TabAudio = 0;
	private const int TabEmulation = 1;
	private const int TabInput = 2;
	private const int TabVideo = 3;
	private const int TabSeparator1 = 4;
	private const int TabNes = 5;
	private const int TabGameboy = 6;
	private const int TabGba = 7;
	private const int TabSms = 8;
	private const int TabSeparator2 = 9;
	private const int TabPreferences = 10;

	private static readonly int[] EssentialTabs = { TabAudio, TabInput, TabVideo };
	private static readonly int[] AdvancedOnlyTabs = { TabEmulation, TabSeparator1, TabNes, TabGameboy, TabGba, TabSms, TabSeparator2, TabPreferences };

	private static List<TabItem> ShowSettings(bool playerMode)
	{
		//Input is the one essentials tab whose view-model does not reach the
		//native core on construction (Audio enumerates devices through
		//ConfigApi, Video reads the core's filter list), so it is the tab a
		//host-free run can open. The tab bar under test is the same either way.
		ConfigWindow window = new(ConfigWindowTab.Input, playerMode);
		window.Show();
		TabControl tabs = window.FindAll<TabControl>().First();
		return tabs.Items.Cast<TabItem>().ToList();
	}

	[AvaloniaFact]
	public void Player_settings_shows_only_the_essentials_tabs()
	{
		List<TabItem> tabs = ShowSettings(playerMode: true);

		Assert.Equal(11, tabs.Count);
		foreach(int index in EssentialTabs) {
			Assert.True(tabs[index].IsOnScreen(), $"Tab {index} must stay visible in Player mode.");
		}
		foreach(int index in AdvancedOnlyTabs) {
			Assert.False(tabs[index].IsOnScreen(), $"Tab {index} must be hidden in Player mode.");
		}
		//The rule itself, applied by the window: Player never lands on a hidden tab.
		Assert.True(PlayerSettingsEssentials.IsEssentials((ConfigWindowTab)tabs.FindIndex(t => t.IsSelected)));
	}

	[AvaloniaFact]
	public void Advanced_settings_still_shows_every_tab()
	{
		//Guards against the reduction being unconditional rather than bound to
		//PlayerMode - the failure mode a grep of the markup cannot tell apart.
		List<TabItem> tabs = ShowSettings(playerMode: false);

		Assert.Equal(11, tabs.Count);
		Assert.All(tabs, tab => Assert.True(tab.IsOnScreen()));
	}
}
