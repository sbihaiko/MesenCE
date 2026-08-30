using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Coverage for the host-free hd-legacy install helpers (MEI-v1 §2.3): the
	//zip-slip normalization mirrors MepPack::NormalizeRelativePath, and the
	//pack-root discovery mirrors FindFallbackSubfolder/DiscoverPrimaryRoot
	//(ADR-0120). These are the exact rules that decide where a community
	//legacy HD pack's hires.txt lands, so the classic HdPacks/<rom>/ loader
	//picks it up (ADR-0040 §5).
	public class LegacyHdPackInstallTests
	{
		// --- NormalizeZipPath -------------------------------------------------

		[Theory]
		[InlineData("hires.txt", "hires.txt")]
		[InlineData("a/b.png", "a/b.png")]
		[InlineData("Contra80s-v1.1/Contra (U) [!]/hires.txt", "Contra80s-v1.1/Contra (U) [!]/hires.txt")]
		[InlineData("a\\b.png", "a/b.png")] // backslash normalised to '/'
		[InlineData("a//b.png", "a/b.png")] // empty segment dropped
		[InlineData("a/./b.png", "a/b.png")] // "." segment dropped
		public void NormalizeZipPath_AcceptablePath_Normalizes(string path, string expected)
		{
			Assert.Equal(expected, LegacyHdPackInstall.NormalizeZipPath(path));
		}

		[Theory]
		[InlineData("../x")]
		[InlineData("a/../b")]
		[InlineData("..")]
		[InlineData("/abs/path")]
		[InlineData("C:/x")]
		[InlineData("C:\\x")]
		[InlineData("a\x01b")] // control character
		[InlineData("")]
		[InlineData(".")]
		public void NormalizeZipPath_ZipSlipOrEmpty_ReturnsNull(string path)
		{
			Assert.Null(LegacyHdPackInstall.NormalizeZipPath(path));
		}

		// --- FindPackRoot -----------------------------------------------------

		[Fact]
		public void FindPackRoot_ArtistFolderNotMatchingRomName_UsesSoleHiresParent()
		{
			//The real Contra80s shape: a single hires.txt under a folder named
			//after the artist's ROM ("Contra (U) [!]"), which does NOT equal the
			//loaded ROM's file name ("Contra (USA"). The root is that folder.
			string[] entries = {
				"Contra80s-v1.1/Contra (U) [!]/hires.txt",
				"Contra80s-v1.1/Contra (U) [!]/Ash1.png",
				"Contra80s-v1.1/art/banner.png",
			};

			Assert.Equal("Contra80s-v1.1/Contra (U) [!]/", LegacyHdPackInstall.FindPackRoot(entries, "Contra (USA)"));
		}

		[Fact]
		public void FindPackRoot_RootLevelHiresText_RootIsZip()
		{
			Assert.Equal("", LegacyHdPackInstall.FindPackRoot(new[] { "hires.txt", "tiles/a.png" }, "Some Rom"));
		}

		[Fact]
		public void FindPackRoot_RomNameFolderPreferredOverAnotherHires()
		{
			string[] entries = {
				"pack/Contra (USA)/hires.txt",
				"pack/alternate/hires.txt",
			};

			Assert.Equal("pack/Contra (USA)/", LegacyHdPackInstall.FindPackRoot(entries, "Contra (USA)"));
		}

		[Fact]
		public void FindPackRoot_NoRomMatch_PicksShallowest()
		{
			string[] entries = {
				"pack/a/hires.txt",
				"pack/a/deep/hires.txt",
			};

			Assert.Equal("pack/a/", LegacyHdPackInstall.FindPackRoot(entries, "Some Rom"));
		}

		[Fact]
		public void FindPackRoot_NoHiresText_ReturnsNull()
		{
			Assert.Null(LegacyHdPackInstall.FindPackRoot(new[] { "pack/a.png" }, "Some Rom"));
		}

		[Fact]
		public void FindPackRoot_HiresTextCaseInsensitive()
		{
			Assert.Equal("PACK/", LegacyHdPackInstall.FindPackRoot(new[] { "PACK/HIRES.TXT" }, "Some Rom"));
		}

		// --- FindNestedZip ------------------------------------------------------

		[Fact]
		public void FindNestedZip_SingleRootLevelZip_FindsIt()
		{
			string[] entries = { "ZeldaRemastered.zip", "readme.txt", "banner.png" };

			Assert.Equal("ZeldaRemastered.zip", LegacyHdPackInstall.FindNestedZip(entries));
		}

		[Fact]
		public void FindNestedZip_NoRootZip_ReturnsNull()
		{
			Assert.Null(LegacyHdPackInstall.FindNestedZip(new[] { "readme.txt", "pack/hires.txt" }));
			Assert.Null(LegacyHdPackInstall.FindNestedZip(Array.Empty<string>()));
		}

		[Fact]
		public void FindNestedZip_MultipleRootLevelZips_ReturnsNull()
		{
			Assert.Null(LegacyHdPackInstall.FindNestedZip(new[] { "a.zip", "b.zip", "readme.txt" }));
		}

		[Fact]
		public void FindNestedZip_ZipInsideSubfolder_IsNotCounted()
		{
			//Only a ROOT-level entry qualifies; a pack folder holding its own
			//assets zip is not a wrapper.
			string[] entries = { "pack/", "pack/hires.txt", "pack/assets.zip" };

			Assert.Null(LegacyHdPackInstall.FindNestedZip(entries));
		}

		[Fact]
		public void FindNestedZip_ExtensionIsCaseInsensitive()
		{
			Assert.Equal("PACK.ZIP", LegacyHdPackInstall.FindNestedZip(new[] { "PACK.ZIP", "readme.txt" }));
		}

		[Fact]
		public void FindNestedZip_OtherRootLevelExtensions_Ignored()
		{
			string[] entries = { "pack.7z", "pack.tar.gz", "pack.zip", "readme.txt" };

			Assert.Equal("pack.zip", LegacyHdPackInstall.FindNestedZip(entries));
		}

		// --- End-to-end plan over a real zip (contra-style structure) ----------

		[Fact]
		public void ExtractionPlan_ContraStyleZip_KeepsPackRootOnly()
		{
			using MemoryStream ms = new();
			using(ZipArchive zip = new(ms, ZipArchiveMode.Create, true)) {
				CreateEntry(zip, "Contra80s-v1.1/Contra (U) [!]/hires.txt", "textures def");
				CreateEntry(zip, "Contra80s-v1.1/Contra (U) [!]/Ash1.png", "png");
				CreateEntry(zip, "Contra80s-v1.1/art/banner.png", "art - outside the pack root");
				CreateEntry(zip, "Contra80s-v1.1/changelog.txt", "readme - outside the pack root");
			}

			ms.Position = 0;
			List<string> normalized = new();
			using(ZipArchive zip = new(ms, ZipArchiveMode.Read)) {
				foreach(ZipArchiveEntry e in zip.Entries) {
					string? norm = LegacyHdPackInstall.NormalizeZipPath(e.FullName);
					if(norm != null) {
						normalized.Add(norm);
					}
				}
			}

			string? root = LegacyHdPackInstall.FindPackRoot(normalized, "Contra (USA)");
			Assert.Equal("Contra80s-v1.1/Contra (U) [!]/", root);

			List<string> rels = normalized
				.Where(n => n.StartsWith(root!, StringComparison.Ordinal))
				.Select(n => n.Substring(root!.Length))
				.Where(r => r.Length > 0)
				.OrderBy(r => r, StringComparer.Ordinal)
				.ToList();

			Assert.Equal(new[] { "Ash1.png", "hires.txt" }, rels);
		}

		private static void CreateEntry(ZipArchive zip, string name, string content)
		{
			ZipArchiveEntry entry = zip.CreateEntry(name);
			using Stream stream = entry.Open();
			using StreamWriter writer = new(stream);
			writer.Write(content);
		}
	}
}
