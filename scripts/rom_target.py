"""ROM-target resolution for the community-pack catalog (ADR-0138 §2.3).

Community HD/MEP submissions name their target game ("Target game/ROM and
region") but rarely declare a No-Intro ROM hash. `CommunityPackCatalogFetcher`
matches a loaded ROM against the catalog by `rom.sha1`, so an entry with an
empty `rom` object can never auto-match — it stays listable/installable by
hand, but the auto-install path silently never fires. This module closes that
gap for NES packs: a deterministic, versioned map from the normalized catalog
game name to the hash of the ROM it targets.

Source of the hashes: **a real No-Intro dump of the target game**, verified
against the Mesen game database. The hash the client matches on is
`EmuApi.GetMepRomSha1()` == `MepPackManager::ComputeNoIntroSha1` — the SHA1
of exactly the PRG+CHR the iNES header declares (ADR-0044), NOT the whole
file with its 16-byte header. A no-intro dat file (e.g. libretro's
`Nintendo - Nintendo Entertainment System.dat`) hashes the *whole file*, so
those sha1/crc32 values are wrong for this matcher by construction. The only
trustworthy source is a dump whose PRG+CHR crc32 the Mesen database
(`UI/Dependencies/MesenNesDB.txt`) recognizes — proof the dump IS the
No-Intro entry the core knows. Each entry below was computed from such a
dump and its crc32 double-checked against the database.

Adding a game: obtain a clean No-Intro dump of the target, compute
SHA1/CRC32 of the PRG+CHR the header declares (16-byte offset, 512-byte
trainer when flags6 bit 2), confirm the crc32 is present in
`UI/Dependencies/MesenNesDB.txt`, and add it here with the dump it came
from. Games not listed keep `rom: {}` (listable/installable, not
hash-matchable) until a verified dump exists.

Usage: `resolve_rom_target(game)` returns `{"sha1": ..., "crc32": ...}` or
None. `normalize_game_name` is the shared normalization the keys below use.
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
    """Returns {"sha1", "crc32"} for a catalog game the verified No-Intro
    map knows, or None when it does not resolve (the entry then keeps its
    empty `rom` object and stays manually installable)."""
    target = NO_INTRO_TARGETS.get(normalize_game_name(game))
    if target is None:
        return None
    # Defensive: never emit a malformed hash into the catalog — validate_mei
    # would reject the whole entry otherwise.
    sha1 = target["sha1"].strip().upper()
    crc32 = target["crc32"].strip().upper()
    if not SHA1_UPPER.match(sha1) or not CRC32_UPPER.match(crc32):
        return None
    return {"sha1": sha1, "crc32": crc32}
