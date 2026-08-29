using System;
using System.Collections.Generic;

namespace Mesen.Logic
{
	//P.5 (PRD-player-shell §5): when the Player-mode pack picker opens for a
	//loaded ROM. The picker is the only place the player chooses among
	//competing packs - it never appears when a sibling-folder pack is present
	//(that pack always wins, §4 "artist at work"), when fewer than two distinct
	//pack_ids exist (the catalog/lexicographic slot applies; never ask 1.0 vs
	//1.2), or when an effective per-ROM preference already exists (silent apply).
	//Dismissing stores nothing, so the next launch asks again; picking stores
	//the per-ROM-sha1 preference (P.3) and applies on the power cycle.
	//
	//Host-free (BCL only) so UI.Tests dual-compiles it and exercises the
	//decision without Avalonia/EmuApi (ADR-0123).
	public static class PlayerPackPicker
	{
		public static bool ShouldOpen(bool hasSiblingPack, int distinctPackIdCount, bool hasEffectivePreference)
		{
			if(hasSiblingPack) {
				//§4: the sibling-folder pack always wins; no catalog auto-install,
				//no picker, while it is present.
				return false;
			}
			if(hasEffectivePreference) {
				//§5: a stored per-ROM choice applies silently on load.
				return false;
			}
			//§5: 2+ competing pack_ids (after the content_id merge) -> ask once.
			return distinctPackIdCount >= 2;
		}

		//Distinct effective pack_ids among the §5 content-merged candidates -
		//ADR-0140 `id`, or the rule-4 `local:<container>` fallback. Two
		//containers sharing a content_id are one pack, so this must be fed the
		//merged candidates (PackPreferenceResolver.Resolve's Candidates), never
		//the raw entry list, or a dropped copy of an installed pack would count
		//as a second choice.
		public static int DistinctPackIdCount(IReadOnlyList<PackPreferenceResolver.Candidate> candidates)
		{
			HashSet<string> ids = new(StringComparer.OrdinalIgnoreCase);
			foreach(PackPreferenceResolver.Candidate c in candidates) {
				ids.Add(PackPreferenceResolver.DerivePackId(c));
			}
			return ids.Count;
		}
	}
}
