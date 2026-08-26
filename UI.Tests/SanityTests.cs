using Xunit;

namespace Mesen.Tests
{
	// Fase 0 (docs/roadmap/plano-testes-unitarios.md): proves the xunit pipeline
	// runs end to end (restore, compile, discover, execute) with no SDL2,
	// no MesenCore native library, and no Avalonia involved.
	public class SanityTests
	{
		[Fact]
		public void Pipeline_RunsAndAsserts()
		{
			Assert.Equal(4, 2 + 2);
		}
	}
}
