using System;
using System.Text;
using System.Text.RegularExpressions;

namespace Mesen.Logic
{
	//Host-free catalog matching (F6.4b, ADR-0138 §38/§41): an entry auto-
	//matches a loaded ROM when it carries a No-Intro sha1 equal to the ROM's
	//(MEP-v1 §4), case-insensitive, including additive `rom.sha1s` (nearby
	//revisions). When the dump hash is not listed, a second pass matches
	//the ROM's display name against the entry's `game` (same core-title
	//token multiset after stripping trailing region/dump tags) for EVERY
	//entry, hash-bearing or hash-less (ADR-0146): a pack whose `rom: {}` is
	//empty (MEI-v1 §2.3) also auto-matches optimistically, so a registered
	//pack with no recorded hash still installs by identity. The optimistic
	//application is self-healing (ADR-0145 health signal). IPS/patches stay
	//hash-gated (ADR-0044). BCL only, dual-compiled into UI.Tests.
	public static class CommunityPackCatalogMatcher
	{
		private static readonly Regex TrailingTag = new Regex(@"\s*[\(\[][^()\[\]]*[\)\]]\s*$", RegexOptions.CultureInvariant);
		private static readonly Regex Separators = new Regex(@"[_-]", RegexOptions.CultureInvariant);
		private static readonly Regex Whitespace = new Regex(@"\s+", RegexOptions.CultureInvariant);

		public static CommunityPackCatalogEntry? FindMatchingEntry(CommunityPackCatalog catalog, string romSha1, string? romName = null)
		{
			if(catalog?.Packs == null) {
				return null;
			}
			foreach(CommunityPackCatalogEntry entry in catalog.Packs) {
				if(Matches(entry.Rom, romSha1)) {
					return entry;
				}
			}
			if(string.IsNullOrWhiteSpace(romName)) {
				return null;
			}
			//Same-game optimistic fallback (ADR-0146, ADR-0145): matches by
			//title token equality regardless of whether the entry carries a
			//sha1. Entries with a sha1 that did not match (different dump/revision)
			//and entries with an empty `rom` (`rom: {}`, MEI-v1 §2.3) both fall
			//here, so a hash-less registered pack still auto-installs. The
			//optimistic application is self-healing — a mismatched pack's tiles
			//falls through to the original (HdNesPack) and the health signal
			//(ADR-0145) disables it when the match rate stays low. IPS/patches
			//stay hash-gated (ADR-0044).
			foreach(CommunityPackCatalogEntry entry in catalog.Packs) {
				if(SameGame(entry.Game, romName)) {
					return entry;
				}
			}
			return null;
		}

		public static bool Matches(CommunityPackRom? rom, string romSha1)
		{
			if(rom == null || string.IsNullOrWhiteSpace(romSha1)) {
				return false;
			}
			if(!string.IsNullOrWhiteSpace(rom.Sha1) &&
				string.Equals(rom.Sha1, romSha1, StringComparison.OrdinalIgnoreCase)) {
				return true;
			}
			if(rom.Sha1s == null) {
				return false;
			}
			foreach(string extra in rom.Sha1s) {
				if(!string.IsNullOrWhiteSpace(extra) &&
					string.Equals(extra, romSha1, StringComparison.OrdinalIgnoreCase)) {
					return true;
				}
			}
			return false;
		}

		//Test-facing / reusable (ADR-0125): word-order/separator-insensitive
		//token equality of two game titles after stripping trailing (region)/
		//[flag] tags. "Legend of Zelda, The (USA)" == "The Legend of Zelda
		//(USA)"; "Super Mario Bros. 3" != "Super Mario Bros" (multiset
		//equality, not containment, so a sequel never collapses into the
		//original). Mirrors scripts/verify_community_install_from_zero.py
		//same_game + mep_lint.normalize_rom_core_name.
		public static bool SameGame(string? a, string? b)
		{
			string[] ta = GameTokens(a);
			string[] tb = GameTokens(b);
			if(ta.Length == 0 || tb.Length == 0 || ta.Length != tb.Length) {
				return false;
			}
			Array.Sort(ta, StringComparer.Ordinal);
			Array.Sort(tb, StringComparer.Ordinal);
			for(int i = 0; i < ta.Length; i++) {
				if(!string.Equals(ta[i], tb[i], StringComparison.Ordinal)) {
					return false;
				}
			}
			return true;
		}

		private static string[] GameTokens(string? name)
		{
			if(string.IsNullOrWhiteSpace(name)) {
				return Array.Empty<string>();
			}
			string norm = NormalizeCoreName(name);
			StringBuilder kept = new StringBuilder(norm.Length);
			foreach(char c in norm) {
				if((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == ' ') {
					kept.Append(c);
				}
			}
			return kept.ToString().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
		}

		private static string NormalizeCoreName(string name)
		{
			string stripped = name.Trim();
			while(true) {
				string next = TrailingTag.Replace(stripped, "");
				if(next == stripped) {
					break;
				}
				stripped = next;
			}
			string folded = Separators.Replace(stripped, " ");
			return Whitespace.Replace(folded, " ").Trim().ToLowerInvariant();
		}
	}
}
