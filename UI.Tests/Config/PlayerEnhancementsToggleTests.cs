using Mesen.Interop;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	//P.7 (PRD Part B §6.1/§6.2). ToggleEnumPreset is exercised against a local
	//test enum, not the real VideoAspectRatio/VideoFilterType - those live in
	//Mesen.Config (UI/Config/VideoConfig.cs), which is not part of this
	//project's dual-compile (UI.Tests.csproj only pulls in UI/Logic/** and
	//UI/Interop/InteropEnums.cs, ADR-0123). The generic function is agnostic
	//to which enum it operates over, so this still exercises the real logic.
	public enum TestPresetEnum
	{
		Off = 0,
		Custom = 1,
		Preset = 2
	}

	public class PlayerEnhancementsToggleTests
	{
		[Fact]
		public void ToggleOn_FromNonPreset_StashesCurrentAsPrior()
		{
			(TestPresetEnum current, TestPresetEnum prior) = PlayerEnhancementsToggle.ToggleEnumPreset(
				current: TestPresetEnum.Custom, storedPrior: TestPresetEnum.Off, preset: TestPresetEnum.Preset, turningOn: true);
			Assert.Equal(TestPresetEnum.Preset, current);
			Assert.Equal(TestPresetEnum.Custom, prior);
		}

		[Fact]
		public void ToggleOff_RestoresStashedPrior()
		{
			(TestPresetEnum current, TestPresetEnum prior) = PlayerEnhancementsToggle.ToggleEnumPreset(
				current: TestPresetEnum.Preset, storedPrior: TestPresetEnum.Custom, preset: TestPresetEnum.Preset, turningOn: false);
			Assert.Equal(TestPresetEnum.Custom, current);
			Assert.Equal(TestPresetEnum.Custom, prior);
		}

		[Fact]
		public void ToggleOnTwiceInARow_DoesNotOverwritePriorWithPreset()
		{
			//Current already equals the preset (e.g. the user turned it on via
			//Advanced GUI directly, or a second toggle-on with no toggle-off in
			//between) - must not stash the preset itself as "prior", which would
			//make toggling off a no-op.
			(TestPresetEnum current, TestPresetEnum prior) = PlayerEnhancementsToggle.ToggleEnumPreset(
				current: TestPresetEnum.Preset, storedPrior: TestPresetEnum.Custom, preset: TestPresetEnum.Preset, turningOn: true);
			Assert.Equal(TestPresetEnum.Preset, current);
			Assert.Equal(TestPresetEnum.Custom, prior);
		}

		[Fact]
		public void ToggleOnFromOff_NoPriorCustomValue_RestoresOffDefault()
		{
			(TestPresetEnum current, TestPresetEnum prior) = PlayerEnhancementsToggle.ToggleEnumPreset(
				current: TestPresetEnum.Off, storedPrior: TestPresetEnum.Off, preset: TestPresetEnum.Preset, turningOn: true);
			Assert.Equal(TestPresetEnum.Preset, current);
			Assert.Equal(TestPresetEnum.Off, prior);

			(TestPresetEnum current2, TestPresetEnum prior2) = PlayerEnhancementsToggle.ToggleEnumPreset(
				current: current, storedPrior: prior, preset: TestPresetEnum.Preset, turningOn: false);
			Assert.Equal(TestPresetEnum.Off, current2);
			Assert.Equal(TestPresetEnum.Off, prior2);
		}

		[Theory]
		[InlineData(0u, 0u, false)]
		[InlineData(300u, 0u, true)]
		[InlineData(0u, 150u, true)]
		public void IsNesOverclockOn_ChecksEitherField(uint before, uint after, bool expected)
		{
			Assert.Equal(expected, PlayerEnhancementsToggle.IsNesOverclockOn(before, after));
		}

		[Theory]
		[InlineData(0u, false)]
		[InlineData(40u, true)]
		public void IsScanlineOverclockOn_ChecksNonZero(uint count, bool expected)
		{
			Assert.Equal(expected, PlayerEnhancementsToggle.IsScanlineOverclockOn(count));
		}

		[Theory]
		[InlineData(ConsoleType.Nes, true)]
		[InlineData(ConsoleType.Gameboy, true)]
		[InlineData(ConsoleType.Gba, true)]
		[InlineData(ConsoleType.Sms, false)]
		[InlineData(ConsoleType.Snes, false)]
		[InlineData(ConsoleType.PcEngine, false)]
		[InlineData(ConsoleType.Ws, false)]
		public void SupportsOverclock_OnlyNesGameboyGba(ConsoleType consoleType, bool expected)
		{
			Assert.Equal(expected, PlayerEnhancementsToggle.SupportsOverclock(consoleType));
		}

		[Fact]
		public void ShouldShowWelcomeCard_OnlyWhenNotDismissed()
		{
			Assert.True(PlayerEnhancementsToggle.ShouldShowWelcomeCard(welcomeCardDismissed: false));
			Assert.False(PlayerEnhancementsToggle.ShouldShowWelcomeCard(welcomeCardDismissed: true));
		}

		[Fact]
		public void ShouldShowContinueCard_OnlyWhenRecentGamesExist()
		{
			Assert.True(PlayerEnhancementsToggle.ShouldShowContinueCard(hasRecentGames: true));
			Assert.False(PlayerEnhancementsToggle.ShouldShowContinueCard(hasRecentGames: false));
		}
	}
}
