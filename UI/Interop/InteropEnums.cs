namespace Mesen.Interop
{
	//Host-free counterpart to the ConsoleType/CheatType enums that previously
	//lived in EmuApi.cs (Fase 2, docs/roadmap/plano-testes-unitarios.md).
	//EmuApi.cs is Avalonia-tainted (references Avalonia.Media.Imaging), so
	//these two enums were split out into this file so UI/Logic/ helpers (and
	//UI.Tests, via UI.Tests.csproj's dual-compile of this file) can consume
	//ConsoleType/CheatType without pulling in Avalonia or the EmuApi P/Invoke
	//surface. Both stay in the Mesen.Interop namespace and keep their exact
	//member names/values, so every existing consumer of EmuApi.cs continues
	//to compile unchanged.
	public enum ConsoleType
	{
		Snes = 0,
		Gameboy = 1,
		Nes = 2,
		PcEngine = 3,
		Sms = 4,
		Gba = 5,
		Ws = 6,
	}

	public enum CheatType : byte
	{
		NesGameGenie = 0,
		NesProActionRocky,
		NesCustom,
		GbGameGenie,
		GbGameShark,
		SnesGameGenie,
		SnesProActionReplay,
		PceRaw,
		PceAddress,
		SmsProActionReplay,
		SmsGameGenie
	}
}
