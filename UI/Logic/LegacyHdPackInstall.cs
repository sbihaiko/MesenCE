using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Mesen.Logic
{
	//Host-free helpers for installing legacy HD packs (MEI-v1.md §2.3
	//`kind: "hd-legacy"` - a plain hires.txt pack with no MEP recipe): finding
	//the pack root inside a zip and zip-slip-safe path normalization. BCL only
	//(no Avalonia/EmuApi), so this file dual-compiles into UI.Tests and any
	//accidental host dependency breaks `dotnet test`. Mirrors the core's rules:
	//MepPack::NormalizeRelativePath (spec §6) and the rom-name-anchored root
	//discovery of MepPack::FindFallbackSubfolder / MepRecipeOps::DiscoverPrimaryRoot
	//(ADR-0120). The UI/Services coordinator opens the zip file;
	//ExtractToFolder unwraps a nested zip (if any) and writes the pack root.
	public static class LegacyHdPackInstall
	{
		//Mirror of MepPack::NormalizeRelativePath (zip-slip): reject absolute
		//paths, drive letters, control characters and any "."/".." segment;
		//return the normalized '/' path, or null to refuse the whole entry.
		public static string? NormalizeZipPath(string path)
		{
			string work = path.Replace('\\', '/');
			if(work.StartsWith("/", StringComparison.Ordinal) || work.Contains(':')) {
				return null;
			}
			foreach(char c in work) {
				if(c < 0x20) {
					return null;
				}
			}
			StringBuilder sb = new();
			foreach(string part in work.Split('/')) {
				if(part.Length == 0 || part == ".") {
					continue;
				}
				if(part == "..") {
					return null;
				}
				if(sb.Length > 0) {
					sb.Append('/');
				}
				sb.Append(part);
			}
			return sb.Length == 0 ? null : sb.ToString();
		}

		//The single root-level (no '/') ".zip" entry of a wrapper zip, or null
		//when there are zero or several - mirrors MepRecipeOps::FindTopLevelNestedZip
		//(the "UnZipMeFirst"-style release that wraps the actual HD pack in a
		//nested zip; case-insensitive on the extension).
		public static string? FindNestedZip(IEnumerable<string> normalizedEntries)
		{
			string? candidate = null;
			foreach(string entry in normalizedEntries) {
				if(entry.Length == 0 || entry.Contains('/')) {
					continue; //not a root-level entry
				}
				if(!entry.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)) {
					continue;
				}
				if(candidate != null) {
					return null; //more than one root-level zip - ambiguous
				}
				candidate = entry;
			}
			return candidate;
		}

		//The pack root = the parent prefix of every hires.txt entry. Prefers
		//the prefix whose leaf folder name equals the loaded ROM name (the
		//artist's per-ROM folder, as FindRomNameAnchor looks for); otherwise
		//the shallowest; a root-level hires.txt makes the root the zip ("").
		//Returns null when the zip has no hires.txt at all.
		public static string? FindPackRoot(IEnumerable<string> normalizedEntries, string romName)
		{
			List<string> hireRoots = new();
			foreach(string entry in normalizedEntries) {
				string name = entry.Substring(entry.LastIndexOf('/') + 1);
				if(!string.Equals(name, "hires.txt", StringComparison.OrdinalIgnoreCase)) {
					continue;
				}
				string prefix = ParentPrefix(entry);
				if(!hireRoots.Contains(prefix)) {
					hireRoots.Add(prefix);
				}
			}
			if(hireRoots.Count == 0) {
				return null;
			}

			//Prefer the prefix whose leaf folder equals the loaded ROM name.
			foreach(string prefix in hireRoots) {
				if(string.Equals(LeafFolder(prefix), romName, StringComparison.OrdinalIgnoreCase)) {
					return prefix;
				}
			}

			//Shallowest otherwise ("" = zip root always wins).
			string? best = null;
			foreach(string prefix in hireRoots) {
				if(best == null || prefix.Length < best.Length) {
					best = prefix;
				}
			}
			return best;
		}

		//Parent folder prefix of a normalized '/' path: "" for a root file,
		//"a/b/" for "a/b/file". Trailing slash kept so a rel path prefixes onto it.
		private static string ParentPrefix(string norm)
		{
			int idx = norm.LastIndexOf('/');
			return idx < 0 ? "" : norm.Substring(0, idx + 1);
		}

		//Last segment of a root prefix ("a/b/" -> "b", "" -> "").
		private static string LeafFolder(string prefix)
		{
			string trimmed = prefix.TrimEnd('/');
			int idx = trimmed.LastIndexOf('/');
			return idx < 0 ? trimmed : trimmed.Substring(idx + 1);
		}

		//Test-facing / reusable (ADR-0125): extract the pack root of an already-
		//open zip into targetFolder. A wrapper with one root-level nested zip
		//(Zelda Remastered's Drive release) is unwrapped in memory and written
		//while that inner ZipArchive is still open — ZipArchiveEntry.Open throws
		//ObjectDisposedException after Dispose. Returns false (with error) when
		//the zip is empty, zip-slip, or has no hires.txt.
		public static bool ExtractToFolder(ZipArchive zip, string targetFolder, string romName, out string error)
		{
			Dictionary<string, ZipArchiveEntry>? byNorm = BuildNormMap(zip, out error);
			if(byNorm == null || byNorm.Count == 0) {
				if(byNorm != null) {
					error = "zip is empty";
				}
				return false;
			}

			string? rootPrefix = FindPackRoot(byNorm.Keys, romName);
			if(rootPrefix != null) {
				WriteUnderRoot(byNorm, rootPrefix, targetFolder);
				return true;
			}

			string? nested = FindNestedZip(byNorm.Keys);
			if(nested == null || !byNorm.TryGetValue(nested, out ZipArchiveEntry? nestedEntry)) {
				error = "not a legacy HD pack (no hires.txt)";
				return false;
			}

			byte[] nestedBytes = ReadEntryBytes(nestedEntry);
			using MemoryStream nestedStream = new MemoryStream(nestedBytes);
			using ZipArchive inner = new ZipArchive(nestedStream, ZipArchiveMode.Read);
			Dictionary<string, ZipArchiveEntry>? innerMap = BuildNormMap(inner, out error);
			if(innerMap == null || innerMap.Count == 0) {
				if(innerMap != null) {
					error = "zip is empty";
				}
				return false;
			}
			rootPrefix = FindPackRoot(innerMap.Keys, romName);
			if(rootPrefix == null) {
				error = "not a legacy HD pack (no hires.txt)";
				return false;
			}
			WriteUnderRoot(innerMap, rootPrefix, targetFolder);
			return true;
		}

		private static Dictionary<string, ZipArchiveEntry>? BuildNormMap(ZipArchive zip, out string error)
		{
			error = "";
			Dictionary<string, ZipArchiveEntry> byNorm = new(StringComparer.Ordinal);
			foreach(ZipArchiveEntry zipEntry in zip.Entries) {
				if(string.IsNullOrEmpty(zipEntry.Name)) {
					continue;
				}
				string? norm = NormalizeZipPath(zipEntry.FullName);
				if(norm == null) {
					error = "zip entry escapes the pack root: '" + zipEntry.FullName + "'";
					return null;
				}
				byNorm[norm] = zipEntry;
			}
			return byNorm;
		}

		private static byte[] ReadEntryBytes(ZipArchiveEntry entry)
		{
			using Stream src = entry.Open();
			using MemoryStream ms = new MemoryStream();
			src.CopyTo(ms);
			return ms.ToArray();
		}

		private static void WriteUnderRoot(Dictionary<string, ZipArchiveEntry> byNorm, string rootPrefix, string targetFolder)
		{
			foreach(KeyValuePair<string, ZipArchiveEntry> pair in byNorm) {
				if(!pair.Key.StartsWith(rootPrefix, StringComparison.Ordinal)) {
					continue;
				}
				string rel = pair.Key.Substring(rootPrefix.Length);
				if(string.IsNullOrEmpty(rel)) {
					continue;
				}
				string dest = Path.Combine(targetFolder, rel.Replace('/', Path.DirectorySeparatorChar));
				Directory.CreateDirectory(Path.GetDirectoryName(dest) ?? targetFolder);
				using Stream src = pair.Value.Open();
				using FileStream outStream = new FileStream(dest, FileMode.Create, FileAccess.Write);
				src.CopyTo(outStream);
			}
		}
	}
}
