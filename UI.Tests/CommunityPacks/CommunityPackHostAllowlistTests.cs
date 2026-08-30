using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	// F6.4b (ADR-0138 SS37): coverage for the client-side mirror of
	// scripts/fetch_pack.py:match_host, and for the loader that reads the
	// real scripts/pack_host_allowlist.json instead of a hand-copied list.
	public class CommunityPackHostAllowlistTests
	{
		// UI.Tests runs from UI.Tests/bin/<config>/net10.0/, several levels
		// below the repo root - walk up from AppContext.BaseDirectory until
		// scripts/pack_host_allowlist.json is found. This is the ONLY place
		// this test file names any host: every assertion below comes from
		// parsing that real file, never from a copy inlined here.
		private static IReadOnlyList<CommunityPackHostEntry> LoadRealAllowlist()
		{
			DirectoryInfo? dir = new(AppContext.BaseDirectory);
			while(dir != null) {
				string candidate = Path.Combine(dir.FullName, CommunityPackHostAllowlist.RepoRelativePath);
				if(File.Exists(candidate)) {
					return CommunityPackHostAllowlist.LoadFromFile(candidate);
				}
				dir = dir.Parent;
			}
			throw new FileNotFoundException(
				$"Could not locate {CommunityPackHostAllowlist.RepoRelativePath} walking up from " +
				AppContext.BaseDirectory);
		}

		[Fact]
		public void LoadFromFile_RealAllowlist_HasExactlyEightEntries()
		{
			Assert.Equal(8, LoadRealAllowlist().Count);
		}

		[Fact]
		public void LoadFromFile_RealAllowlist_GithubComHasReleasesAndArchivePathGate()
		{
			CommunityPackHostEntry github = Assert.Single(LoadRealAllowlist(), h => h.Host == "github.com");

			Assert.Equal(new[] { "/releases/", "/archive/" }, github.PathContainsAny);
			Assert.Equal("direct", github.Kind);
		}

		[Fact]
		public void LoadFromFile_RealAllowlist_ReleaseAssetHostIsDirectAndPathGated()
		{
			//release-assets.githubusercontent.com serves the actual bytes behind
			//github.com release redirects - the client hits it on the second hop
			//(issue #142 investigation).
			CommunityPackHostEntry asset = Assert.Single(LoadRealAllowlist(), h => h.Host == "release-assets.githubusercontent.com");

			Assert.Equal("direct", asset.Kind);
			Assert.Null(asset.PathContainsAny);
			Assert.NotNull(CommunityPackHostAllowlist.MatchHost(
				"https://release-assets.githubusercontent.com/github-production-release-asset/1/2.zip", LoadRealAllowlist()));
		}

		[Theory]
		[InlineData("codeload.github.com", "direct")]
		[InlineData("release-assets.githubusercontent.com", "direct")]
		[InlineData("raw.githubusercontent.com", "direct")]
		[InlineData("gist.githubusercontent.com", "direct")]
		[InlineData("gist.github.com", "direct")]
		[InlineData("drive.google.com", "google-drive")]
		[InlineData("drive.usercontent.google.com", "google-drive")]
		public void LoadFromFile_RealAllowlist_NonGithubHostsHaveNoPathGate(string host, string kind)
		{
			CommunityPackHostEntry entry = Assert.Single(LoadRealAllowlist(), h => h.Host == host);

			Assert.True(entry.PathContainsAny == null || entry.PathContainsAny.Count == 0);
			Assert.Equal(kind, entry.Kind);
		}

		[Theory]
		[InlineData("https://github.com/u/r/releases/download/v1/pack.zip", "github.com")]
		[InlineData("https://codeload.github.com/u/r/zip/refs/heads/main", "codeload.github.com")]
		[InlineData("https://drive.google.com/file/d/abc123/view", "drive.google.com")]
		public void MatchHost_RealAllowlist_AllowedUrl_Matches(string url, string expectedHost)
		{
			CommunityPackHostEntry? match = CommunityPackHostAllowlist.MatchHost(url, LoadRealAllowlist());

			Assert.NotNull(match);
			Assert.Equal(expectedHost, match!.Host);
		}

		[Theory]
		[InlineData("https://github.com/u/r/blob/main/pack.zip")] // path gate not satisfied
		[InlineData("http://github.com/u/r/releases/download/v1/pack.zip")] // non-https
		[InlineData("https://evil.example.com/releases/pack.zip")] // unlisted host
		[InlineData("https://notgithub.com.evil.example/releases/pack.zip")] // substring, not exact netloc
		public void MatchHost_RealAllowlist_RejectedUrl_ReturnsNull(string url)
		{
			Assert.Null(CommunityPackHostAllowlist.MatchHost(url, LoadRealAllowlist()));
		}

		// --- Pure Parse(string)/LoadFromStream coverage, independent of the real file ---

		[Fact]
		public void Parse_MinimalJson_ReturnsParsedEntries()
		{
			const string json = """
				{"_comment": "ignored", "hosts": [
				  {"host": "example.com", "path_contains_any": ["/a/"], "kind": "direct"},
				  {"host": "nogate.example.com", "kind": "direct"}
				]}
				""";

			IReadOnlyList<CommunityPackHostEntry> hosts = CommunityPackHostAllowlist.Parse(json);

			Assert.Equal(2, hosts.Count);
			Assert.Equal(new[] { "/a/" }, hosts[0].PathContainsAny);
			Assert.Null(hosts[1].PathContainsAny);
		}

		[Fact]
		public void Parse_EmptyHostsArray_ReturnsEmptyList()
		{
			Assert.Empty(CommunityPackHostAllowlist.Parse("""{"hosts": []}"""));
		}

		[Fact]
		public void MatchHost_ParsedMinimalAllowlist_PathGateEnforced()
		{
			IReadOnlyList<CommunityPackHostEntry> hosts = CommunityPackHostAllowlist.Parse(
				"""{"hosts": [{"host": "example.com", "path_contains_any": ["/releases/"]}]}""");

			Assert.NotNull(CommunityPackHostAllowlist.MatchHost("https://example.com/x/releases/y", hosts));
			Assert.Null(CommunityPackHostAllowlist.MatchHost("https://example.com/x/other/y", hosts));
		}

		[Fact]
		public void LoadFromStream_MinimalJson_ParsesSameAsParse()
		{
			using MemoryStream stream = new(Encoding.UTF8.GetBytes("""{"hosts": [{"host": "example.com"}]}"""));

			IReadOnlyList<CommunityPackHostEntry> hosts = CommunityPackHostAllowlist.LoadFromStream(stream);

			Assert.Single(hosts);
			Assert.Equal("example.com", hosts[0].Host);
		}
	}
}
