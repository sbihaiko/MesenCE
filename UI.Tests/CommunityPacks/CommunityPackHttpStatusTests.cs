using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for CommunityPackHttpStatus (ADR-0138 §50): the downloader
	//must follow real redirects and must NOT treat 304 Not Modified as one.
	public class CommunityPackHttpStatusTests
	{
		[Theory]
		[InlineData(301)]
		[InlineData(302)]
		[InlineData(303)]
		[InlineData(307)]
		[InlineData(308)]
		public void IsFollowableRedirect_RfcRedirects_ReturnsTrue(int statusCode)
		{
			Assert.True(CommunityPackHttpStatus.IsFollowableRedirect(statusCode));
		}

		[Theory]
		[InlineData(200)]
		[InlineData(204)]
		[InlineData(304)]
		[InlineData(400)]
		[InlineData(404)]
		[InlineData(500)]
		[InlineData(300)]
		[InlineData(305)]
		[InlineData(306)]
		public void IsFollowableRedirect_NonRedirectsIncluding304_ReturnsFalse(int statusCode)
		{
			Assert.False(CommunityPackHttpStatus.IsFollowableRedirect(statusCode));
		}
	}
}
