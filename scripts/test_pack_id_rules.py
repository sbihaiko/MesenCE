#!/usr/bin/env python3
"""Framework-free checks for scripts/pack_id_rules.py (P.2, ADR-0140/0141,
PRD-player-shell §3.3/§3.6).

Covers: the SLUG constraint, github_origin extraction (github.com +
codeload.github.com, owner/repo lowercased, other hosts None), the pack_id
resolution order (id -> owner/repo -> issue-n), pack_origin binding
(owner/repo for GitHub hosts, issue author otherwise), compare_semver, and
slot_winner's §3.6 precedence (semver > validated_at > issue number, with
non-comparable versions falling through to the time/issue rules).

Usage: python3 scripts/test_pack_id_rules.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import pack_id_rules  # noqa: E402
import mei_catalog_entry  # noqa: E402 -- integration: identity fields in the MEI entry

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"PASS: {msg}")


def check_github_origin():
    cases = [
        ("https://github.com/sbihaiko/contra80s/releases/download/v1.1/contra.zip", "sbihaiko/contra80s"),
        ("https://codeload.github.com/Foo/Bar/zip/refs/heads/main", "foo/bar"),
        ("https://github.com/User/Repo", "user/repo"),
        ("https://gist.github.com/abc123", None),
        ("https://raw.githubusercontent.com/u/r/x.txt", "u/r"),
        ("", None),
        (None, None),
    ]
    for url, expected in cases:
        got = pack_id_rules.github_origin(url)
        if got != expected:
            fail(f"github_origin({url!r}) = {got!r}, expected {expected!r}")
            return
    ok("github_origin extracts owner/repo from github.com and codeload, None elsewhere")


def check_slug():
    valid = ["contra80s", "a-b-c", "abc123xyz", "hd-mesen-pack"]
    invalid = ["Abc", "a", "ab", "has space", "scream!", ""]
    for slug in valid:
        if not pack_id_rules.SLUG.match(slug):
            fail(f"SLUG rejected a valid id: {slug!r}")
            return
    for slug in invalid:
        if pack_id_rules.SLUG.match(slug):
            fail(f"SLUG accepted an invalid id: {slug!r}")
            return
    ok("SLUG matches the ADR-0140 lowercase [a-z0-9][a-z0-9-]{2,63} constraint")


def check_resolve_pack_id():
    # (1) declared id wins over an owner/repo URL.
    meta = {"recipe": {"pack": {"id": "Contra80s"}}}
    pack_id, source = pack_id_rules.resolve_pack_id(
        "https://github.com/sbihaiko/contra80s/releases/download/v1/contra.zip", meta, 77)
    if (pack_id, source) != ("contra80s", "id"):
        fail(f"declared id resolution: got {(pack_id, source)!r}")
        return
    # (2) no id -> owner/repo from a GitHub URL.
    pack_id, source = pack_id_rules.resolve_pack_id(
        "https://github.com/SbiHaiko/Contra80s/releases/download/v1/contra.zip", {}, 77)
    if (pack_id, source) != ("sbihaiko/contra80s", "owner-repo"):
        fail(f"owner/repo resolution: got {(pack_id, source)!r}")
        return
    # (3) no id, non-GitHub host -> issue-n.
    pack_id, source = pack_id_rules.resolve_pack_id(
        "https://drive.google.com/file/d/xyz/view", {}, 42)
    if (pack_id, source) != ("issue-42", "issue"):
        fail(f"issue-n resolution: got {(pack_id, source)!r}")
        return
    ok("resolve_pack_id follows id -> owner/repo -> issue-n order")


def check_pack_origin():
    if pack_id_rules.pack_origin("https://github.com/User/Repo/releases/x", "someone") != "user/repo":
        fail("pack_origin should use owner/repo for a GitHub host")
        return
    if pack_id_rules.pack_origin("https://drive.google.com/file/d/x", "Alice") != "alice":
        fail("pack_origin should use the issue author's login for hosts without a repo")
        return
    if pack_id_rules.pack_origin("https://drive.google.com/file/d/x", None) is not None:
        fail("pack_origin with no repo and no author should be None")
        return
    ok("pack_origin binds to owner/repo for GitHub hosts, issue author otherwise")


def check_compare_semver():
    if pack_id_rules.compare_semver("1.2.3", "1.2.2") <= 0:
        fail("1.2.3 should compare higher than 1.2.2")
        return
    if pack_id_rules.compare_semver("1.2.3", "1.2.3") != 0:
        fail("equal versions should compare equal")
        return
    if pack_id_rules.compare_semver("1.2.3", "1.10.0") >= 0:
        fail("1.2.3 should compare lower than 1.10.0 (numeric, not lexical)")
        return
    if pack_id_rules.compare_semver("1.2.3", None) is not None:
        fail("a missing version is not comparable")
        return
    if pack_id_rules.compare_semver(None, "1.0.0") is not None:
        fail("a missing version is not comparable")
        return
    if pack_id_rules.compare_semver("1.0", "1.0.0") is not None:
        fail("a non-x.y.z version is not comparable")
        return
    ok("compare_semver is numeric and returns None for non-comparable pairs")


def check_slot_winner():
    base = [
        {"issue_number": 10, "version": "1.1.0", "validated_at": "2026-08-01T00:00:00Z"},
        {"issue_number": 11, "version": "1.0.0", "validated_at": "2026-08-02T00:00:00Z"},
    ]
    if pack_id_rules.slot_winner(base) != base[0]:
        fail("rule 1: higher semver must win regardless of time/issue")
        return
    no_version = [
        {"issue_number": 10, "version": None, "validated_at": "2026-08-01T00:00:00Z"},
        {"issue_number": 11, "version": None, "validated_at": "2026-08-02T00:00:00Z"},
    ]
    if pack_id_rules.slot_winner(no_version) != no_version[1]:
        fail("rule 2: with no comparable version, later validated_at must win")
        return
    tied = [
        {"issue_number": 10, "version": None, "validated_at": None},
        {"issue_number": 12, "version": None, "validated_at": None},
    ]
    if pack_id_rules.slot_winner(tied) != tied[1]:
        fail("rule 3: with nothing else comparable, the higher issue number must win")
        return
    one = [base[0]]
    if pack_id_rules.slot_winner(one) != one[0]:
        fail("a single candidate wins its own slot")
        return
    if pack_id_rules.slot_winner([]) is not None:
        fail("empty input yields no winner")
        return
    ok("slot_winner follows semver > validated_at > issue number")


def cand(issue, pack_id=None, content_id=None, version=None, validated_at=None, origin="u/r"):
    return {"issue_number": issue, "pack_id": pack_id or f"p{issue}", "content_id": content_id,
            "version": version, "validated_at": validated_at, "origin": origin}


def check_select_catalog_rows():
    # Slot: two revisions of one pack_id -> only the higher semver is kept.
    a = cand(10, "pack", content_id="c1", version="1.2.0", validated_at="2026-08-01T00:00:00Z")
    b = cand(11, "pack", content_id="c2", version="1.2.0", validated_at="2026-08-02T00:00:00Z")
    kept, reasons = pack_id_rules.select_catalog_rows([a, b])
    if [c["issue_number"] for c in kept] != [11] or reasons.get(10) != ("slot", 11):
        fail(f"slot: kept {[c['issue_number'] for c in kept]!r} reasons {reasons!r}")
        return
    # A revalidation that republishes a LOWER semver never displaces the slot
    # (§3.6): same pack_id, NEW content_id, lower version -> loses the slot.
    c = cand(12, "pack", content_id="c3", version="1.1.0", validated_at="2026-08-03T00:00:00Z")
    kept, reasons = pack_id_rules.select_catalog_rows([a, c])
    if [x["issue_number"] for x in kept] != [10] or reasons.get(12) != ("slot", 10):
        fail(f"revalidate lower semver: kept {[x['issue_number'] for x in kept]!r} reasons {reasons!r}")
        return
    # Content_id duplicate under a different pack_id -> not a second row.
    d = cand(13, "other-pack", content_id="c1", version="9.9.9", validated_at="2026-08-04T00:00:00Z")
    kept, reasons = pack_id_rules.select_catalog_rows([a, d])
    if [x["issue_number"] for x in kept] != [10] or reasons.get(13) != ("duplicate", 10):
        fail(f"byte-duplicate: kept {[x['issue_number'] for x in kept]!r} reasons {reasons!r}")
        return
    # Foreign origin claiming an existing pack_id -> not listed, never the slot.
    e = cand(14, "pack", content_id="c9", version="99.0.0", validated_at="2026-08-05T00:00:00Z", origin="other/repo")
    kept, reasons = pack_id_rules.select_catalog_rows([a, e])
    if [x["issue_number"] for x in kept] != [10] or reasons.get(14) != ("origin", "u/r"):
        fail(f"origin binding: kept {[x['issue_number'] for x in kept]!r} reasons {reasons!r}")
        return
    # Two competing products (different pack_id, different content_id) both listed.
    f = cand(15, "rival", content_id="zzz", version="1.0.0", validated_at="2026-08-06T00:00:00Z")
    kept, _ = pack_id_rules.select_catalog_rows([a, f])
    if sorted(x["issue_number"] for x in kept) != [10, 15]:
        fail(f"competing packs: kept {sorted(x['issue_number'] for x in kept)!r}")
        return
    # Determinism: input order never changes the outcome (same drops/slots as
    # the ordered runs above: d byte-duplicate of a, c loses the slot to b).
    shuffled = [f, d, a, c, b]
    kept2, reasons2 = pack_id_rules.select_catalog_rows(shuffled)
    if sorted(x["issue_number"] for x in kept2) != [11, 15]:
        fail(f"determinism: kept {sorted(x['issue_number'] for x in kept2)!r}")
        return
    if reasons2.get(12) != ("slot", 11) or reasons2.get(13) != ("duplicate", 10):
        fail(f"determinism: reasons {reasons2!r}")
        return
    ok("select_catalog_rows keeps one slot per pack_id, drops duplicates/origin/slot losers deterministically")


def check_mei_identity_fields():
    # build_pack_entry must carry the additive P.2 fields: pack_id (resolved
    # id -> owner/repo -> issue-n), content_id (from mep-meta), votes (the
    # community 👍 count) — each omitted when unknown, never empty.
    meta = {
        "content_id": "c" * 64,
        "kind": "mep",
        "recipe": {"pack": {"id": "My Pack", "version": "1.2.0", "mep": "1.1.0"}},
    }
    entry, mismatch = mei_catalog_entry.build_pack_entry(
        issue_number=42, game="Contra", system="nes", license_="CC0",
        pack_url="https://github.com/User/Repo/releases/download/v1/c.zip",
        pack_hash="a" * 64, rom_sha1="A" * 40, status="Aceito (MEP completo)",
        mep_meta=meta, votes=7)
    if mismatch:
        fail("a conformant mep entry reports a source_sha256 mismatch")
        return
    if entry.get("pack_id") != "user/repo":
        fail(f"pack_id should fall back to owner/repo, got {entry.get('pack_id')!r}")
        return
    if entry.get("content_id") != "c" * 64 or entry.get("votes") != 7:
        fail(f"content_id/votes missing: {entry!r}")
        return
    if entry.get("version") != "1.2.0":
        fail(f"version missing from the mep entry: {entry.get('version')!r}")
        return
    # A declared (if invalid-cased) id is normalized and wins over the URL.
    meta2 = dict(meta)
    meta2["recipe"] = {"pack": {"id": "Contra80s", "version": "1.2.0", "mep": "1.1.0"}}
    entry2, _ = mei_catalog_entry.build_pack_entry(
        issue_number=42, game="Contra", system="nes", license_="CC0",
        pack_url="https://github.com/User/Repo/releases/download/v1/c.zip",
        pack_hash="a" * 64, rom_sha1="A" * 40, status="Aceito (MEP completo)",
        mep_meta=meta2, votes=0)
    if entry2.get("pack_id") != "contra80s":
        fail(f"declared id should win and normalize, got {entry2.get('pack_id')!r}")
        return
    # No id, no GitHub host -> issue-n; absent votes omit the key.
    entry3, _ = mei_catalog_entry.build_pack_entry(
        issue_number=7, game="G", system="sms", license_="x",
        pack_url="https://drive.google.com/file/d/x", pack_hash="b" * 64,
        rom_sha1=None, status="Aceito parcial (HD Mesen)", mep_meta={}, votes=0)
    if entry3.get("pack_id") != "issue-7":
        fail(f"hostless pack_id should be issue-n, got {entry3.get('pack_id')!r}")
        return
    # content_id/version omitted when unknown (never empty); votes=0 IS a
    # legitimate integer and stays.
    if "content_id" in entry3 or "version" in entry3 or entry3.get("votes") != 0:
        fail(f"absent content_id/version must be omitted; votes=0 kept: {entry3!r}")
        return
    ok("build_pack_entry carries pack_id/content_id/votes as additive MAY fields")


def main():
    check_github_origin()
    check_slug()
    check_resolve_pack_id()
    check_pack_origin()
    check_compare_semver()
    check_slot_winner()
    check_select_catalog_rows()
    check_mei_identity_fields()

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
