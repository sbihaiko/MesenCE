using System;
using Mesen.Interop;

namespace Mesen.Logic
{
	//P.7 (PRD Part B §6.1/§6.2): the Player-mode "Enhancements" overlay panel
	//toggles settings that already exist elsewhere (VideoConfig.AspectRatio/
	//VideoFilter, the per-console overclock fields) instead of owning new
	//on/off state - "on" is derived by comparing the current value against a
	//curated preset, so the panel can never drift from what Advanced's own
	//config pages show.
	//
	//Host-free (BCL + the already-dual-compiled Mesen.Interop.ConsoleType, ADR-0123)
	//so UI.Tests exercises this without Avalonia/EmuApi. Deliberately has no
	//dependency on Mesen.Config (VideoAspectRatio/VideoFilterType live there and
	//are NOT part of the UI.Tests dual-compile) - ToggleEnumPreset is generic
	//over any enum, so the caller (UI/ViewModels, full UI project) supplies the
	//concrete Video enum at the call site instead of this file referencing it.
	public static class PlayerEnhancementsToggle
	{
		//Restore-not-clobber (§6.1): turning a toggle on stashes whatever the
		//current value was (unless it already equals the preset, e.g. two
		//toggles flipped on/off/on in a row) so turning it back off restores
		//exactly that - never a hardcoded default. Used for both WideScrn
		//(VideoAspectRatio, preset Widescreen) and HiRes (VideoFilterType,
		//preset HQ4x); both are simple value enums, so one generic function
		//covers both instead of two near-identical copies.
		public static (T NewCurrent, T NewStoredPrior) ToggleEnumPreset<T>(T current, T storedPrior, T preset, bool turningOn) where T : struct, Enum
		{
			if(turningOn) {
				T newPrior = !current.Equals(preset) ? current : storedPrior;
				return (preset, newPrior);
			}
			//Turning off: the toggle is stateless (derived from the current
			//value, not a stored flag) - restoring storedPrior *is* turning off,
			//and the stored value carries forward unchanged for next time.
			return (storedPrior, storedPrior);
		}

		//Overclock (§6.1) has no restore-not-clobber rule in the PRD - it is a
		//plain 0/preset toggle, so a custom value set from Advanced is replaced
		//(not stashed) while the toggle is on.
		//NES: the app's own documented starting point (resources.en.xml
		//lblOverclockHint: "try setting the before NMI value to a few hundred
		//lines (e.g 300+)").
		public const uint NesOverclockBeforeNmi = 300;
		public const uint NesOverclockAfterNmi = 0;
		//GB/GBA: no equivalent in-app guidance exists for OverclockScanlineCount
		//(0-1000 range) - this is a conservative, easily-retuned default.
		public const uint ScanlineOverclockPreset = 40;

		public static bool IsNesOverclockOn(uint beforeNmi, uint afterNmi) => beforeNmi != 0 || afterNmi != 0;

		public static bool IsScanlineOverclockOn(uint scanlineCount) => scanlineCount != 0;

		//SMS has no overclock knob (no OverclockScanlineCount-equivalent field
		//in SmsConfig) - the toggle stays visible but disabled there so the
		//panel layout does not shift per console. Snes/PcEngine/Ws are not
		//product consoles on `main` (docs/roadmap/AGENTS.md) and are excluded
		//the same way.
		public static bool SupportsOverclock(ConsoleType consoleType)
		{
			return consoleType switch {
				ConsoleType.Nes => true,
				ConsoleType.Gameboy => true,
				ConsoleType.Gba => true,
				_ => false
			};
		}

		//§6.2: the Welcome card shows once, on the very first Player-mode boot,
		//and never again once dismissed.
		public static bool ShouldShowWelcomeCard(bool welcomeCardDismissed) => !welcomeCardDismissed;

		//§6.2: the Continue card is not gated on first-run - it is simply what
		//the Player home shows whenever there is a game to resume.
		public static bool ShouldShowContinueCard(bool hasRecentGames) => hasRecentGames;
	}
}
