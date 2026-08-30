"""ROM-target resolution for the community-pack catalog (ADR-0138 §2.3).

Community HD/MEP submissions name their target game ("Target game/ROM and
region") but rarely declare a No-Intro ROM hash. `CommunityPackCatalogFetcher`
matches a loaded ROM against the catalog by `rom.sha1`, so an entry with an
empty `rom` object can never auto-match — it stays listable/installable by
hand, but the auto-install path silently never fires. This module closes that
gap for NES packs: a deterministic, versioned map from the normalized catalog
game name to the hash of the ROM it targets.

Source of the hashes — two legitimate sources:
  1. **A real No-Intro dump of the target game**, verified against the Mesen
     game database. The hash the client matches on is
     `EmuApi.GetMepRomSha1()` == `MepPackManager::ComputeNoIntroSha1` — the
     SHA1 of exactly the PRG+CHR the iNES header declares (ADR-0044), NOT the
     whole file with its 16-byte header. A no-intro dat file (e.g. libretro's
     `Nintendo - Nintendo Entertainment System.dat`) hashes the *whole file*,
     so those sha1/crc32 values are wrong for this matcher by construction.
     The trustworthy dump is one whose PRG+CHR crc32 the Mesen database
     (`UI/Dependencies/MesenNesDB.txt`) recognizes — proof the dump IS the
     No-Intro entry the core knows. Those entries carry both sha1 and crc32.
  2. **The sha1 the pack itself declares** — the pack's `<supportedRom>` /
     `<patch>` hash, which is exactly what the patch matcher compares against
     `ComputeNoIntroSha1`. When no verified dump is at hand but the pack
     declares its target hash (as Zelda Remastered v1.3 does), the declared
     sha1 is a trustworthy `rom.sha1` on its own (sha1-only, no crc32).

Adding a game: obtain a clean No-Intro dump of the target, compute
SHA1/CRC32 of the PRG+CHR the header declares (16-byte offset, 512-byte
trainer when flags6 bit 2), confirm the crc32 is present in
`UI/Dependencies/MesenNesDB.txt`, and add it here with the dump it came
from — or, when no dump exists but the pack declares its target hash, record
that declared sha1 (sha1-only) with a `source` note. Games not listed keep
`rom: {}` (listable/installable, not hash-matchable) until then.

Usage: `resolve_rom_target(game)` returns `{"sha1", "crc32"}` (crc32
optional) or None. `normalize_game_name` is the shared normalization the
keys below use.
"""
import re

SHA1_UPPER = re.compile(r"^[0-9A-F]{40}$")
CRC32_UPPER = re.compile(r"^[0-9A-F]{8}$")

# key: `normalize_game_name(<catalog game>)`; value: hashes of the target
# ROM. `source_dump` names the No-Intro dump the hashes were computed from.
NO_INTRO_TARGETS = {
    "super mario bros": {
        "source_dump": "Super Mario Bros. 1 (1985) (Nintendo).nes",
        "sha1": "B606D2CF1EC5E8732B8748D272417B7FECB4EEF7",
        "crc32": "7C26958E",
    },
    "mega man usa": {
        "source_dump": "Mega Man (1987) (Capcom).nes",
        "sha1": "6047E52929DFE8ED4708D325766CCB8D3D583C7D",
        "crc32": "6EE4BB0A",
    },
    "contra usa": {
        "source_dump": "Contra (USA).nes",
        "sha1": "979494E7869AC7AB4815FDBD1DC99F893F713FBF",
        "crc32": "F6035030",
    },
    "the legend of zelda usa": {
        "source": "pack-declared <supportedRom>/<patch> sha1 (Zelda Remastered v1.3, issue #139)",
        "sha1": "DAB79C84934F9AA5DB4E7DAD390E5D0C12443FA2",
    },
    "castlevania usa": {
        "source": "Mesen CheatDb.Nes.json 'Castlevania (USA)' sha1 (GetMepRomSha1)",
        "sha1": "EE09B857C90916EDD92A20C463485A610B0A76FD",
        # The kya HD pack still loads textures on Rev A (ADR-0044: a
        # <patch> that does not match the dump is skipped; tiles still apply).
        "alt_sha1": [
            "3DCB69A8C861C041AEB56C04E39ADF6D332EDA3A",  # Castlevania (USA) (Rev A)
        ],
    },
}


def normalize_game_name(game):
    """Collapses a catalog game string to the lookup key: lowercase, every
    separator (underscore/hyphen/dot/colon/parens/comma) becomes a space,
    runs of whitespace collapse. "Urban_Champion", "The Legend of Zelda
    (USA)" and "Pac-Man (Namco, US, 1993)" all land on stable, distinct
    keys."""
    if not game:
        return ""
    s = game.lower()
    s = s.replace("_", " ").replace("-", " ").replace(".", " ").replace(":", " ")
    s = s.replace("'", "")
    s = re.sub(r"[(),]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_rom_target(game):
    """Returns {"sha1", "crc32"} — crc32 only when known — for a catalog game
    the map knows, or None when it does not resolve (the entry then keeps its
    empty `rom` object and stays manually installable). A sha1-only entry is
    valid (MEI-v1 §2.3): it matches auto-install by sha1 alone. Defensive:
    never emit a malformed hash into the catalog — validate_mei would reject
    the whole entry otherwise."""
    target = NO_INTRO_TARGETS.get(normalize_game_name(game))
    if target is None:
        return None
    sha1 = target["sha1"].strip().upper()
    if not SHA1_UPPER.match(sha1):
        return None
    crc32 = (target.get("crc32") or "").strip().upper()
    if crc32 and not CRC32_UPPER.match(crc32):
        return None
    rom = {"sha1": sha1}
    if crc32:
        rom["crc32"] = crc32
    extras = []
    for raw in target.get("alt_sha1") or []:
        extra = (raw or "").strip().upper()
        if SHA1_UPPER.match(extra) and extra != sha1:
            extras.append(extra)
    if extras:
        rom["alt_sha1"] = extras
    return rom
