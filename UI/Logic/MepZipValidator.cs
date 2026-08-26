using System.IO.Compression;
using System.Linq;

namespace Mesen.Logic
{
	//Host-free MEP zip validator (Fase 1, docs/roadmap/plano-testes-unitarios.md).
	//BCL + System.IO.Compression only, per the UI/Logic/ firewall contract - so
	//this file dual-compiles unmodified into UI.Tests (see UI.Tests/UI.Tests.csproj).
	//
	//Mirrors MepPack::DetectConventionLayout (Core/Shared/EnhancementPacks/MepPack.cpp):
	//a zip is a valid pack if it has pack.json at the root, or a probe file for
	//one of the three convention sections (ADR-0049), in either the human or
	//the `auto/` layer. The audio section additionally accepts fingerprints.json
	//in place of hires.txt (ADR-0047) - this was the one gap between the C++
	//core loader and the old inline UI check, closed here.
	public static class MepZipValidator
	{
		//Convention-layout probe files (Core kConventionProbe, plus the
		//audio/fingerprints.json alternative from ADR-0047).
		private static readonly string[] LayerProbes = new[] {
			"textures/hires.txt",
			"audio/hires.txt",
			"audio/fingerprints.json",
			"synth/preset.cfg",
		};

		//Structural fallback search limits (ADR-0120). Mirrored numerically (not
		//algorithmically - see the ADR for the C++-vs-validators asymmetry) by
		//Core::MepPackManager::FindFallbackSubfolder and scripts/mep_lint.py's
		//own copies of these same two constants, so the fallback's search cost
		//is bounded the same way everywhere.
		//"Depth" = number of '/'-separated path segments in a normalized zip
		//entry, e.g. "Contra80s-v1.1/Contra (U) [!]/textures/hires.txt" is
		//depth 4.
		private const int FallbackMaxDepth = 4;
		private const int FallbackMaxEntries = 2000;

		//Validates a MEP pack zip already opened for reading. Returns null when
		//the archive is an acceptable pack; otherwise a message ID from the
		//existing UI string table describing why it was rejected.
		public static string? Validate(ZipArchive zip)
		{
			if(!HasAnyLayer(zip) && FindStructuralFallbackPrefix(zip) == null) {
				return "InstallMepPackInvalidPack";
			}

			foreach(ZipArchiveEntry entry in zip.Entries) {
				if(!IsSafePath(entry.FullName)) {
					return "InstallMepPackInvalidPack";
				}
			}

			return null;
		}

		private static bool HasAnyLayer(ZipArchive zip)
		{
			if(zip.GetEntry("pack.json") != null) {
				return true;
			}

			foreach(string probe in LayerProbes) {
				if(zip.GetEntry(probe) != null || zip.GetEntry("auto/" + probe) != null) {
					return true;
				}
			}

			return false;
		}

		//Name-agnostic, last-priority fallback (ADR-0120): when the zip has no
		//layer at its root, look for exactly one subfolder anywhere in the
		//entry list (depth/entry-capped) that itself directly contains
		//pack.json or one of the LayerProbes (human or auto/ layer). Unlike the
		//C++ core's MepPackManager::FindFallbackSubfolder, this call site has
		//no ROM name to match against - it is purely structural - so more than
		//one candidate subfolder is ambiguous and is refused rather than
		//guessed at, keeping the same fail-closed philosophy as the exact-name
		//match. Returns the discovered prefix, or null when no unambiguous
		//candidate exists.
		private static string? FindStructuralFallbackPrefix(ZipArchive zip)
		{
			string[] suffixes = LayerProbes
				.SelectMany(probe => new[] { probe, "auto/" + probe })
				.Append("pack.json")
				.ToArray();

			string? candidate = null;
			int visited = 0;
			foreach(ZipArchiveEntry entry in zip.Entries) {
				if(++visited > FallbackMaxEntries) {
					//Fail closed: too many entries to search safely rather than
					//silently searching only a prefix of them.
					return null;
				}

				string? prefix = MatchCandidatePrefix(entry.FullName, suffixes);
				if(prefix == null || prefix.Length == 0) {
					continue;
				}
				if(candidate != null && candidate != prefix) {
					//Ambiguous: two structurally distinct candidate roots.
					return null;
				}
				candidate = prefix;
			}
			return candidate;
		}

		//Returns the leading path prefix of entryFullName when it ends with one
		//of the given probe suffixes and its own segment depth is within
		//FallbackMaxDepth, or null when it does not match / is too deep.
		private static string? MatchCandidatePrefix(string entryFullName, string[] suffixes)
		{
			string normalized = entryFullName.Replace('\\', '/');
			if(normalized.Split('/').Length > FallbackMaxDepth) {
				return null;
			}

			foreach(string suffix in suffixes) {
				if(normalized.EndsWith("/" + suffix)) {
					return normalized.Substring(0, normalized.Length - suffix.Length - 1);
				}
			}

			return null;
		}

		//Rejects zip-slip entry names: absolute paths (leading '/'), a colon
		//anywhere (Windows drive letters and NTFS alternate data streams alike),
		//any ".." path segment (checked after normalizing '\' to '/', since a
		//zip built on Windows may use either separator), and raw control
		//characters (< 0x20) that a downstream extractor could mishandle.
		public static bool IsSafePath(string entryFullName)
		{
			string normalized = entryFullName.Replace('\\', '/');
			if(normalized.StartsWith("/") || normalized.Contains(':')) {
				return false;
			}

			if(normalized.Split('/').Contains("..")) {
				return false;
			}

			foreach(char c in normalized) {
				if(c < 0x20) {
					return false;
				}
			}

			return true;
		}
	}
}
