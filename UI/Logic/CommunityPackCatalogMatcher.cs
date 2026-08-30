using System;

namespace Mesen.Logic
{
	//Host-free catalog matching (F6.4b, ADR-0138 §38/§41): an entry auto-
	//matches a loaded ROM when it carries a No-Intro sha1 equal to the ROM's
	//(MEP-v1 §4), case-insensitive. Entries without a sha1 (`rom: {}` -
	//MEI-v1 §2.3) are listable but never hash-matched, so a bare "no match"
	//cannot be an entry with a mismatched dump slipping through. BCL only,
	//dual-compiled into UI.Tests like the rest of UI/Logic.
	public static class CommunityPackCatalogMatcher
	{
		public static CommunityPackCatalogEntry? FindMatchingEntry(CommunityPackCatalog catalog, string romSha1)
		{
			if(catalog?.Packs == null) {
				return null;
			}
			foreach(CommunityPackCatalogEntry entry in catalog.Packs) {
				if(Matches(entry.Rom, romSha1)) {
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
	}
}
