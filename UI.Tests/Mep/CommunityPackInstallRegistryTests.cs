using Mesen.Logic;
using System;
using System.IO;
using Xunit;

namespace Mesen.Tests.Mep
{
	// Coverage for the host-free install registry (UI/Logic/CommunityPackInstallRegistry.cs,
	// ADR-0147): round-trips the ROM -> pack mapping outside the editable mep/ folder, so a
	// mangled pack never destroys the ability to Restore.
	public class CommunityPackInstallRegistryTests
	{
		private const string RomSha1 = "2A4E126D0286BEA0BF503C80A12352C57539F76B";

		[Fact]
		public void Write_Then_Read_RoundTripsEveryField()
		{
			string cacheRoot = Path.Combine(Path.GetTempPath(), "mep_registry_" + Guid.NewGuid().ToString("N"));
			var record = new CommunityPackInstallRecord {
				PackId = "com.example.zelda",
				ContentId = "abc123",
				SourceSha256 = new string('a', 64),
				Container = "Zelda",
				MepPath = Path.Combine(cacheRoot, "sibling", "mep"),
				InstalledAt = "2026-09-01T00:00:00Z",
			};
			try {
				CommunityPackInstallRegistry.Write(cacheRoot, RomSha1, record);
				Assert.True(File.Exists(CommunityPackInstallRegistry.FilePath(cacheRoot, RomSha1)));

				CommunityPackInstallRecord? read = CommunityPackInstallRegistry.Read(cacheRoot, RomSha1);
				Assert.NotNull(read);
				Assert.Equal(record.PackId, read!.PackId);
				Assert.Equal(record.ContentId, read.ContentId);
				Assert.Equal(record.SourceSha256, read.SourceSha256);
				Assert.Equal(record.Container, read.Container);
				Assert.Equal(record.MepPath, read.MepPath);
				Assert.Equal(record.InstalledAt, read.InstalledAt);
			} finally {
				Directory.Delete(cacheRoot, true);
			}
		}

		[Fact]
		public void Read_MissingRomSha1_ReturnsNull()
		{
			string cacheRoot = Path.Combine(Path.GetTempPath(), "mep_registry_" + Guid.NewGuid().ToString("N"));
			try {
				Assert.Null(CommunityPackInstallRegistry.Read(cacheRoot, RomSha1));
			} finally {
				if(Directory.Exists(cacheRoot)) {
					Directory.Delete(cacheRoot, true);
				}
			}
		}

		[Fact]
		public void Read_MalformedJson_ReturnsNull()
		{
			string cacheRoot = Path.Combine(Path.GetTempPath(), "mep_registry_" + Guid.NewGuid().ToString("N"));
			string path = CommunityPackInstallRegistry.FilePath(cacheRoot, RomSha1);
			Directory.CreateDirectory(Path.GetDirectoryName(path)!);
			File.WriteAllText(path, "{ not valid json ");
			try {
				Assert.Null(CommunityPackInstallRegistry.Read(cacheRoot, RomSha1));
			} finally {
				Directory.Delete(cacheRoot, true);
			}
		}

		[Fact]
		public void FilePath_LowercasesTheRomSha1Key()
		{
			Assert.EndsWith("/installs/" + RomSha1.ToLowerInvariant() + ".json",
				CommunityPackInstallRegistry.FilePath("/cache", RomSha1).Replace('\\', '/'));
		}
	}
}
