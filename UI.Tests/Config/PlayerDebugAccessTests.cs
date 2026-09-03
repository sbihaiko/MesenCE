using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	//P.4 (PRD Part B §6): "Debugger ... reachable only after switching to
	//Advanced". The predicate MainMenuViewModel.InitDebugMenu composes over
	//every Debug menu action before DebugShortcutManager registers them, so it
	//governs the menu item and the debugger keyboard shortcut alike.
	public class PlayerDebugAccessTests
	{
		[Fact]
		public void Player_CannotReachDebug()
		{
			Assert.False(PlayerDebugAccess.IsDebugReachable(UiMode.Player));
		}

		[Fact]
		public void Advanced_CanReachDebug()
		{
			Assert.True(PlayerDebugAccess.IsDebugReachable(UiMode.Advanced));
		}

		[Theory]
		//Player: no Debug entry point is enabled, whatever its own condition says
		//(null = the action declared no condition of its own).
		[InlineData(true)]
		[InlineData(false)]
		[InlineData(null)]
		public void Player_DisablesEveryDebugEntryPoint(bool? baseEnabled)
		{
			Assert.False(PlayerDebugAccess.IsDebugEntryEnabled(UiMode.Player, baseEnabled));
		}

		[Theory]
		//Advanced: the gate is a no-op - the action's own condition decides,
		//exactly as before the extraction (a conditionless action stays enabled).
		[InlineData(true, true)]
		[InlineData(false, false)]
		[InlineData(null, true)]
		public void Advanced_KeepsTheActionsOwnCondition(bool? baseEnabled, bool expected)
		{
			Assert.Equal(expected, PlayerDebugAccess.IsDebugEntryEnabled(UiMode.Advanced, baseEnabled));
		}

		[Fact]
		public void SwitchingToAdvanced_RestoresDebugAccess()
		{
			//The "without switching" half of the acceptance clause: the same
			//entry point that is dead in Player comes back in Advanced.
			Assert.False(PlayerDebugAccess.IsDebugEntryEnabled(UiMode.Player, true));
			Assert.True(PlayerDebugAccess.IsDebugEntryEnabled(UiMode.Advanced, true));
		}
	}
}
