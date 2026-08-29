using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Mesen.Logic
{
	//Host-free MEI v1.1 catalog DTOs (F6.4b, ADR-0138 §4/§37/§38) - the shape
	//of docs/community-packs.json exactly as emitted by
	//scripts/mei_catalog_entry.py::build_catalog/build_pack_entry, which in
	//turn implements docs/specs/MEI-v1.md §2. BCL only, per the UI/Logic/
	//firewall contract (UI/AGENTS.md) - no Avalonia/EmuApi - so this file
	//dual-compiles unmodified into UI.Tests (UI.Tests/UI.Tests.csproj's
	//"../UI/Logic/**/*.cs" glob).
	//
	//Field names/casing mirror the wire JSON verbatim via
	//[JsonPropertyName] - MesenSerializerContext (UI/Utilities/JsonHelper.cs)
	//applies no naming policy, so every property that isn't already an exact
	//case-sensitive match for its JSON key needs an explicit attribute.
	//Every property is nullable/optional except the fields MEI-v1.md §2.1/
	//§2.2 marks MUST for every `kind` (`name`, `game`, `system`, `rom`,
	//`url`, `sha256`) - `version`/`mep` are MUST unless `kind: "hd-legacy"`
	//(§2.2), so they stay nullable here too. Unknown JSON fields are
	//ignored by System.Text.Json by default, matching MEI-v1.md §2.2's
	//"Unknown fields MUST be ignored".
	public class CommunityPackCatalog
	{
		[JsonPropertyName("mei")] public string Mei { get; set; } = "";
		[JsonPropertyName("name")] public string Name { get; set; } = "";
		[JsonPropertyName("maintainer")] public string? Maintainer { get; set; }
		[JsonPropertyName("updated")] public string? Updated { get; set; }
		[JsonPropertyName("packs")] public CommunityPackCatalogEntry[] Packs { get; set; } = Array.Empty<CommunityPackCatalogEntry>();
	}

	//One `packs[]` entry (MEI-v1.md §2.2/§2.3). `Url`/`Sha256`/`Size` are the
	//wire-flat primary-artifact fields (matching the real generator output
	//and the MEI-v1.md example, which does NOT nest them under a "source"
	//key); `Source` below is a host-free convenience grouping of those same
	//three fields for callers that think in terms of "the pack's source
	//artifact" (e.g. CommunityPackReinstallDecision comparing this entry's
	//`Source.Sha256` against an installed `.mep-install.json`'s recorded
	//`source.sha256` - ADR-0138 §4) - it is [JsonIgnore]d, not a second wire
	//shape.
	public class CommunityPackCatalogEntry
	{
		[JsonPropertyName("kind")] public string? Kind { get; set; }
		[JsonPropertyName("name")] public string Name { get; set; } = "";
		[JsonPropertyName("version")] public string? Version { get; set; }
		//P.2 (ADR-0140) additive MEI fields, MAY - read-only for the client:
		//the resolved pack_id, the content_id (ADR-0139 revision), and the
		//community 👍 count that sorts the Player picker. Each may be absent.
		[JsonPropertyName("pack_id")] public string? PackId { get; set; }
		[JsonPropertyName("content_id")] public string? ContentId { get; set; }
		[JsonPropertyName("votes")] public int? Votes { get; set; }
		[JsonPropertyName("game")] public string Game { get; set; } = "";
		[JsonPropertyName("system")] public string System { get; set; } = "";
		[JsonPropertyName("rom")] public CommunityPackRom Rom { get; set; } = new();
		[JsonPropertyName("mep")] public string? Mep { get; set; }
		[JsonPropertyName("license")] public string? License { get; set; }
		[JsonPropertyName("url")] public string Url { get; set; } = "";
		[JsonPropertyName("size")] public long? Size { get; set; }
		[JsonPropertyName("sha256")] public string Sha256 { get; set; } = "";
		[JsonPropertyName("deps")] public CommunityPackDep[]? Deps { get; set; }
		//MEI-v1.md §2.3: the MEP-recipe-v1 document assembled for `deps`. Kept
		//opaque (JsonElement, source-gen/AOT-safe) and handed verbatim to
		//MepRecipeInstaller::Install - the UI never interprets it (ADR-0138 §45).
		[JsonPropertyName("recipe")] public JsonElement? Recipe { get; set; }

		//Provenance fields (MEI-v1.md §2.2: "MAY, non-normative - clients
		//MUST ignore them for install decisions and MAY display them").
		[JsonPropertyName("issue")] public int? Issue { get; set; }
		[JsonPropertyName("verdict")] public string? Verdict { get; set; }
		[JsonPropertyName("validated_at")] public string? ValidatedAt { get; set; }
		[JsonPropertyName("labels")] public string[]? Labels { get; set; }
		[JsonPropertyName("recipe_hash")] public string? RecipeHash { get; set; }
		[JsonPropertyName("recipe_ok")] public bool? RecipeOk { get; set; }

		//`kind` defaults to "mep" when absent (§2.2/§2.3).
		[JsonIgnore] public string EffectiveKind => string.IsNullOrEmpty(Kind) ? "mep" : Kind;
		[JsonIgnore] public bool IsHdLegacy => string.Equals(EffectiveKind, "hd-legacy", StringComparison.OrdinalIgnoreCase);
		[JsonIgnore] public CommunityPackSource Source => new CommunityPackSource(Url, Sha256, Size);
		//§2.2: "an absent field is read as 'unknown'".
		[JsonIgnore] public string LicenseOrUnknown => string.IsNullOrWhiteSpace(License) ? "unknown" : License;
	}

	//`rom` object (MEI-v1.md §2.2/§2.3). `Sha1` is a single 40-uppercase-hex
	//No-Intro hash (MEP-v1 §4), MAY be absent per the v1.1 downgrade of the
	//v1.0 MUST (§2.3) - entries without one are listable but not
	//hash-matchable against a loaded ROM. `Crc32` is the legacy fallback for
	//`kind: "hd-legacy"` entries pre-dating MEP.
	public class CommunityPackRom
	{
		[JsonPropertyName("sha1")] public string? Sha1 { get; set; }
		[JsonPropertyName("crc32")] public string? Crc32 { get; set; }
	}

	//Host-free grouping of a downloadable artifact's location/identity
	//(url + sha256 + size) - shared shape between a catalog entry's primary
	//artifact (`CommunityPackCatalogEntry.Source`) and the trust rules MEI-v1
	//§3 applies to it (sha256 verified before extraction, HTTPS required).
	//Not a JSON-wire nesting of its own (see `CommunityPackCatalogEntry`
	//above) - constructed from the entry's flat `url`/`sha256`/`size`
	//fields, so it still needs registering in `MesenSerializerContext` for
	//any call site that serializes/clones it standalone (`JsonHelper.Clone`).
	public class CommunityPackSource
	{
		public CommunityPackSource() { }

		public CommunityPackSource(string url, string sha256, long? size)
		{
			Url = url;
			Sha256 = sha256;
			Size = size;
		}

		[JsonPropertyName("url")] public string Url { get; set; } = "";
		[JsonPropertyName("sha256")] public string Sha256 { get; set; } = "";
		[JsonPropertyName("size")] public long? Size { get; set; }
	}

	//One `deps[]` item (MEI-v1.md §2.3): a third-party artifact the pack
	//references but does not bundle. `Hints`/`UserSupplied` mirror
	//MEP-recipe-v1's `sources.deps[]` shape (ADR-0138 §1/§4) for a dep the
	//client cannot auto-download and must prompt the user for; the current
	//catalog generator (scripts/mei_catalog_entry.py::_dep_entry) collapses
	//a recipe's `hints[0]` into this entry's flat `url`, so `Hints` reads
	//null against today's real catalog and a future generator revision (or
	//a dep resolver that also treats `Url` as a lone hint) can populate it
	//without a DTO change.
	public class CommunityPackDep
	{
		[JsonPropertyName("id")] public string Id { get; set; } = "";
		[JsonPropertyName("url")] public string? Url { get; set; }
		[JsonPropertyName("sha256")] public string? Sha256 { get; set; }
		[JsonPropertyName("size")] public long? Size { get; set; }
		[JsonPropertyName("license")] public string? License { get; set; }
		[JsonPropertyName("hints")] public string[]? Hints { get; set; }
		[JsonPropertyName("user_supplied")] public bool? UserSupplied { get; set; }

		//§2.3: dep `license` SHOULD be present; the resolver-facing fallback
		//is the literal "not declared" (ADR-0138), distinct from the
		//catalog-level "unknown" default (§2.2) used for the pack's own
		//`license` field.
		[JsonIgnore] public string LicenseOrNotDeclared => string.IsNullOrWhiteSpace(License) ? "not declared" : License;
	}
}
