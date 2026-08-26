using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Mep
{
	// Fase 1 (docs/roadmap/plano-testes-unitarios.md): coverage for the
	// EmuApi.GetMepPackList() TSV parser extracted into UI/Logic/MepPackListParser.cs.
	public class MepPackListParserTests
	{
		private const string ValidSiblingLine =
			"pack1.zip\tMy Pack\t1.0\tSome Author\tMIT\tgfx,audio\t1\t2";

		[Fact]
		public void Parse_ValidRow_MapsAllEightColumns()
		{
			MepPackListResult result = MepPackListParser.Parse(ValidSiblingLine);

			Assert.True(result.HasPacks);
			MepPackListEntry entry = Assert.Single(result.Packs);
			Assert.Equal("pack1.zip", entry.Container);
			Assert.Equal("My Pack", entry.Name);
			Assert.Equal("1.0", entry.Version);
			Assert.Equal("Some Author", entry.Author);
			Assert.Equal("MIT", entry.License);
			Assert.Equal("gfx,audio", entry.Sections);
			Assert.True(entry.Enabled);
			Assert.Equal("sibling", entry.Source);
		}

		[Fact]
		public void Parse_MultipleValidRows_PreservesOrder()
		{
			string input =
				"a.zip\tA\t1\tAu\tLic\tS\t1\t0\n" +
				"b.zip\tB\t2\tAu\tLic\tS\t0\t1\n" +
				"c.zip\tC\t3\tAu\tLic\tS\t1\t2";

			MepPackListResult result = MepPackListParser.Parse(input);

			Assert.Equal(3, result.Packs.Count);
			Assert.Equal("a.zip", result.Packs[0].Container);
			Assert.Equal("b.zip", result.Packs[1].Container);
			Assert.Equal("c.zip", result.Packs[2].Container);
		}

		[Fact]
		public void Parse_DisabledColumn_SetsEnabledFalse()
		{
			string input = "pack.zip\tName\t1\tAu\tLic\tS\t0\t0";

			MepPackListEntry entry = Assert.Single(MepPackListParser.Parse(input).Packs);

			Assert.False(entry.Enabled);
		}

		[Fact]
		public void Parse_SectionsColumn_IsPassedThroughRaw()
		{
			// The ","->", " display formatting is the caller's (VM) job, not
			// the parser's — the raw field must survive untouched here.
			string input = "pack.zip\tName\t1\tAu\tLic\tgfx,audio,music\t1\t0";

			MepPackListEntry entry = Assert.Single(MepPackListParser.Parse(input).Packs);

			Assert.Equal("gfx,audio,music", entry.Sections);
		}

		[Fact]
		public void Parse_RejectedLine_IsStrippedOfBangAndExcludedFromPacks()
		{
			string input = "!some-bad-pack.zip: missing pack.json\n" + ValidSiblingLine;

			MepPackListResult result = MepPackListParser.Parse(input);

			Assert.Single(result.Packs);
			Assert.True(result.HasRejected);
			Assert.Equal("some-bad-pack.zip: missing pack.json", result.RejectedInfo);
		}

		[Fact]
		public void Parse_MultipleRejectedLines_AreJoinedAndTrimmed()
		{
			string input = "!first bad\n!second bad\n";

			MepPackListResult result = MepPackListParser.Parse(input);

			Assert.Empty(result.Packs);
			Assert.False(result.HasPacks);
			Assert.Equal("first bad" + System.Environment.NewLine + "second bad", result.RejectedInfo);
		}

		[Theory]
		[InlineData("pack.zip\tName\t1\tAu\tLic\tS\t1")] // 7 columns
		[InlineData("pack.zip\tName")] // 2 columns
		[InlineData("")] // empty, dropped by RemoveEmptyEntries before Split('\t') even runs
		public void Parse_ShortRow_IsIgnoredNotThrown(string shortLine)
		{
			MepPackListResult result = MepPackListParser.Parse(shortLine + "\n" + ValidSiblingLine);

			Assert.Single(result.Packs);
			Assert.Equal("pack1.zip", result.Packs[0].Container);
		}

		[Fact]
		public void Parse_EmptyInput_ReturnsEmptyResult()
		{
			MepPackListResult result = MepPackListParser.Parse("");

			Assert.False(result.HasPacks);
			Assert.False(result.HasRejected);
			Assert.Empty(result.Packs);
			Assert.Equal("", result.RejectedInfo);
		}

		[Theory]
		[InlineData("2", "sibling")]
		[InlineData("1", "zip")]
		[InlineData("0", "folder")]
		[InlineData("9", "folder")] // any unrecognized origin value falls back to folder
		public void Parse_OriginColumn_MapsToExpectedSource(string origin, string expectedSource)
		{
			string input = $"pack.zip\tName\t1\tAu\tLic\tS\t1\t{origin}";

			MepPackListEntry entry = Assert.Single(MepPackListParser.Parse(input).Packs);

			Assert.Equal(expectedSource, entry.Source);
		}
	}
}
