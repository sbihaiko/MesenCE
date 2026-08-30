using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for the Google Drive URL parser (MEI-v1 §2.4, ADR-0138 §50):
	//the client maps the catalog's drive share URL onto the two-step download
	//dance, and this decides which file the dance targets. Mirrors
	//scripts/fetch_pack.py::extract_drive_id - the canonical '/d/<id>' path
	//segment wins, then the '?id=' query parameter.
	public class CommunityPackDriveTests
	{
		[Theory]
		[InlineData("https://drive.google.com/file/d/abc123/view", "abc123")]
		[InlineData("https://drive.google.com/file/d/AbC_-xYz/view?usp=sharing", "AbC_-xYz")]
		[InlineData("https://drive.google.com/open?id=abc123", "abc123")]
		[InlineData("https://drive.google.com/open?id=abc123&usp=sharing", "abc123")]
		[InlineData("https://drive.google.com/uc?export=download&id=abc123", "abc123")]
		[InlineData("https://drive.google.com/file/d/abc123/view#frag", "abc123")]
		public void ExtractFileId_ValidShare_FindsId(string url, string expected)
		{
			Assert.Equal(expected, CommunityPackDrive.ExtractFileId(url));
		}

		[Fact]
		public void ExtractFileId_PathSegmentWinsOverQuery()
		{
			//A fragment or query can carry a stray 'id' - the '/d/<id>' path is
			//canonical and must win (matches fetch_pack.py, which regexes path).
			Assert.Equal("real", CommunityPackDrive.ExtractFileId(
				"https://drive.google.com/file/d/real/view?id=decoy"));
		}

		[Theory]
		[InlineData("https://drive.google.com/drive/folders/abc123")] // folder, not a file
		[InlineData("https://drive.google.com/file/d/")] // empty id
		[InlineData("https://drive.google.com/open?other=1")] // no id at all
		[InlineData("")]
		[InlineData(null)]
		public void ExtractFileId_NotAFileShare_ReturnsNull(string? url)
		{
			Assert.Null(CommunityPackDrive.ExtractFileId(url!));
		}

		[Fact]
		public void ExtractFileId_DoesNotCheckHost()
		{
			//The parser only turns a share-shaped URL into an id; the host gate
			//is the downloader's allow-list (MatchHost must return a
			//"google-drive"-kind entry before the dance is even attempted).
			//This mirrors fetch_pack.py, which urlparses and regexes the path
			//without looking at netloc - so it also yields "abc123" here.
			Assert.Equal("abc123", CommunityPackDrive.ExtractFileId(
				"https://example.com/file/d/abc123"));
		}

		[Fact]
		public void ExtractFileId_QueryValueIsDecoded()
		{
			//parse_qs semantics: '+' is a space and %XX is unquoted.
			Assert.Equal("ab c", CommunityPackDrive.ExtractFileId(
				"https://drive.google.com/open?id=ab%20c"));
		}

		[Fact]
		public void ExtractFileId_IdLookAlikeInTrailingPath_NotMatched()
		{
			//'/d/' must be a path segment; '/whatever/d/' does not qualify.
			Assert.Null(CommunityPackDrive.ExtractFileId(
				"https://drive.google.com/xd/abc123"));
		}
	}
}
