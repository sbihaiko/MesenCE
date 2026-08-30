using System;
using System.Collections.Generic;
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
	//(ADR-0120). The UI/Services coordinator supplies the zip entry list and
	//does the actual I/O.
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
	}
}
