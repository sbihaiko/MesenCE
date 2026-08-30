using System;
using System.Collections.Generic;

namespace Mesen.Logic
{
	//P.3 (PRD Part B §5, ADR-0140/0141): resolves, among the discovered
	//packs for a loaded ROM, which container is the chosen one, from the
	//persisted per-ROM preference (a pack_id). Host-free (BCL only - no
	//Avalonia/EmuApi/IO) so UI.Tests dual-compiles it via UI.Tests.csproj
	//(ADR-0123), and the core-side lookup stays a pure consequence of this
	//decision (see MepPackManager::FindPreferredPack).
	//
	//The preference is stored per ROM sha1 as a pack_id (ADR-0140): the
	//pack's declared `id`, `owner/repo`, or the `local:<container>` fallback
	//for a dropped container with no .mep-install.json stamp. This class
	//turns that pack_id into the winning *container* for the current
	//candidates, applies the §5 content_id merge (a container whose
	//content_id equals an already-seen one is the same pack, not a second
	//choice), and leaves the lexicographic default (ADR-0040, the core's own
	//order) untouched when there is no stored preference.
	public static class PackPreferenceResolver
	{
		public sealed class Candidate
		{
			public string Container { get; init; } = "";
			//Display name (pack.json `name`, or the submission title)
			public string Name { get; init; } = "";
			//From the container's .mep-install.json stamp; "" when none
			public string PackId { get; init; } = "";
			//From the container's .mep-install.json stamp; "" when none
			public string ContentId { get; init; } = "";
			public string Version { get; init; } = "";
			public bool Enabled { get; init; } = true;
		}

		public sealed class Resolution
		{
			//The winning container, or null when there is no stored preference
			//or the preferred pack_id matches no candidate (stale choice) - in
			//both cases the core's lexicographic default applies.
			public string? PreferredContainer { get; init; }
			//Content-merged candidates in the caller's order; a later container
			//duplicating an earlier one's content_id is not a new entry (§5).
			public List<Candidate> Candidates { get; init; } = new();
		}

		//A pack's effective pack_id for preference matching (ADR-0140): the
		//stamp's pack_id when present, else the rule-4 `local:<container>`
		//fallback. Lower-cased so the comparison is case-insensitive on both
		//sides (the core's EffectivePackId mirrors this).
		public static string DerivePackId(Candidate candidate)
		{
			return string.IsNullOrEmpty(candidate.PackId)
				? "local:" + candidate.Container.ToLowerInvariant()
				: candidate.PackId.ToLowerInvariant();
		}

		public static Resolution Resolve(IReadOnlyList<Candidate> candidates, string? preference)
		{
			string? wanted = string.IsNullOrWhiteSpace(preference)
				? null
				: preference.Trim().ToLowerInvariant();

			//§5 content_id merge: a container whose content_id equals an
			//already-seen one is the same pack, not a second entry. The
			//survivor is the one matching the preference; otherwise the first
			//seen stays (deterministic). Stamp-less containers (no content_id)
			//never merge - a local drop is always its own `local:` candidate.
			List<Candidate> merged = new();
			Dictionary<string, Candidate> byContentId = new(StringComparer.OrdinalIgnoreCase);
			foreach(Candidate c in candidates) {
				if(!string.IsNullOrEmpty(c.ContentId) && byContentId.TryGetValue(c.ContentId, out Candidate? existing)) {
					if(wanted != null && DerivePackId(c) == wanted && DerivePackId(existing) != wanted) {
						merged[merged.IndexOf(existing)] = c;
						byContentId[c.ContentId] = c;
					}
					continue; //not a new entry
				}
				if(!string.IsNullOrEmpty(c.ContentId)) {
					byContentId[c.ContentId] = c;
				}
				merged.Add(c);
			}

			//Preference -> winning container; stale/missing -> null (default).
			string? preferredContainer = null;
			if(wanted != null) {
				foreach(Candidate c in merged) {
					if(c.Enabled && DerivePackId(c) == wanted) {
						preferredContainer = c.Container;
						break;
					}
				}
			}

			return new Resolution {
				PreferredContainer = preferredContainer,
				Candidates = merged
			};
		}
	}
}
