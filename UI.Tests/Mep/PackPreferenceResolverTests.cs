using Mesen.Logic;
using System.Collections.Generic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//P.3 (PRD Part B §5, ADR-0140/0141): coverage for the host-free
	//per-ROM preference resolver (UI/Logic/PackPreferenceResolver.cs) -
	//`local:<container>` fallback, content_id merge (a container duplicating
	//another's content_id is not a new entry), and the lexicographic default
	//when there is no (or a stale) preference.
	public class PackPreferenceResolverTests
	{
		private static PackPreferenceResolver.Candidate Local(string container) => new() { Container = container };

		private static PackPreferenceResolver.Candidate Stamped(string container, string packId, string contentId) => new() {
			Container = container,
			PackId = packId,
			ContentId = contentId
		};

		[Fact]
		public void Resolve_LocalPreference_PicksTheChosenContainer()
		{
			//Two local (stamp-less) packs for one ROM; the user picked B.
			var candidates = new List<PackPreferenceResolver.Candidate> { Local("a"), Local("b") };

			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, "local:b");

			Assert.Equal("b", resolution.PreferredContainer);
		}

		[Fact]
		public void Resolve_OtherLocalPreference_PicksThatContainer()
		{
			var candidates = new List<PackPreferenceResolver.Candidate> { Local("a"), Local("b") };

			Assert.Equal("a", PackPreferenceResolver.Resolve(candidates, "local:a").PreferredContainer);
		}

		[Fact]
		public void Resolve_NoPreference_KeepsLexicographicDefault()
		{
			var candidates = new List<PackPreferenceResolver.Candidate> { Local("a"), Local("b") };

			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, null);

			Assert.Null(resolution.PreferredContainer);
			Assert.Equal(2, resolution.Candidates.Count);
		}

		[Fact]
		public void Resolve_StalePreference_KeepsLexicographicDefault()
		{
			//The preferred container is gone (removed); no override may apply.
			var candidates = new List<PackPreferenceResolver.Candidate> { Local("a") };

			Assert.Null(PackPreferenceResolver.Resolve(candidates, "local:gone").PreferredContainer);
		}

		[Fact]
		public void Resolve_CatalogPackIdPreference_MatchesStampPackId()
		{
			//A catalog-installed pack carries its pack_id in .mep-install.json;
			//the preference is stored as that pack_id (case-insensitive).
			var candidates = new List<PackPreferenceResolver.Candidate> {
				Stamped("contra-a", "contra80s", "abc"),
				Stamped("contra-b", "another-contra", "def")
			};

			Assert.Equal("contra-b", PackPreferenceResolver.Resolve(candidates, "ANOTHER-CONTRA").PreferredContainer);
		}

		[Fact]
		public void Resolve_ThirdContainerWithSameContentId_IsNotANewEntry()
		{
			//Acceptance: a third container whose content_id equals the chosen
			//pack's is the same pack, not a second choice (PRD §5).
			var candidates = new List<PackPreferenceResolver.Candidate> {
				Local("a"),
				Stamped("b", "pack-b", "abc123"),
				Stamped("c", "pack-c", "abc123") //byte-duplicate of b
			};

			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, "pack-b");

			Assert.Equal(2, resolution.Candidates.Count); //a + the merged b/c
			Assert.Equal("b", resolution.PreferredContainer);
		}

		[Fact]
		public void Resolve_SameContentId_NotPreferredDuplicateKeepsFirst()
		{
			var candidates = new List<PackPreferenceResolver.Candidate> {
				Stamped("a", "pack-a", "abc"),
				Stamped("b", "pack-b", "abc")
			};

			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, "pack-a");

			Assert.Single(resolution.Candidates); //b merged away
			Assert.Equal("a", resolution.Candidates[0].Container);
			Assert.Equal("a", resolution.PreferredContainer);
		}

		[Fact]
		public void Resolve_SameContentId_PreferenceOnLaterDuplicateWins()
		{
			var candidates = new List<PackPreferenceResolver.Candidate> {
				Stamped("a", "pack-a", "abc"),
				Stamped("b", "pack-b", "abc")
			};

			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, "pack-b");

			Assert.Single(resolution.Candidates);
			Assert.Equal("b", resolution.Candidates[0].Container); //the chosen one survives
			Assert.Equal("b", resolution.PreferredContainer);
		}

		[Fact]
		public void Resolve_DisabledPreferredPack_IsNotChosen()
		{
			var candidates = new List<PackPreferenceResolver.Candidate> {
				Local("a"),
				new() { Container = "b", Enabled = false }
			};

			Assert.Null(PackPreferenceResolver.Resolve(candidates, "local:b").PreferredContainer);
		}

		[Fact]
		public void DerivePackId_Stamped_UsesStampPackId()
		{
			Assert.Equal("contra80s", PackPreferenceResolver.DerivePackId(Stamped("x", "Contra80s", "abc")));
		}

		[Fact]
		public void DerivePackId_LocalContainer_UsesLocalPrefix()
		{
			Assert.Equal("local:my-pack", PackPreferenceResolver.DerivePackId(Local("My-Pack")));
		}
	}
}
