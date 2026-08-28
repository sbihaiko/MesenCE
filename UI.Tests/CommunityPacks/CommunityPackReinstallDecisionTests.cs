using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//D7: exercises UI/Logic/CommunityPackReinstallDecision.cs against raw
	//JSON text - no real filesystem access, no Avalonia/EmuApi.
	public class CommunityPackReinstallDecisionTests
	{
		private const string CatalogSha256 = "a3f1c2d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2";

		[Fact]
		public void Decide_ReturnsNotInstalledWhenStampIsNull()
		{
			Assert.Equal(CommunityPackReinstallVerdict.NotInstalled, CommunityPackReinstallDecision.Decide(CatalogSha256, null));
		}

		[Fact]
		public void Decide_ReturnsNotInstalledWhenStampIsEmptyOrWhitespace()
		{
			Assert.Equal(CommunityPackReinstallVerdict.NotInstalled, CommunityPackReinstallDecision.Decide(CatalogSha256, ""));
			Assert.Equal(CommunityPackReinstallVerdict.NotInstalled, CommunityPackReinstallDecision.Decide(CatalogSha256, "   "));
		}

		[Fact]
		public void Decide_ReturnsUpToDateWhenSha256Matches()
		{
			string stamp = BuildStamp(CatalogSha256);

			Assert.Equal(CommunityPackReinstallVerdict.UpToDate, CommunityPackReinstallDecision.Decide(CatalogSha256, stamp));
		}

		[Fact]
		public void Decide_MatchIsCaseInsensitiveOnHexHash()
		{
			string stamp = BuildStamp(CatalogSha256.ToUpperInvariant());

			Assert.Equal(CommunityPackReinstallVerdict.UpToDate, CommunityPackReinstallDecision.Decide(CatalogSha256, stamp));
		}

		[Fact]
		public void Decide_ReturnsReinstallWhenSha256Differs()
		{
			string stamp = BuildStamp("0000000000000000000000000000000000000000000000000000000000000f");

			Assert.Equal(CommunityPackReinstallVerdict.Reinstall, CommunityPackReinstallDecision.Decide(CatalogSha256, stamp));
		}

		[Fact]
		public void Decide_ReturnsReinstallWhenStampJsonIsMalformed()
		{
			//A stamp file exists but is corrupt: fail closed toward
			//reinstalling rather than silently treating it as up to date.
			Assert.Equal(CommunityPackReinstallVerdict.Reinstall, CommunityPackReinstallDecision.Decide(CatalogSha256, "{not valid json"));
		}

		[Fact]
		public void Decide_ReturnsReinstallWhenStampJsonIsMissingSourceSha256()
		{
			string stamp = "{\"recipe_hash\": \"abc\", \"deps\": {}, \"installed_at\": \"2026-08-28T00:00:00Z\"}";

			Assert.Equal(CommunityPackReinstallVerdict.Reinstall, CommunityPackReinstallDecision.Decide(CatalogSha256, stamp));
		}

		[Fact]
		public void Decide_ReturnsReinstallWhenSourceIsNotAnObject()
		{
			string stamp = "{\"source\": \"" + CatalogSha256 + "\"}";

			Assert.Equal(CommunityPackReinstallVerdict.Reinstall, CommunityPackReinstallDecision.Decide(CatalogSha256, stamp));
		}

		//Mirrors the exact shape MepRecipeInstaller::WriteInstallStamp writes
		//(Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp).
		private static string BuildStamp(string sourceSha256)
		{
			return "{\n  \"recipe_hash\": \"deadbeef\",\n  \"source\": { \"sha256\": \"" + sourceSha256 + "\" },\n"
				+ "  \"deps\": {},\n  \"installed_at\": \"2026-08-28T00:00:00Z\"\n}\n";
		}
	}
}
