using System;
using Mesen.Interop;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Cheats
{
	// Fase 2 (docs/roadmap/plano-testes-unitarios.md): coverage for the
	// CheatListWindowViewModel.GetCheatType branching extracted into
	// UI/Logic/CheatTypeDetector.cs.
	public class CheatTypeDetectorTests
	{
		[Fact]
		public void FromCode_NesCodeWithoutColon_ReturnsNesGameGenie()
		{
			CheatType result = CheatTypeDetector.FromCode(ConsoleType.Nes, "SXIOPO");

			Assert.Equal(CheatType.NesGameGenie, result);
		}

		[Fact]
		public void FromCode_NesCodeWithColon_ReturnsNesCustom()
		{
			CheatType result = CheatTypeDetector.FromCode(ConsoleType.Nes, "0018:AD");

			Assert.Equal(CheatType.NesCustom, result);
		}

		[Fact]
		public void FromCode_SnesCodeWithDash_ReturnsSnesGameGenie()
		{
			CheatType result = CheatTypeDetector.FromCode(ConsoleType.Snes, "DD62-3435");

			Assert.Equal(CheatType.SnesGameGenie, result);
		}

		[Fact]
		public void FromCode_SnesCodeWithoutDash_ReturnsSnesProActionReplay()
		{
			CheatType result = CheatTypeDetector.FromCode(ConsoleType.Snes, "7E000E63");

			Assert.Equal(CheatType.SnesProActionReplay, result);
		}

		[Fact]
		public void FromCode_UnsupportedConsole_Gameboy_Throws()
		{
			// CheatType declares GbGameGenie/GbGameShark members, but no
			// console branch produces them (documented pre-existing gap,
			// not changed in this phase) - Gameboy throws like any other
			// unhandled console.
			Assert.ThrowsAny<Exception>(() => CheatTypeDetector.FromCode(ConsoleType.Gameboy, "01XX-XXX"));
		}

		[Theory]
		[InlineData(ConsoleType.PcEngine)]
		[InlineData(ConsoleType.Sms)]
		[InlineData(ConsoleType.Gba)]
		[InlineData(ConsoleType.Ws)]
		public void FromCode_OtherUnsupportedConsoles_Throw(ConsoleType consoleType)
		{
			Assert.ThrowsAny<Exception>(() => CheatTypeDetector.FromCode(consoleType, "0000-0000"));
		}
	}
}
