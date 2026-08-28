using System.Collections.Generic;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//D5: exercises UI/Logic/CommunityPackDepResolver.cs entirely with
	//in-memory file lists - no real filesystem access, no Avalonia/EmuApi.
	public class CommunityPackDepResolverTests
	{
		private const string DepSha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85";

		[Fact]
		public void Resolve_FindsDepInPackFolder()
		{
			List<CommunityPackLocalFile> packFolder = new() {
				new CommunityPackLocalFile("/rom/Zelda/audio.zip", DepSha256)
			};
			List<CommunityPackLocalFile> downloadsCache = new();

			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(DepSha256, packFolder, downloadsCache);

			Assert.False(result.RequiresPrompt);
			Assert.Equal("/rom/Zelda/audio.zip", result.ResolvedPath);
		}

		[Fact]
		public void Resolve_FindsDepInDownloadsCacheWhenNotInPackFolder()
		{
			List<CommunityPackLocalFile> packFolder = new() {
				new CommunityPackLocalFile("/rom/Zelda/unrelated.png", "00000000000000000000000000000000000000000000000000000000000000")
			};
			List<CommunityPackLocalFile> downloadsCache = new() {
				new CommunityPackLocalFile("/home/user/Downloads/zelda-hd-ogg.zip", DepSha256)
			};

			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(DepSha256, packFolder, downloadsCache);

			Assert.False(result.RequiresPrompt);
			Assert.Equal("/home/user/Downloads/zelda-hd-ogg.zip", result.ResolvedPath);
		}

		[Fact]
		public void Resolve_PrefersPackFolderOverDownloadsCacheWhenBothMatch()
		{
			List<CommunityPackLocalFile> packFolder = new() {
				new CommunityPackLocalFile("/rom/Zelda/audio.zip", DepSha256)
			};
			List<CommunityPackLocalFile> downloadsCache = new() {
				new CommunityPackLocalFile("/home/user/Downloads/zelda-hd-ogg.zip", DepSha256)
			};

			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(DepSha256, packFolder, downloadsCache);

			Assert.Equal("/rom/Zelda/audio.zip", result.ResolvedPath);
		}

		[Fact]
		public void Resolve_MatchIsCaseInsensitiveOnHexHash()
		{
			List<CommunityPackLocalFile> packFolder = new() {
				new CommunityPackLocalFile("/rom/Zelda/audio.zip", DepSha256.ToUpperInvariant())
			};

			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(DepSha256, packFolder, new List<CommunityPackLocalFile>());

			Assert.False(result.RequiresPrompt);
			Assert.Equal("/rom/Zelda/audio.zip", result.ResolvedPath);
		}

		[Fact]
		public void Resolve_NotFoundAnywhereReturnsPromptWithHintsAndLicense()
		{
			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(
				DepSha256,
				new List<CommunityPackLocalFile>(),
				new List<CommunityPackLocalFile>(),
				hints: "Download the audio archive from the forum thread linked in the pack README.",
				license: "CC0-1.0");

			Assert.True(result.RequiresPrompt);
			Assert.Null(result.ResolvedPath);
			Assert.Equal("Download the audio archive from the forum thread linked in the pack README.", result.Hints);
			Assert.Equal("CC0-1.0", result.License);
		}

		[Fact]
		public void Resolve_NotFoundWithNoLicenseDeclaredFallsBackToNotDeclaredLiteral()
		{
			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(
				DepSha256,
				new List<CommunityPackLocalFile>(),
				new List<CommunityPackLocalFile>(),
				hints: "See the issue thread.",
				license: null);

			Assert.True(result.RequiresPrompt);
			Assert.Equal(CommunityPackDepResolver.LicenseNotDeclared, result.License);
			Assert.Equal("not declared", result.License);
		}

		[Fact]
		public void Resolve_NotFoundWithBlankLicenseFallsBackToNotDeclaredLiteral()
		{
			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(
				DepSha256,
				new List<CommunityPackLocalFile>(),
				new List<CommunityPackLocalFile>(),
				hints: null,
				license: "   ");

			Assert.True(result.RequiresPrompt);
			Assert.Equal("not declared", result.License);
			Assert.Equal("", result.Hints);
		}

		[Fact]
		public void Resolve_MismatchedHashInBothListsStillPrompts()
		{
			List<CommunityPackLocalFile> packFolder = new() {
				new CommunityPackLocalFile("/rom/Zelda/other.zip", "1111111111111111111111111111111111111111111111111111111111111a")
			};
			List<CommunityPackLocalFile> downloadsCache = new() {
				new CommunityPackLocalFile("/home/user/Downloads/other.zip", "2222222222222222222222222222222222222222222222222222222222222b")
			};

			CommunityPackDepResolution result = CommunityPackDepResolver.Resolve(DepSha256, packFolder, downloadsCache);

			Assert.True(result.RequiresPrompt);
			Assert.Null(result.ResolvedPath);
		}
	}
}
