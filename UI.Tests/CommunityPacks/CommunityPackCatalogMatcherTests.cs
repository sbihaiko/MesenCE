using System;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for the catalog matcher (F6.4b, ADR-0138 §38/§41): auto-match
	//is an exact No-Intro sha1 (MEP-v1 §4), case-insensitive, then a same-
	//game identity fallback for entries that already carry a sha1. An entry
	//without a sha1 (`rom: {}` - MEI-v1 §2.3) is never auto-matched.
	public class CommunityPackCatalogMatcherTests
	{
		private const string ZeldaDump = "B6643CE5CD43F14915466407FFA1F89C1CDFE76F";
		private const string ZeldaCatalogSha1 = "DAB79C84934F9AA5DB4E7DAD390E5D0C12443FA2";
		private const string ContraSha1 = "979494E7869AC7AB4815FDBD1DC99F893F713FBF";

		private static CommunityPackCatalogEntry Entry(string name, string? sha1, string? kind = "hd-legacy", string? game = null) => new() {
			Name = name,
			Game = game ?? name,
			Kind = kind,
			Rom = new CommunityPackRom { Sha1 = sha1 },
		};

		[Fact]
		public void FindMatchingEntry_ExactSha1_FindsEntry()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] {
					Entry("Other", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"),
					Entry("Contra (USA)", "979494E7869AC7AB4815FDBD1DC99F893F713FBF"),
				},
			};

			CommunityPackCatalogEntry? match = CommunityPackCatalogMatcher.FindMatchingEntry(
				catalog, "979494E7869AC7AB4815FDBD1DC99F893F713FBF");

			Assert.NotNull(match);
			Assert.Equal("Contra (USA)", match!.Name);
		}

		[Fact]
		public void FindMatchingEntry_MatchIsCaseInsensitive()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] { Entry("Contra (USA)", "979494e7869ac7ab4815fdbd1dc99f893f713fbf") },
			};

			Assert.NotNull(CommunityPackCatalogMatcher.FindMatchingEntry(catalog, "979494E7869AC7AB4815FDBD1DC99F893F713FBF"));
		}

		[Fact]
		public void FindMatchingEntry_EntryWithoutSha1_IsNeverMatched()
		{
			//rom: {} - listable/installable, not hash-matchable (MEI-v1 §2.3).
			CommunityPackCatalog catalog = new() {
				Packs = new[] { Entry("Zelda II", null) },
			};

			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(catalog, "979494E7869AC7AB4815FDBD1DC99F893F713FBF"));
		}

		[Fact]
		public void FindMatchingEntry_NoEntryForDump_ReturnsNull()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] { Entry("Contra (USA)", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") },
			};

			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(catalog, "979494E7869AC7AB4815FDBD1DC99F893F713FBF"));
		}

		[Fact]
		public void FindMatchingEntry_EmptyOrNullCatalog_ReturnsNull()
		{
			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(new CommunityPackCatalog(), "979494E7869AC7AB4815FDBD1DC99F893F713FBF"));
			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(null!, "979494E7869AC7AB4815FDBD1DC99F893F713FBF"));
		}

		[Fact]
		public void FindMatchingEntry_AltSha1s_MatchesRevision()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] {
					new CommunityPackCatalogEntry {
						Name = "Castlevania (USA)",
						Kind = "hd-legacy",
						Rom = new CommunityPackRom {
							Sha1 = "EE09B857C90916EDD92A20C463485A610B0A76FD",
							Sha1s = new[] { "3DCB69A8C861C041AEB56C04E39ADF6D332EDA3A" },
						},
					},
				},
			};

			CommunityPackCatalogEntry? match = CommunityPackCatalogMatcher.FindMatchingEntry(
				catalog, "3DCB69A8C861C041AEB56C04E39ADF6D332EDA3A");

			Assert.NotNull(match);
			Assert.Equal("Castlevania (USA)", match!.Name);
		}

		[Fact]
		public void FindMatchingEntry_DifferentDumpSameGame_MatchesWhenEntryHasSha1()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] {
					Entry("The Legend of Zelda (USA) — community submission", ZeldaCatalogSha1,
						game: "The Legend of Zelda (USA)"),
				},
			};

			CommunityPackCatalogEntry? match = CommunityPackCatalogMatcher.FindMatchingEntry(
				catalog, ZeldaDump, "Legend of Zelda, The (USA)");

			Assert.NotNull(match);
			Assert.Equal("The Legend of Zelda (USA)", match!.Game);
			Assert.False(CommunityPackCatalogMatcher.Matches(match.Rom, ZeldaDump));
		}

		[Fact]
		public void FindMatchingEntry_DifferentDumpSameGame_DoesNotMatchEmptyRom()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] { Entry("The Legend of Zelda (USA)", null, game: "The Legend of Zelda (USA)") },
			};

			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(catalog, ZeldaDump, "Legend of Zelda, The (USA)"));
		}

		[Fact]
		public void FindMatchingEntry_SequelDoesNotMatch()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] {
					Entry("The Legend of Zelda (USA)", ZeldaCatalogSha1, game: "The Legend of Zelda (USA)"),
				},
			};

			Assert.Null(CommunityPackCatalogMatcher.FindMatchingEntry(
				catalog, "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Zelda II: The Adventure of Link (USA)"));
		}

		[Fact]
		public void FindMatchingEntry_Sha1WinsOverGameName()
		{
			CommunityPackCatalog catalog = new() {
				Packs = new[] {
					Entry("The Legend of Zelda (USA)", ZeldaCatalogSha1, game: "The Legend of Zelda (USA)"),
					Entry("Contra (USA)", ContraSha1, game: "Contra (USA)"),
				},
			};

			CommunityPackCatalogEntry? match = CommunityPackCatalogMatcher.FindMatchingEntry(
				catalog, ContraSha1, "Legend of Zelda, The (USA)");

			Assert.NotNull(match);
			Assert.Equal("Contra (USA)", match!.Name);
		}

		[Theory]
		[InlineData("Legend of Zelda, The (USA)", "The Legend of Zelda (USA)", true)]
		[InlineData("Castlevania (USA) (Rev A)", "Castlevania (USA)", true)]
		[InlineData("Mega Man (USA)", "Mega Man 2 (USA)", false)]
		[InlineData("Super Mario Bros.", "Super Mario Bros. 3", false)]
		[InlineData("The Legend of Zelda (USA)", "Zelda II: The Adventure of Link (USA)", false)]
		[InlineData("", "The Legend of Zelda (USA)", false)]
		public void SameGame_TokenEquality(string a, string b, bool expected)
		{
			Assert.Equal(expected, CommunityPackCatalogMatcher.SameGame(a, b));
		}
	}
}
