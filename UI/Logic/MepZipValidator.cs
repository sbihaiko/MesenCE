using System;
using System.Collections.Generic;
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

		//Bare leaf names of the probes above (ADR-0121, extending ADR-0120
		//§3's structural fallback): a classic Mesen HD pack (hires.txt at a
		//wrapper folder's own root, no textures/ wrapper at all) whose
		//wrapper is named after a release/repo rather than the ROM - e.g. a
		//raw GitHub archive download's "<Repo>-<branch>/hires.txt" - has no
		//textures/audio/synth shape and no ROM name for this validator to
		//anchor on (see ADR-0120 §3), so only a bare-basename match can ever
		//discover it. Mirrors scripts/mep_lint.py's FALLBACK_PROBE_BASENAMES;
		//see community-pack issues #46/#47 for the real fixtures that
		//motivated this.
		private static readonly string[] LegacyProbeBasenames = new[] {
			"hires.txt",
			"preset.cfg",
			"fingerprints.json",
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

		//Name-agnostic, last-priority fallback (ADR-0120, extended by
		//ADR-0121 to LegacyProbeBasenames): when the zip has no layer at its
		//root, look for exactly one subfolder anywhere in the entry list
		//(depth/entry-capped) that itself directly contains pack.json, one of
		//the LayerProbes (human or auto/ layer), or a bare LegacyProbeBasenames
		//leaf with no wrapper. Unlike the C++ core's
		//MepPackManager::FindFallbackSubfolder, this call site has no ROM name
		//to match against - it is purely structural - so more than one
		//candidate subfolder is ambiguous and is refused rather than guessed
		//at, keeping the same fail-closed philosophy as the exact-name match.
		//Returns the discovered prefix, or null when no unambiguous candidate
		//exists.
		private static string? FindStructuralFallbackPrefix(ZipArchive zip)
		{
			string[] suffixes = LayerProbes
				.SelectMany(probe => new[] { probe, "auto/" + probe })
				.Concat(LegacyProbeBasenames)
				.Append("pack.json")
				.ToArray();

			if(zip.Entries.Count > FallbackMaxEntries) {
				//Fail closed: too many entries to search safely rather than
				//silently searching only a prefix of them.
				return null;
			}

			//Folders that directly hold at least one image, for the
			//bare-hires.txt qualification below. Mirrors scripts/mep_lint.py.
			HashSet<string> foldersWithImages = new();
			foreach(ZipArchiveEntry entry in zip.Entries) {
				string normalized = entry.FullName.Replace('\\', '/');
				int slash = normalized.LastIndexOf('/');
				if(slash > 0 && normalized.EndsWith(".png", StringComparison.OrdinalIgnoreCase)) {
					foldersWithImages.Add(normalized.Substring(0, slash));
				}
			}

			string? candidate = null;
			foreach(ZipArchiveEntry entry in zip.Entries) {
				string? prefix = MatchCandidatePrefix(entry.FullName, suffixes);
				if(prefix == null || prefix.Length == 0) {
					continue;
				}
				if(entry.FullName.Replace('\\', '/') == prefix + "/hires.txt" && !foldersWithImages.Contains(prefix)) {
					//A folder holding a bare hires.txt and no image beside it is
					//a variant manifest, not a pack root: in an HD Mesen pack the
					//PNGs are siblings of hires.txt, so such a folder cannot
					//resolve a single <img>/<background>. Counting them as roots
					//made a one-game pack look ambiguous and failed discovery on
					//a pack with 1222 PNGs (#161). The wrapper shapes
					//(textures/hires.txt, pack.json, ...) are an explicit layout
					//declaration and keep their old meaning.
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
		//Every bare probe suffix ("textures/hires.txt") is itself a trailing
		//substring of its `auto/` counterpart ("auto/textures/hires.txt"), so an
		//entry inside the auto/ layer matches both - e.g.
		//"W/auto/textures/hires.txt" ends with "/textures/hires.txt" too. Taking
		//the bare match alone would wrongly return "W/auto" as the pack root
		//instead of "W". Picking the LONGEST matching suffix fixes that: the
		//more specific auto/ suffix wins and strips down to "W", which also
		//makes a pack root that carries both layers of the same section
		//(MEP-v1.md's human+auto layering, ADR-0047/ADR-0049) resolve every
		//entry to the same candidate "W" instead of splitting into "W" and
		//"W/auto" and tripping the ambiguity check below.
		private static string? MatchCandidatePrefix(string entryFullName, string[] suffixes)
		{
			string normalized = entryFullName.Replace('\\', '/');
			if(normalized.Split('/').Length > FallbackMaxDepth) {
				return null;
			}

			string? bestPrefix = null;
			int bestSuffixLength = -1;
			foreach(string suffix in suffixes) {
				if(suffix.Length > bestSuffixLength && normalized.EndsWith("/" + suffix)) {
					bestSuffixLength = suffix.Length;
					bestPrefix = normalized.Substring(0, normalized.Length - suffix.Length - 1);
				}
			}

			return bestPrefix;
		}

		//Test-facing / reusable pure predicate (ADR-0125): public so
		//UI.Tests drives it row-by-row over docs/specs/golden/mep/path-cases.txt
		//without building a ZipArchive per row; the production entry point is
		//Validate(ZipArchive), this stays a documented reusable helper.
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
