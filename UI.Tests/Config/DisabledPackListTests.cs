using System.Collections.Generic;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config
{
	// Fase 2 (docs/roadmap/plano-testes-unitarios.md): coverage for the
	// EnhancementPackConfig.SetPackEnabled list mutation extracted into
	// UI/Logic/DisabledPackList.cs.
	public class DisabledPackListTests
	{
		[Fact]
		public void Set_DisablingNewPack_AddsItOnce()
		{
			List<string> disabledPacks = new();

			DisabledPackList.Set(disabledPacks, "pack1.zip", false);

			string entry = Assert.Single(disabledPacks);
			Assert.Equal("pack1.zip", entry);
		}

		[Fact]
		public void Set_DisablingAlreadyDisabledPack_DoesNotDuplicate()
		{
			List<string> disabledPacks = new() { "pack1.zip" };

			DisabledPackList.Set(disabledPacks, "pack1.zip", false);

			string entry = Assert.Single(disabledPacks);
			Assert.Equal("pack1.zip", entry);
		}

		[Fact]
		public void Set_DisablingWithDifferentCasing_MatchesExistingEntryCaseInsensitively()
		{
			List<string> disabledPacks = new() { "Pack1.ZIP" };

			DisabledPackList.Set(disabledPacks, "pack1.zip", false);

			string entry = Assert.Single(disabledPacks);
			Assert.Equal("pack1.zip", entry);
		}

		[Fact]
		public void Set_ReEnablingDisabledPack_RemovesTheEntry()
		{
			List<string> disabledPacks = new() { "pack1.zip" };

			DisabledPackList.Set(disabledPacks, "pack1.zip", true);

			Assert.Empty(disabledPacks);
		}

		[Fact]
		public void Set_ReEnablingWithDifferentCasing_RemovesTheEntryCaseInsensitively()
		{
			List<string> disabledPacks = new() { "Pack1.ZIP" };

			DisabledPackList.Set(disabledPacks, "pack1.zip", true);

			Assert.Empty(disabledPacks);
		}

		[Fact]
		public void Set_ReEnablingPackNotInList_LeavesListUntouched()
		{
			List<string> disabledPacks = new() { "other.zip" };

			DisabledPackList.Set(disabledPacks, "pack1.zip", true);

			string entry = Assert.Single(disabledPacks);
			Assert.Equal("other.zip", entry);
		}

		[Fact]
		public void Set_DisablingPackAmongOthers_OnlyAffectsMatchingContainer()
		{
			List<string> disabledPacks = new() { "a.zip", "b.zip" };

			DisabledPackList.Set(disabledPacks, "c.zip", false);

			Assert.Equal(3, disabledPacks.Count);
			Assert.Contains("a.zip", disabledPacks);
			Assert.Contains("b.zip", disabledPacks);
			Assert.Contains("c.zip", disabledPacks);
		}
	}
}
