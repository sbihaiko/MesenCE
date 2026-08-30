using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	//P.4 (PRD Part B §6): the one-shot default for PreferencesConfig.UiMode.
	//The rule only runs while the key is absent from the settings file - once
	//saved, the stored value wins. No settings.json (fresh unzip, the
	//Configuration.CreateConfig path) starts in Player; an existing settings.json
	//without the UiMode key (a pre-Player upgrade) keeps Advanced so a current
	//Mesen user is not stripped of Debug. The key is always written on first save.
	public class UiModeDefaultRuleTests
	{
		[Fact]
		public void MissingKey_NoSettingsFile_IsPlayer()
		{
			//Fresh unzip: no settings.json at startup -> Player chrome.
			Assert.Equal(UiMode.Player, UiModeDefaultRule.ForMissingKey(settingsFileExists: false));
		}

		[Fact]
		public void MissingKey_ExistingSettingsFile_IsAdvanced()
		{
			//Upgrade: existing settings.json without the UiMode key -> keep Advanced.
			Assert.Equal(UiMode.Advanced, UiModeDefaultRule.ForMissingKey(settingsFileExists: true));
		}

		[Fact]
		public void EnumZero_IsAdvanced()
		{
			//The property initializer (PreferencesConfig.UiMode = UiMode.Advanced)
			//is what an existing keyless file deserializes to; the zero value must
			//stay the upgrade-safe default so a missing key never degrades to Player.
			Assert.Equal(UiMode.Advanced, (UiMode)0);
		}
	}
}
