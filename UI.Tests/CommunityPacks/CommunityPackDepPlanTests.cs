using Mesen.Logic;
using System.Collections.Generic;
using System.Linq;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//F6.4b / F6.5: the pure half of CommunityPackInstallCoordinator.ResolveDeps
	//- the pending-dependency prompt list and the hash-match verdict for a file
	//dropped into .cache/downloads/.
	public class CommunityPackDepPlanTests
	{
		private const string ShaA = "aaaa000000000000000000000000000000000000000000000000000000000001";
		private const string ShaB = "bbbb000000000000000000000000000000000000000000000000000000000002";

		private static CommunityPackDep Dep(string id, string sha, string? license = null, string[]? hints = null)
		{
			return new CommunityPackDep { Id = id, Sha256 = sha, License = license, Hints = hints };
		}

		private static List<CommunityPackLocalFile> Files(params CommunityPackLocalFile[] files) => files.ToList();

		private static List<CommunityPackLocalFile> None() => new();

		[Fact]
		public void DependencyPresentInDownloadsCache_Resolves()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, System.Array.Empty<string>(), None(),
				Files(new CommunityPackLocalFile("/cache/downloads/whatever.bin", ShaA)));

			Assert.Empty(plan.Pending);
			Assert.Equal("/cache/downloads/whatever.bin", plan.Resolved["bios"]);
		}

		[Fact]
		public void PackFolderWinsOverDownloadsCache()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, System.Array.Empty<string>(),
				Files(new CommunityPackLocalFile("/mep/bios.bin", ShaA)),
				Files(new CommunityPackLocalFile("/cache/downloads/bios.bin", ShaA)));

			Assert.Equal("/mep/bios.bin", plan.Resolved["bios"]);
		}

		[Fact]
		public void DependencyAbsent_BecomesAPromptCarryingHintsAndLicense()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA, "CC-BY-4.0", new[] { "look here", "or here" }) },
				System.Array.Empty<string>(), None(), None());

			Assert.Empty(plan.Resolved);
			CommunityPackPendingDep pending = Assert.Single(plan.Pending);
			Assert.Equal("bios", pending.DepId);
			Assert.Equal("look here, or here", pending.Hints);
			Assert.Equal("CC-BY-4.0", pending.License);
		}

		[Fact]
		public void DependencyAbsentWithNoDeclaredLicense_PromptsWithNotDeclared()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, System.Array.Empty<string>(), None(), None());

			Assert.Equal(CommunityPackDepResolver.LicenseNotDeclared, Assert.Single(plan.Pending).License);
		}

		[Fact]
		public void DependenciesPartiallyPresent_ResolvesOneAndPromptsForTheOther()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("have", ShaA), Dep("missing", ShaB) }, System.Array.Empty<string>(), None(),
				Files(new CommunityPackLocalFile("/cache/downloads/have.bin", ShaA)));

			Assert.Equal("/cache/downloads/have.bin", plan.Resolved["have"]);
			Assert.False(plan.Resolved.ContainsKey("missing"));
			Assert.Equal("missing", Assert.Single(plan.Pending).DepId);
		}

		[Fact]
		public void HashMismatch_DoesNotResolve()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, System.Array.Empty<string>(), None(),
				Files(new CommunityPackLocalFile("/cache/downloads/other.bin", ShaB)));

			Assert.Empty(plan.Resolved);
			Assert.Equal("bios", Assert.Single(plan.Pending).DepId);
		}

		[Fact]
		public void WrongBytesRightName_DoesNotResolve()
		{
			//Negative control: the resolver matches by content hash, never by
			//name. A file the user dropped under the dep's exact id/file name but
			//whose bytes hash to something else stays a prompt.
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, System.Array.Empty<string>(), None(),
				Files(new CommunityPackLocalFile("/cache/downloads/bios", ShaB)));

			Assert.Empty(plan.Resolved);
			Assert.Equal("bios", Assert.Single(plan.Pending).DepId);
		}

		[Fact]
		public void HexCaseIsNotNormativeOnRead()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA.ToUpperInvariant()) }, System.Array.Empty<string>(), None(),
				Files(new CommunityPackLocalFile("/cache/downloads/bios.bin", ShaA)));

			Assert.Equal("/cache/downloads/bios.bin", plan.Resolved["bios"]);
		}

		[Fact]
		public void AlreadyResolvedDep_IsNeitherReResolvedNorPrompted()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("bios", ShaA) }, new[] { "bios" }, None(),
				Files(new CommunityPackLocalFile("/cache/downloads/bios.bin", ShaA)));

			Assert.Empty(plan.Resolved);
			Assert.Empty(plan.Pending);
		}

		[Fact]
		public void DepWithoutIdOrSha256_IsSkippedSilently()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(
				new[] { Dep("", ShaA), Dep("nohash", "") }, System.Array.Empty<string>(), None(), None());

			Assert.Empty(plan.Resolved);
			Assert.Empty(plan.Pending);
		}

		[Fact]
		public void NoDeps_IsAnEmptyPlan()
		{
			CommunityPackDepPlanResult plan = CommunityPackDepPlan.Build(null, System.Array.Empty<string>(), None(), None());
			Assert.Empty(plan.Resolved);
			Assert.Empty(plan.Pending);

			plan = CommunityPackDepPlan.Build(System.Array.Empty<CommunityPackDep>(), System.Array.Empty<string>(), None(), None());
			Assert.Empty(plan.Resolved);
			Assert.Empty(plan.Pending);
		}
	}
}
