using System;
using Mesen.Interop;

namespace Mesen.Logic
{
	//Host-free counterpart to CheatListWindowViewModel.GetCheatType (Fase 2,
	//docs/roadmap/plano-testes-unitarios.md). Given the code text imported
	//from the cheat database, guesses the CheatType from its punctuation:
	//Snes codes containing "-" are GameGenie, everything else ProActionReplay;
	//Nes codes containing ":" are the custom (raw address/value) format,
	//everything else GameGenie. Any other ConsoleType throws
	//NotSupportedException naming the console, matching the behavior being
	//replaced but with a type/message the UI can surface (ADR-0128-b) - this
	//includes ConsoleType.Gameboy, which is a documented pre-existing gap
	//(CheatType has GbGameGenie/GbGameShark members, but no console branch
	//produces them) and is not "fixed" here. The parity tests use
	//Assert.ThrowsAny<Exception>, so the exception type is not part of the
	//tested contract. Kept free of Avalonia/EmuApi so it can be dual-compiled
	//into UI.Tests (see UI.Tests/UI.Tests.csproj) and unit tested without the
	//native MesenCore library.
	public static class CheatTypeDetector
	{
		public static CheatType FromCode(ConsoleType consoleType, string code)
		{
			switch(consoleType) {
				case ConsoleType.Snes:
					return code.Contains("-") ? CheatType.SnesGameGenie : CheatType.SnesProActionReplay;

				case ConsoleType.Nes:
					return code.Contains(":") ? CheatType.NesCustom : CheatType.NesGameGenie;

				default:
					throw new NotSupportedException("Unsupported cheat type: " + consoleType);
			}
		}
	}
}
