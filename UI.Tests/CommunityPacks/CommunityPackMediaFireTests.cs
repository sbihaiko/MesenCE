using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for CommunityPackMediaFire (allow-list kind "mediafire"):
	//the share page's downloadN.mediafire.com href, including HTML entities.
	public class CommunityPackMediaFireTests
	{
		[Fact]
		public void ExtractDownloadUrl_QuotedHttpsCdnHref_ReturnsUrl()
		{
			const string html = "<a href=\"https://download1532.mediafire.com/abc/pack.zip\">Download</a>";

			Assert.Equal(
				"https://download1532.mediafire.com/abc/pack.zip",
				CommunityPackMediaFire.ExtractDownloadUrl(html));
		}

		[Fact]
		public void ExtractDownloadUrl_HtmlEncodedAmpersand_IsDecoded()
		{
			const string html = "<a href=\"https://download1.mediafire.com/x?a=1&amp;b=2\">x</a>";

			Assert.Equal(
				"https://download1.mediafire.com/x?a=1&b=2",
				CommunityPackMediaFire.ExtractDownloadUrl(html));
		}

		[Theory]
		[InlineData("")]
		[InlineData("<html></html>")]
		[InlineData("href=\"https://evil.example.com/download1.mediafire.com/x\"")]
		[InlineData("href=\"http://download1.mediafire.com/x\"")]
		public void ExtractDownloadUrl_MissingOrNonHttpsCdn_ReturnsNull(string html)
		{
			Assert.Null(CommunityPackMediaFire.ExtractDownloadUrl(html));
		}
	}
}
