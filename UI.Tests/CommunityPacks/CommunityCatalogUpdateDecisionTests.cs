using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//P.6 (PRD Part B §3.6, amends ADR-0138 §37): the client-side catalog
	//update decision. Trigger is the installed content_id vs the slot's - a
	//different content_id reinstalls (unless the installed semver is newer, no
	//auto-downgrade), an unchanged content_id never reinstalls (wrapper-only
	//repack), and a slot that disappeared keeps the install with no toast.
	public class CommunityCatalogUpdateDecisionTests
	{
		private static InstallStampFields Installed(string contentId = "AAA", string source = "src1") => new(contentId, source);

		[Fact]
		public void DifferentContentId_Updates()
		{
			//The chosen pack_id's catalog slot gained a new revision -> reinstall.
			Assert.Equal(CommunityCatalogUpdateVerdict.Updated, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "BBB", slotVersion: "1.1.0", slotSourceSha256: "src2", isHdLegacy: false,
				installed: Installed("AAA", "src1"), installedVersion: "1.0.0"));
		}

		[Fact]
		public void SameContentId_SameSource_UpToDate()
		{
			Assert.Equal(CommunityCatalogUpdateVerdict.UpToDate, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "AAA", slotVersion: "1.0.0", slotSourceSha256: "src1", isHdLegacy: false,
				installed: Installed("AAA", "src1"), installedVersion: "1.0.0"));
		}

		[Fact]
		public void SameContentId_DifferentSource_WrapperOnly_NoReinstall()
		{
			//ADR-0138 §37's source.sha256 trigger fires, but the content_id is
			//unchanged - a wrapper-only repack. P.6: do not reinstall.
			Assert.Equal(CommunityCatalogUpdateVerdict.WrapperOnly, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "AAA", slotVersion: "1.0.0", slotSourceSha256: "src2", isHdLegacy: false,
				installed: Installed("AAA", "src1"), installedVersion: "1.0.0"));
		}

		[Fact]
		public void InstalledNewer_NoDowngrade()
		{
			//Installed 1.5.0, slot 1.2.0 (yank/rollback) -> keep the install.
			Assert.Equal(CommunityCatalogUpdateVerdict.NoDowngrade, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "BBB", slotVersion: "1.2.0", slotSourceSha256: "src2", isHdLegacy: false,
				installed: Installed("AAA", "src1"), installedVersion: "1.5.0"));
		}

		[Fact]
		public void RemovedFromCatalog_KeepsInstall()
		{
			//No slot for the chosen pack_id -> keep the install, no toast.
			Assert.Equal(CommunityCatalogUpdateVerdict.RemovedFromCatalog, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "", slotVersion: null, slotSourceSha256: null, isHdLegacy: false,
				installed: Installed("AAA", "src1"), installedVersion: "1.0.0"));
		}

		[Fact]
		public void HdLegacy_NoSemver_AnyContentChange_Updates()
		{
			//hd-legacy has no version number to protect: a content_id difference
			//always updates, even though the installed "version" (validation date)
			//would compare higher.
			Assert.Equal(CommunityCatalogUpdateVerdict.Updated, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "BBB", slotVersion: "2026-08-01", slotSourceSha256: "src2", isHdLegacy: true,
				installed: Installed("AAA", "src1"), installedVersion: "2026-08-20"));
		}

		[Fact]
		public void NoStamp_NotInstalled()
		{
			Assert.Equal(CommunityCatalogUpdateVerdict.NotInstalled, CommunityCatalogUpdateDecision.Decide(
				slotContentId: "AAA", slotVersion: "1.0.0", slotSourceSha256: "src1", isHdLegacy: false,
				installed: null, installedVersion: null));
		}

		[Fact]
		public void ReadStampFields_ParsesContentIdAndSource()
		{
			InstallStampFields? fields = CommunityCatalogUpdateDecision.ReadStampFields(
				"{\"pack_id\":\"x\",\"content_id\":\"AAA\",\"recipe_hash\":\"h\",\"source\":{\"sha256\":\"src1\"},\"deps\":{},\"installed_at\":\"t\"}");
			Assert.NotNull(fields);
			Assert.Equal("AAA", fields!.ContentId);
			Assert.Equal("src1", fields.SourceSha256);
		}

		[Fact]
		public void ReadStampFields_Malformed_ReturnsNull()
		{
			Assert.Null(CommunityCatalogUpdateDecision.ReadStampFields("not json{"));
			Assert.Null(CommunityCatalogUpdateDecision.ReadStampFields(""));
			Assert.Null(CommunityCatalogUpdateDecision.ReadStampFields(null));
		}

		[Theory]
		[InlineData("1.5.0", "1.2.0", 1)]
		[InlineData("2.0.0", "1.9.9", 1)]
		[InlineData("1.0.0", "1.0.0", 0)]
		[InlineData("0.9.9", "1.0.0", -1)]
		[InlineData("1.0.0-beta", "1.0.0", 0)]
		[InlineData("unknown", "1.0.0", 0)]
		public void CompareSemver_Numeric(string a, string b, int expected)
		{
			Assert.Equal(expected, CommunityCatalogUpdateDecision.CompareSemver(a, b));
		}
	}
}
