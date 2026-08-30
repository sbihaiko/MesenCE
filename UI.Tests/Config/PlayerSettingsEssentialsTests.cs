using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	//PRD Part B §6: Player mode's Settings page shows only the essentials
	//tabs (video / audio / input) and clamps a non-essentials initial selection
	//(e.g. Preferences from the Advanced GUI path) to Audio, so the window never
	//lands on a hidden tab.
	public class PlayerSettingsEssentialsTests
	{
		[Fact]
		public void Essentials_AreAudioInputVideo()
		{
			Assert.True(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Audio));
			Assert.True(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Input));
			Assert.True(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Video));
		}

		[Fact]
		public void NonEssentials_AreNotEssentials()
		{
			Assert.False(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Emulation));
			Assert.False(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Nes));
			Assert.False(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Gameboy));
			Assert.False(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Sms));
			Assert.False(PlayerSettingsEssentials.IsEssentials(ConfigWindowTab.Preferences));
		}

		[Theory]
		[InlineData(ConfigWindowTab.Audio, ConfigWindowTab.Audio)]
		[InlineData(ConfigWindowTab.Input, ConfigWindowTab.Input)]
		[InlineData(ConfigWindowTab.Video, ConfigWindowTab.Video)]
		[InlineData(ConfigWindowTab.Preferences, ConfigWindowTab.Audio)]
		[InlineData(ConfigWindowTab.Emulation, ConfigWindowTab.Audio)]
		[InlineData(ConfigWindowTab.Nes, ConfigWindowTab.Audio)]
		public void ClampToEssentials_KeepsOrFallsBackToAudio(ConfigWindowTab tab, ConfigWindowTab expected)
		{
			Assert.Equal(expected, PlayerSettingsEssentials.ClampToEssentials(tab));
		}
	}
}
