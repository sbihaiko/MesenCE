namespace Mesen.Logic;

//The tabs of the ConfigWindow (Settings). Kept host-free in UI/Logic so the
//Player-mode essentials decision (PlayerSettingsEssentials) is unit-testable
//without the Avalonia window. The index comments are part of the contract:
//the ConfigWindow.axaml TabControl order depends on them, and removed systems
//leave holes (never reuse an id).
public enum ConfigWindowTab
{
	Audio = 0,
	Emulation = 1,
	Input = 2,
	Video = 3,
	//separator
	Nes = 5,
	// 6 was Snes — do not reuse
	Gameboy = 7,
	Gba = 8,
	// 9 was PcEngine — do not reuse
	Sms = 10,
	Ws = 11,
	// 12 was OtherConsoles (ColecoVision) — do not reuse
	//separator
	Preferences = 14
}
