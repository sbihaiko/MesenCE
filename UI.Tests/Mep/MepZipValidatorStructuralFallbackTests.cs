using System.Collections.Generic;
using System.IO.Compression;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//ADR-0120 structural (name-agnostic) fallback cases for UI/Logic/MepZipValidator.cs, split out from
	//MepZipValidatorTests.cs (same partial class - BuildZip below is defined there and shared) to keep both files
	//under the 200-line-per-file cap.
	public partial class MepZipValidatorTests
	{
		//No ROM name here, unlike Core's MepPackManager::FindFallbackSubfolder: accepts one unambiguous subfolder
		//holding a layer probe, depth/entry-capped via FallbackMaxDepth/FallbackMaxEntries. Root-level regressions
		//(pack.json, synth/preset.cfg standing in for zip-named-as-ROM) already run via
		//Validate_AcceptsEveryDocumentedLayerProbe in MepZipValidatorTests.cs.
		public static IEnumerable<object[]> StructuralFallbackCases()
		{
			yield return new object[] { new[] { ("P/readme.txt", "n"), ("P/Game/textures/hires.txt", "x") }, true };
			yield return new object[] { new[] { ("A/textures/hires.txt", "x"), ("B/textures/hires.txt", "x") }, false }; //ambiguous
			yield return new object[] { new[] { ("A/B/C/textures/hires.txt", "x") }, false }; //depth 5 > FallbackMaxDepth (4)

			var overCap = new List<(string, string)>();
			for(int i = 0; i < 2001; i++) {
				overCap.Add(($"filler/decoy{i}.txt", "x"));
			}
			overCap.Add(("P/Game/textures/hires.txt", "x"));
			yield return new object[] { overCap.ToArray(), false }; //2001 entries > FallbackMaxEntries (2000)

			//A subfolder carrying BOTH the human and auto/ layer of the same section (MEP-v1.md's human+auto
			//layering, ADR-0047/ADR-0049) is one candidate pack root, not two - regression for the bug where the
			//bare probe suffix ("textures/hires.txt") matched the auto/ entry too (it's a trailing substring of
			//"auto/textures/hires.txt"), splitting "W" and "W/auto" into a false ambiguity.
			yield return new object[] { new[] { ("W/textures/hires.txt", "x"), ("W/auto/textures/hires.txt", "x") }, true };
			yield return new object[] { new[] { ("W/audio/hires.txt", "x"), ("W/auto/audio/hires.txt", "x") }, true };

			//Only the auto/ layer present: the discovered prefix must be the pack root "W", not the layer
			//folder "W/auto" - verified indirectly here via acceptance, and directly via reflection below.
			yield return new object[] { new[] { ("W/auto/textures/hires.txt", "x") }, true };
		}

		[Theory]
		[MemberData(nameof(StructuralFallbackCases))]
		public void Validate_HandlesStructuralFallbackCases((string, string)[] entries, bool expectedAccept)
		{
			using ZipArchive zip = BuildZip(entries);
			Assert.Equal(expectedAccept, MepZipValidator.Validate(zip) == null);
		}

		//Same auto-only-layer shape as the last StructuralFallbackCases entry, but asserting the actual returned
		//prefix (via reflection, since FindStructuralFallbackPrefix is private) rather than just acceptance - the
		//discovered prefix feeds NormalizeRelativePath as a real extraction-root path in the C++ mirror
		//(MepPackManager::FindFallbackSubfolder) and in scripts/mep_lint.py, so "W/auto" instead of "W" would be
		//silently wrong there even though Validate() would still accept the zip either way.
		[Fact]
		public void FindStructuralFallbackPrefix_ReturnsPackRootNotAutoLayerFolder()
		{
			using ZipArchive zip = BuildZip(("W/auto/textures/hires.txt", "x"));
			var method = typeof(MepZipValidator).GetMethod("FindStructuralFallbackPrefix",
				System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
			Assert.NotNull(method);
			string? prefix = (string?)method!.Invoke(null, new object[] { zip });
			Assert.Equal("W", prefix);
		}
	}
}
