using System.Collections.Generic;

namespace Mesen.Logic
{
	//F6.4b / F6.5 (ADR-0138 §4/§37/§46): the pure half of
	//CommunityPackInstallCoordinator.ResolveDeps - which of a catalog entry's
	//`deps[]` are already satisfied, which resolve against a local file by
	//content hash, and which must be prompted for.
	//
	//Stateful partner (ADR-0127): UI/Services/CommunityPackInstallCoordinator
	//owns the impure half - it enumerates and SHA-256-hashes the pack folder
	//and the .cache/downloads scratch folder, turns each pending entry into a
	//CommunityPackDepPrompt carrying that folder's real path, and calls
	//EmuApi.InstallMepRecipe. This class only decides; it never touches the
	//filesystem, and the resolution itself is delegated to
	//CommunityPackDepResolver so "match by content hash, never by name" stays
	//a single rule.
	public static class CommunityPackDepPlan
	{
		//deps: the entry's declared deps (may be null/empty).
		//alreadyResolvedIds: dep ids the caller already has a path for (the
		//catalog fetcher's pre-resolved map) - never re-resolved, never prompted.
		//packFolderFiles/downloadsCacheFiles: already-hashed local candidates.
		public static CommunityPackDepPlanResult Build(
			IEnumerable<CommunityPackDep>? deps,
			IEnumerable<string> alreadyResolvedIds,
			IReadOnlyList<CommunityPackLocalFile> packFolderFiles,
			IReadOnlyList<CommunityPackLocalFile> downloadsCacheFiles)
		{
			Dictionary<string, string> resolved = new(System.StringComparer.Ordinal);
			List<CommunityPackPendingDep> pending = new();
			if(deps == null) {
				return new CommunityPackDepPlanResult(resolved, pending);
			}

			HashSet<string> known = new(alreadyResolvedIds, System.StringComparer.Ordinal);
			foreach(CommunityPackDep dep in deps) {
				//A dep with no id, one the caller already resolved, or one with no
				//declared sha256 (nothing to match on) is skipped silently - the
				//recipe installer withholds whatever depends on it (§6).
				if(string.IsNullOrEmpty(dep.Id) || known.Contains(dep.Id) || string.IsNullOrEmpty(dep.Sha256)) {
					continue;
				}

				CommunityPackDepResolution resolution = CommunityPackDepResolver.Resolve(
					dep.Sha256, packFolderFiles, downloadsCacheFiles,
					dep.Hints != null ? string.Join(", ", dep.Hints) : null, dep.License);

				if(resolution.ResolvedPath != null) {
					resolved[dep.Id] = resolution.ResolvedPath;
					known.Add(dep.Id);
				} else {
					pending.Add(new CommunityPackPendingDep(dep.Id, resolution.Hints, resolution.License));
				}
			}

			return new CommunityPackDepPlanResult(resolved, pending);
		}
	}

	//Newly resolved dep id -> local path, plus the deps that still need the
	//user to drop a file. The caller merges Resolved into its own map and
	//decorates each pending entry with the drop-folder path.
	public sealed record CommunityPackDepPlanResult(
		IReadOnlyDictionary<string, string> Resolved, IReadOnlyList<CommunityPackPendingDep> Pending);

	//An unresolved user_supplied dep (MEI-v1.md §2.3): the host-free payload
	//behind Services.CommunityPackDepPrompt. License is never blank - the
	//resolver substitutes the literal "not declared".
	public sealed record CommunityPackPendingDep(string DepId, string Hints, string License);
}
