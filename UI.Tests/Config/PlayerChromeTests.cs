using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	//P.7 (PRD Part B §6): the menu-bar visibility rule shared by the
	//MainWindowViewModel initializer and MouseManager.UpdateMainMenuVisibility().
	public class PlayerChromeTests
	{
		[Theory]
		//Player ignores every other input - the menu bar does not exist there.
		[InlineData(false, false, false, false)]
		[InlineData(true, true, true, true)]
		[InlineData(false, true, false, true)]
		[InlineData(true, false, true, false)]
		public void Player_AlwaysHidesMenu(bool exclusiveFullscreen, bool autoHide, bool menuOpen, bool cursorInBand)
		{
			Assert.False(PlayerChrome.IsMenuVisible(UiMode.Player, exclusiveFullscreen, autoHide, menuOpen, cursorInBand));
		}

		[Fact]
		public void Advanced_ExclusiveFullscreen_HidesMenuEvenWhenOpenOrHovered()
		{
			Assert.False(PlayerChrome.IsMenuVisible(UiMode.Advanced, true, false, false, false));
			Assert.False(PlayerChrome.IsMenuVisible(UiMode.Advanced, true, true, true, true));
			Assert.False(PlayerChrome.IsMenuVisible(UiMode.Advanced, true, false, true, true));
		}

		[Fact]
		public void Advanced_WithoutAutoHide_AlwaysShowsMenu()
		{
			Assert.True(PlayerChrome.IsMenuVisible(UiMode.Advanced, false, false, false, false));
			Assert.True(PlayerChrome.IsMenuVisible(UiMode.Advanced, false, false, true, false));
			Assert.True(PlayerChrome.IsMenuVisible(UiMode.Advanced, false, false, false, true));
		}

		[Theory]
		//autoHide on: the bar shows only while the menu is open or the cursor
		//is inside the top hover band.
		[InlineData(false, false, false)]
		[InlineData(true, false, true)]
		[InlineData(false, true, true)]
		[InlineData(true, true, true)]
		public void Advanced_WithAutoHide_FollowsMenuOpenOrHover(bool menuOpen, bool cursorInBand, bool expected)
		{
			Assert.Equal(expected, PlayerChrome.IsMenuVisible(UiMode.Advanced, false, true, menuOpen, cursorInBand));
		}

		[Fact]
		public void InitializerInputs_MatchHistoricalRule()
		{
			//MainWindowViewModel's initializer passes false for the window/cursor
			//state, which must reduce to "UiMode != Player && !AutoHideMenu".
			foreach(UiMode mode in new[] { UiMode.Advanced, UiMode.Player }) {
				foreach(bool autoHide in new[] { false, true }) {
					bool expected = mode != UiMode.Player && !autoHide;
					Assert.Equal(expected, PlayerChrome.IsMenuVisible(mode, false, autoHide, false, false));
				}
			}
		}

		[Fact]
		public void CursorBand_CoversTopStripOfWindow()
		{
			//Window at (100, 200), 640 wide, 20px menu, scale 1: the band runs
			//from y = 185 (15px above the window) to y = 235 (max(20+10, 35)).
			Assert.True(PlayerChrome.IsCursorInMenuBand(400, 200, 100, 200, 640, 20, 1));
			Assert.True(PlayerChrome.IsCursorInMenuBand(100, 185, 100, 200, 640, 20, 1));
			Assert.True(PlayerChrome.IsCursorInMenuBand(740, 230, 100, 200, 640, 20, 1));

			//Above the band, below the band, left of it, right of it.
			Assert.False(PlayerChrome.IsCursorInMenuBand(400, 184, 100, 200, 640, 20, 1));
			Assert.False(PlayerChrome.IsCursorInMenuBand(400, 236, 100, 200, 640, 20, 1));
			Assert.False(PlayerChrome.IsCursorInMenuBand(99, 200, 100, 200, 640, 20, 1));
			Assert.False(PlayerChrome.IsCursorInMenuBand(741, 200, 100, 200, 640, 20, 1));
		}

		[Fact]
		public void CursorBand_ScalesWidthAndHeight()
		{
			//scale 2 doubles the menu height (2*20+10 = 50 > 35*2 = 70 -> 70) and
			//the window width used for the horizontal extent.
			Assert.True(PlayerChrome.IsCursorInMenuBand(1379, 270, 100, 200, 640, 20, 2));
			Assert.False(PlayerChrome.IsCursorInMenuBand(1381, 270, 100, 200, 640, 20, 2));
			Assert.False(PlayerChrome.IsCursorInMenuBand(400, 271, 100, 200, 640, 20, 2));
		}
	}
}
