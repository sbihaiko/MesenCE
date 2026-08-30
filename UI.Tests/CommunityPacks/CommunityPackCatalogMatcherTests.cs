using System;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for the catalog matcher (F6.4b, ADR-0138 §38/§41): auto-match
	//is an exact No-Intro sha1 (MEP-v1 §4), case-insensitive; an entry without
	//a sha1 (`rom: {}` - MEI-v1 §2.3) is never hash-matched, so a bare "no
	//match" is precisely "no entry carries this dump's hash".
	public class CommunityPackCatalogMatcherTests
	{
		private static CommunityPackCatalogEntry Entry(string name, string? sha1, string? kind = "hd-legacy") => new() {
			Name = name,
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
	}
}
