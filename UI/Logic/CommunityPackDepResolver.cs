using System;
using System.Collections.Generic;

namespace Mesen.Logic
{
	//Pure MEP-recipe dep resolver (ADR-0138 SS4/SS37, F6.4b). Given a recipe
	//dep's declared sha256 (MEP-recipe-v1 sources.deps[].sha256) this looks
	//the hash up first among the per-ROM pack folder's own files, then among
	//the user's downloads cache - both supplied by the caller as already-
	//hashed file lists, since this class touches neither the filesystem nor
	//the network itself (UI/Logic firewall, see UI/AGENTS.md - the actual
	//directory scan and hashing belongs to UI/Services/CommunityPackInstallService,
	//not here). When neither list has a match, this returns a "needs prompt"
	//result carrying the dep's `hints` and `license` (MEI-v1.md SS2.3 /
	//ADR-0138 Clarification SS34: an absent license is shown as the literal
	//"not declared", never left blank or silently defaulted to a real SPDX
	//id) for the caller to surface in a user-facing dialog - the client
	//never scrapes Drive/MEGA on its own (MEP-v1 SS6, no automated fetch of
	//`user_supplied` deps).
	public static class CommunityPackDepResolver
	{
		public const string LicenseNotDeclared = "not declared";

		public static CommunityPackDepResolution Resolve(
			string declaredSha256,
			IEnumerable<CommunityPackLocalFile> packFolderFiles,
			IEnumerable<CommunityPackLocalFile> downloadsCacheFiles,
			string? hints = null,
			string? license = null)
		{
			//Pack folder takes precedence: a file the pack's own convention
			//layout already ships (e.g. a previously resolved dep left in
			//place) should win over a same-hash file that happens to also
			//sit in the shared downloads cache.
			string? resolvedPath = FindBySha256(packFolderFiles, declaredSha256)
				?? FindBySha256(downloadsCacheFiles, declaredSha256);

			if(resolvedPath != null) {
				return CommunityPackDepResolution.Found(resolvedPath);
			}

			return CommunityPackDepResolution.Prompt(
				hints ?? "",
				string.IsNullOrWhiteSpace(license) ? LicenseNotDeclared : license);
		}

		private static string? FindBySha256(IEnumerable<CommunityPackLocalFile> files, string sha256)
		{
			foreach(CommunityPackLocalFile file in files) {
				//Hex case is not normative on read (MEI-v1.md SS2.2: "case-
				//insensitive on read"), so compare ordinally-ignoring-case
				//rather than requiring the caller to have lowercased first.
				if(string.Equals(file.Sha256, sha256, StringComparison.OrdinalIgnoreCase)) {
					return file.Path;
				}
			}
			return null;
		}
	}

	//One file already hashed by the caller (a pack-folder or downloads-cache
	//directory scan) - this resolver never hashes a file itself.
	public sealed record CommunityPackLocalFile(string Path, string Sha256);

	//Outcome of CommunityPackDepResolver.Resolve(): either a resolved local
	//path, or a payload the caller shows in a prompt asking the user to
	//supply the file by hand.
	public sealed class CommunityPackDepResolution
	{
		public bool RequiresPrompt { get; }
		public string? ResolvedPath { get; }
		public string Hints { get; }
		public string License { get; }

		private CommunityPackDepResolution(bool requiresPrompt, string? resolvedPath, string hints, string license)
		{
			RequiresPrompt = requiresPrompt;
			ResolvedPath = resolvedPath;
			Hints = hints;
			License = license;
		}

		public static CommunityPackDepResolution Found(string path)
		{
			return new CommunityPackDepResolution(false, path, "", "");
		}

		public static CommunityPackDepResolution Prompt(string hints, string license)
		{
			return new CommunityPackDepResolution(true, null, hints, license);
		}
	}
}
