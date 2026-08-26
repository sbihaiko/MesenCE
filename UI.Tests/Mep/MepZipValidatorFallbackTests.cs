using System.Collections.Generic;
using System.IO.Compression;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//ADR-0120: last-priority, name-agnostic structural fallback in
	//UI/Logic/MepZipValidator.cs, plus regression coverage confirming the
	//existing conventions still classify unchanged. Partial-class sibling of
	//MepZipValidatorTests.cs, reusing its private BuildZip/FindRepoRoot helpers.
	public partial class MepZipValidatorTests
	{
		//Mirrors a TasticHacks/Contra80s-style release zip that ships wrapped
		//in a version folder plus the ROM's own display-name folder, with
		//nothing recognizable at the zip root - MepZipValidator has no ROM
		//name to match by name (unlike Core's
		//MepPackManager::FindFallbackSubfolder), so it falls back to finding
		//the single unambiguous subfolder that itself directly contains a
		//convention probe.
		[Fact]
		public void Validate_AcceptsContra80sShapedStructuralFallback()
		{
			using ZipArchive zip = BuildZip(
				("Contra80s-v1.1/readme.txt", "not a layer"),
				("Contra80s-v1.1/Contra (U) [!]/textures/hires.txt", "x"),
				("Contra80s-v1.1/Contra (U) [!]/audio/hires.txt", "x"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Null(result);
		}

		//Two subfolders each independently look like a valid pack root; with
		//no ROM name to disambiguate with, the fallback refuses to guess and
		//the whole archive is rejected - same fail-closed philosophy as the
		//exact-name convention it extends.
		[Fact]
		public void Validate_RejectsAmbiguousStructuralFallbackWithTwoCandidates()
		{
			using ZipArchive zip = BuildZip(
				("Bundle/GameOne/textures/hires.txt", "x"),
				("Bundle/GameTwo/textures/hires.txt", "x"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Equal("InstallMepPackInvalidPack", result);
		}

		//FallbackMaxDepth (4) counts '/'-separated path segments in the
		//normalized entry: "A/B/C/textures/hires.txt" is depth 5, one past
		//the cap, so the "A/B/C" subfolder it would otherwise resolve to is
		//never considered a candidate.
		[Fact]
		public void Validate_RejectsStructuralFallbackCandidateBeyondMaxDepth()
		{
			using ZipArchive zip = BuildZip(("A/B/C/textures/hires.txt", "x"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Equal("InstallMepPackInvalidPack", result);
		}

		//FallbackMaxEntries (2000) bounds how many entries the structural
		//fallback will scan; a zip with more entries than that fails closed
		//rather than silently only searching a prefix of them - the one
		//legitimate candidate placed after the cap is never reached.
		[Fact]
		public void Validate_FailsClosedWhenEntryCountExceedsFallbackMaxEntries()
		{
			var entries = new List<(string, string)>();
			for(int i = 0; i < 2001; i++) {
				entries.Add(($"filler/decoy{i}.txt", "x"));
			}
			entries.Add(("Contra80s-v1.1/Contra (U) [!]/textures/hires.txt", "x"));

			using ZipArchive zip = BuildZip(entries.ToArray());

			string? result = MepZipValidator.Validate(zip);

			Assert.Equal("InstallMepPackInvalidPack", result);
		}

		//Existing-convention regressions: MepZipValidator has no filesystem or
		//ROM-name context (sibling-folder placement and zip-filename-equals-ROM
		//matching both happen in Core::MepPackManager::PrepareZip, not here),
		//so from its perspective every one of ADR-0040/ADR-0049's conventions
		//is just a root-level layer - confirm the new fallback code path added
		//above didn't change that.
		[Fact]
		public void Validate_SiblingFolderConventionZip_StillAccepted()
		{
			using ZipArchive zip = BuildZip(("pack.json", "{}"), ("textures/hires.txt", "x"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Null(result);
		}

		[Fact]
		public void Validate_RootPackJsonConventionZip_StillAccepted()
		{
			using ZipArchive zip = BuildZip(("pack.json", "{}"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Null(result);
		}

		[Fact]
		public void Validate_ZipNamedAsRomConventionZip_StillAccepted()
		{
			using ZipArchive zip = BuildZip(("synth/preset.cfg", "x"));

			string? result = MepZipValidator.Validate(zip);

			Assert.Null(result);
		}
	}
}
