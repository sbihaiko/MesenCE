using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	// ADR-0138 §52 (F6.4b-2): the submitter-influenced catalog name must never
	// escape the enhancement-pack folder or collapse into '.'/'..'.
	public class CommunityPackContainerNameTests
	{
		[Fact]
		public void Sanitize_PlainName_IsKept()
		{
			Assert.Equal("Zelda HD", CommunityPackContainerName.Sanitize("Zelda HD", "The Legend of Zelda"));
		}

		[Fact]
		public void Sanitize_BlankName_FallsBackToGame()
		{
			Assert.Equal("Excitebike", CommunityPackContainerName.Sanitize("  ", "Excitebike"));
		}

		[Theory]
		[InlineData("..")]
		[InlineData(".")]
		[InlineData("...")]
		[InlineData("")]
		public void Sanitize_DotOnlyOrEmpty_UsesFallback(string name)
		{
			Assert.Equal(CommunityPackContainerName.Fallback, CommunityPackContainerName.Sanitize(name, ""));
		}

		[Theory]
		[InlineData("../../etc", ".._.._etc")]
		[InlineData("..\\..\\x", ".._.._x")]
		[InlineData("a/b", "a_b")]
		public void Sanitize_PathSeparators_AreReplaced(string name, string expected)
		{
			Assert.Equal(expected, CommunityPackContainerName.Sanitize(name, ""));
		}

		[Fact]
		public void Sanitize_TrailingDotsAndSpaces_AreStripped()
		{
			Assert.Equal("pack", CommunityPackContainerName.Sanitize("pack. . ", ""));
		}

		[Fact]
		public void Sanitize_LongName_IsCappedAndRetrimmed()
		{
			string name = new string('a', CommunityPackContainerName.MaxLength - 1) + "." + new string('b', 20);
			string result = CommunityPackContainerName.Sanitize(name, "");
			Assert.Equal(CommunityPackContainerName.MaxLength - 1, result.Length);
			Assert.DoesNotContain(".", result);
		}
	}
}
