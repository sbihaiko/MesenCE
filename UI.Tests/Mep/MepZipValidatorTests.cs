using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//Fase 1: exercises UI/Logic/MepZipValidator.cs entirely in-memory - no filesystem zip, no host, no Avalonia/EmuApi.
	public class MepZipValidatorTests
	{
		//Every probe MepPack::DetectConventionLayout recognizes plus audio/fingerprints.json (ADR-0047), also in `auto/` form.
		public static IEnumerable<object[]> LayerProbes()
		{
			string[] probes = {
				"pack.json",
				"textures/hires.txt",
				"audio/hires.txt",
				"audio/fingerprints.json",
				"synth/preset.cfg",
				"auto/textures/hires.txt",
				"auto/audio/hires.txt",
				"auto/audio/fingerprints.json",
				"auto/synth/preset.cfg",
			};
			foreach(string probe in probes) {
				yield return new object[] { probe };
			}
		}

		[Theory]
		[MemberData(nameof(LayerProbes))]
		public void Validate_AcceptsEveryDocumentedLayerProbe(string probeEntryName)
		{
			using ZipArchive zip = BuildZip((probeEntryName, "x"));
			Assert.Null(MepZipValidator.Validate(zip));
		}

		[Fact]
		public void Validate_AcceptsGoldenFingerprintsJsonFixture()
		{
			string goldenPath = Path.Combine(FindRepoRoot(), "docs", "specs", "golden", "mep", "audio", "fingerprints.json");
			string goldenContent = File.ReadAllText(goldenPath);
			Assert.Contains("\"version\": 1", goldenContent);
			using ZipArchive zip = BuildZip(("audio/fingerprints.json", goldenContent));
			Assert.Null(MepZipValidator.Validate(zip));
		}

		[Fact]
		public void Validate_RejectsZipWithNoRecognizedLayer()
		{
			using ZipArchive zip = BuildZip(("readme.txt", "not a pack"), ("textures/Tiles_00_0.png", "x"));
			Assert.Equal("InstallMepPackInvalidPack", MepZipValidator.Validate(zip));
		}

		[Fact]
		public void Validate_RejectsAnEmptyZip()
		{
			using ZipArchive zip = BuildZip();
			Assert.Equal("InstallMepPackInvalidPack", MepZipValidator.Validate(zip));
		}

		//ADR-0120 structural (name-agnostic) fallback: no ROM name here (unlike Core's MepPackManager::FindFallbackSubfolder),
		//so it accepts exactly one unambiguous subfolder holding a layer probe, depth/entry-capped via FallbackMaxDepth/
		//FallbackMaxEntries. Root-level regressions (pack.json, synth/preset.cfg for zip-named-as-ROM) already run above.
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
			//Both layers of a section under one subfolder is one candidate root, not two - regression: the bare
			//suffix ("textures/hires.txt") trailing-matches the auto/ entry too, splitting "W"/"W/auto" before.
			yield return new object[] { new[] { ("W/textures/hires.txt", "x"), ("W/auto/textures/hires.txt", "x") }, true };
			yield return new object[] { new[] { ("W/audio/hires.txt", "x"), ("W/auto/audio/hires.txt", "x") }, true };
			//Only the auto/ layer present is still one candidate root (not split into "root" and "root/auto").
			yield return new object[] { new[] { ("W/auto/textures/hires.txt", "x") }, true };
			//ADR-0121: a classic Mesen HD pack (hires.txt loose at a wrapper folder's own root, no textures/
			//wrapper) whose wrapper is named after a release/repo, not the ROM - the real shape of a raw
			//GitHub archive download (see community-pack issues #46/#47). No textures/ wrapper exists for the
			//pre-ADR-0121 structural test to key off, so only the bare-basename acceptance finds it.
			yield return new object[] { new[] { ("HDNes-Graphics-Pac-master/hires.txt", "x"), ("HDNes-Graphics-Pac-master/Chr_00_0.png", "x") }, true };
			yield return new object[] { new[] { ("Wrapper/preset.cfg", "x") }, true };
			yield return new object[] { new[] { ("Wrapper/fingerprints.json", "x") }, true };
			//Two distinct repo-named wrappers, each with its own loose root hires.txt: ambiguous, must reject.
			//Each carries a PNG so both stay real candidates under the #161 qualification below - without one
			//they would be rejected for having no candidate at all, and this row would stop testing ambiguity.
			yield return new object[] { new[] { ("RepoA-main/hires.txt", "x"), ("RepoA-main/Chr_00_0.png", "x"), ("RepoB-master/hires.txt", "x"), ("RepoB-master/Chr_00_0.png", "x") }, false };
			//#161: a folder holding a bare hires.txt and no image beside it is a variant manifest, not a pack
			//root - in an HD Mesen pack the PNGs are siblings of hires.txt, so it cannot resolve a single
			//<img>/<background>. Counting those made a one-game pack that ships alternate manifests next to a
			//patch (issue #138's "Customization/Patch - Music .../") look ambiguous and failed discovery.
			yield return new object[] { new[] { ("W/hires.txt", "x"), ("W/Chr_00_0.png", "x"), ("W/Custom/A/hires.txt", "x"), ("W/Custom/A/p.ips", "x") }, true };
			//The qualification is not a licence to accept a manifest-only archive: still nothing to resolve.
			yield return new object[] { new[] { ("W/Custom/A/hires.txt", "x"), ("W/Custom/A/p.ips", "x") }, false };
		}

		[Theory]
		[MemberData(nameof(StructuralFallbackCases))]
		public void Validate_HandlesStructuralFallbackCases((string, string)[] entries, bool expectedAccept)
		{
			using ZipArchive zip = BuildZip(entries);
			Assert.Equal(expectedAccept, MepZipValidator.Validate(zip) == null);
		}

		public static IEnumerable<object[]> FixtureCases()
		{
			foreach((string path, bool ok) in LoadPathCasesFixture()) {
				yield return new object[] { path, ok };
			}
		}

		[Theory]
		[MemberData(nameof(FixtureCases))]
		public void IsSafePath_MatchesSharedFixtureVerdict(string path, bool expectedOk)
		{
			Assert.Equal(expectedOk, MepZipValidator.IsSafePath(path));
		}

		//A zip-slip path alongside a valid pack.json layer must still fail - Validate walks every entry.
		[Theory]
		[MemberData(nameof(FixtureCases))]
		public void Validate_HonorsFixtureVerdictEvenWithAValidLayerPresent(string path, bool expectedOk)
		{
			using ZipArchive zip = BuildZip(("pack.json", "{}"), (path, "x"));
			string? result = MepZipValidator.Validate(zip);
			if(expectedOk) {
				Assert.Null(result);
			} else {
				Assert.Equal("InstallMepPackInvalidPack", result);
			}
		}

		//Control characters aren't in the shared fixture (fragile as raw bytes in a TAB-separated file) - covered here.
		[Theory]
		[InlineData('\u0000')]
		[InlineData('\u0001')]
		[InlineData('\t')]
		[InlineData('\u001f')]
		public void IsSafePath_RejectsControlCharacters(char controlChar)
		{
			Assert.False(MepZipValidator.IsSafePath("textures/bad" + controlChar + "name.txt"));
		}

		[Fact]
		public void IsSafePath_AcceptsPrintableCharactersDownTo0x20()
		{
			Assert.True(MepZipValidator.IsSafePath("textures/has space.txt"));
		}

		[Fact]
		public void PathCasesFixture_ContainsTheDocumentedRequiredCases()
		{
			List<(string path, bool ok)> cases = LoadPathCasesFixture().ToList();
			Assert.Contains(cases, c => c.path == "../x" && !c.ok);
			Assert.Contains(cases, c => c.path.Contains("/abs") && !c.ok);
		}

		private static List<(string path, bool ok)> LoadPathCasesFixture()
		{
			string fixturePath = Path.Combine(FindRepoRoot(), "docs", "specs", "golden", "mep", "path-cases.txt");
			var cases = new List<(string, bool)>();
			foreach(string rawLine in File.ReadAllLines(fixturePath)) {
				string line = rawLine.Trim();
				if(line.Length == 0 || line.StartsWith("#")) {
					continue;
				}
				string[] parts = line.Split('\t');
				Assert.Equal(2, parts.Length);
				bool ok = parts[1] switch {
					"ok" => true,
					"bad" => false,
					_ => throw new InvalidDataException($"path-cases.txt: unknown verdict '{parts[1]}' for '{parts[0]}'")
				};
				cases.Add((parts[0], ok));
			}
			return cases;
		}

		//Builds an in-memory zip from (entryName, textContent) pairs, stored verbatim - only MepZipValidator
		//validates names, not the zip format.
		private static ZipArchive BuildZip(params (string name, string content)[] entries)
		{
			var stream = new MemoryStream();
			using(var writer = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: true)) {
				foreach((string name, string content) in entries) {
					ZipArchiveEntry entry = writer.CreateEntry(name);
					using Stream entryStream = entry.Open();
					using var textWriter = new StreamWriter(entryStream);
					textWriter.Write(content);
				}
			}
			stream.Position = 0;
			return new ZipArchive(stream, ZipArchiveMode.Read);
		}

		//UI.Tests runs from bin/<config>/net10.0/ inside whichever checkout built it - walk up to the nearest
		//Mesen.sln instead of hardcoding an absolute repo path.
		private static string FindRepoRoot()
		{
			DirectoryInfo? dir = new DirectoryInfo(AppContext.BaseDirectory);
			while(dir != null && !File.Exists(Path.Combine(dir.FullName, "Mesen.sln"))) {
				dir = dir.Parent;
			}
			if(dir == null) {
				throw new InvalidOperationException("Could not locate repo root (Mesen.sln) from " + AppContext.BaseDirectory);
			}
			return dir.FullName;
		}
	}
}
