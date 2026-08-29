using Mesen.Logic;
using System.Collections.Generic;
using Xunit;

namespace Mesen.Tests.Config
{
	//P.4 (PRD-player-shell §6): the Player-mode shortcut precedence that
	//resolves the Esc collision in the shortcut config. The core fires every
	//pressed shortcut, so in Player the overlay shortcut must own its key(s) -
	//a Pause (or any other) binding on the same combination is suppressed and
	//Esc only ever opens the overlay. Advanced mode filters nothing (the
	//overlay is inert there, ignored by ShortcutHandler).
	public class UiModeShortcutPrecedenceTests
	{
		private static ShortcutBinding Pause(string sig) => new(false, sig);
		private static ShortcutBinding Overlay(string sig) => new(true, sig);

		[Fact]
		public void Player_SameKeyAsPause_SuppressesPause()
		{
			//Default setup: Pause = Esc, ToggleOverlay = Esc. In Player the
			//overlay owns Esc, so the Pause binding is dropped.
			var bindings = new List<ShortcutBinding> { Pause("Esc"), Overlay("Esc") };
			var owned = UiModeShortcutPrecedence.OverlayOwnedSignatures(UiMode.Player, bindings);
			Assert.Contains("Esc", owned);
		}

		[Fact]
		public void Player_DifferentKeys_KeepsBoth()
		{
			//User bound the overlay to a controller button: Esc keeps meaning
			//Pause, no suppression.
			var bindings = new List<ShortcutBinding> { Pause("Esc"), Overlay("Pad1-X") };
			var owned = UiModeShortcutPrecedence.OverlayOwnedSignatures(UiMode.Player, bindings);
			Assert.DoesNotContain("Esc", owned);
			Assert.Contains("Pad1-X", owned);
		}

		[Fact]
		public void Player_OverlayUnbound_OwnsNothing()
		{
			//No overlay binding at all -> nothing is suppressed.
			var bindings = new List<ShortcutBinding> { Pause("Esc") };
			var owned = UiModeShortcutPrecedence.OverlayOwnedSignatures(UiMode.Player, bindings);
			Assert.Empty(owned);
		}

		[Fact]
		public void Advanced_OwnsNothing()
		{
			//Advanced is the classic GUI: no precedence, Pause/Esc keeps meaning.
			var bindings = new List<ShortcutBinding> { Pause("Esc"), Overlay("Esc") };
			var owned = UiModeShortcutPrecedence.OverlayOwnedSignatures(UiMode.Advanced, bindings);
			Assert.Empty(owned);
		}

		[Fact]
		public void Player_SecondComboSameKey_SuppressedToo()
		{
			//A shortcut with two combos where the second collides with the overlay.
			var bindings = new List<ShortcutBinding> { Pause("Esc"), Pause("Pad1-B"), Overlay("Pad1-B") };
			var owned = UiModeShortcutPrecedence.OverlayOwnedSignatures(UiMode.Player, bindings);
			Assert.Contains("Pad1-B", owned);
		}
	}
}
