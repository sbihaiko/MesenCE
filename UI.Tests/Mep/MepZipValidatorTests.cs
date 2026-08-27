using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//Fase 1 (docs/roadmap/plano-testes-unitarios.md): exercises UI/Logic/MepZipValidator.cs entirely in-memory - no filesystem zip, no host, no Avalonia/EmuApi.
	//Split across this file and MepZipValidatorStructuralFallbackTests.cs (same partial class, ADR-0120 structural
	//fallback cases) purely to stay under the 200-line-per-file cap - BuildZip/FindRepoRoot below are shared by both.
	public partial class MepZipValidatorTests
	{
		//Every convention-layout probe MepPack::DetectConventionLayout recognizes (Core/Shared/EnhancementPacks/MepPack.cpp
		//kConventionProbe), plus the audio/fingerprints.json alternative (ADR-0047), each also checked in its `auto/` form.
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

		//ADR-0120 structural fallback cases (StructuralFallbackCases, Validate_HandlesStructuralFallbackCases,
		//FindStructuralFallbackPrefix_ReturnsPackRootNotAutoLayerFolder) live in
		//MepZipValidatorStructuralFallbackTests.cs, a second file of this same partial class.

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

		//A zip-slip path smuggled alongside a perfectly valid pack.json layer must still fail the whole archive - Validate
		//walks every entry, not just the layer probes.
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

		//Control characters aren't part of the shared fixture (raw control bytes in a TAB-separated text file are fragile
		//across editors/git) - covered directly here instead, via escape sequences.
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

		//Builds an in-memory zip with the given (entryName, textContent) pairs. Entry names are stored verbatim (including
		//"bad" ones under test) - the zip format itself does not validate them, only MepZipValidator does.
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

		//UI.Tests runs from bin/<config>/net10.0/ inside whichever checkout (worktree or main tree) built it - walk up to
		//the nearest Mesen.sln instead of hardcoding an absolute repo path.
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
