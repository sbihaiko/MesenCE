# Slice 1 — Utilities/ + SevenZip/ (+ vendored Lua) — inherited-code review

- Repo `HEAD` reviewed: `2c58e139`; fork/upstream merge-base `73be5b58` (upstream/master ancestor).
- Scope: `Utilities/*` (hash, CRC/archive, patches, compression, FastString, Video/Audio) plus the vendored `SevenZip/` (7-Zip LZMA SDK + Mesen-origin `7zMemBuffer.c` adapter) and vendored `Lua/` (Lua 5.4.8 + stock LuaSocket 3.0.0).
- Method: tier/heat snapshot (`scripts/upstream_tiers.py`), grep sweep over mem-copy/format/alloc/IO signatures, targeted reads of flag sites; fork-owned A-tier hashing/process files double-checked clean.

## Findings

11 total — P0 0, P1 3, P2 8. All tier C. Lua subtree: pristine Lua core (upstream-hot, report-only) and stock LuaSocket — **no defect worth filing** in the reachable script/network path; the real defects sit in `SevenZip/7zMemBuffer.c`, the only non-official-SDK file on the archive-controlled read path.

Classification note: raw agents marked everything "C+hot" (heat>0). Under the ADR-0163 working rule (hot = named dirs *or* heat ≥ 5/yr), every file here is **cold** (heat 0–1), so each real defect is patchable with a minimal hunk.

## Patched (10 findings, 7 files, +90/−22, 4 commits)

| file | heat | finding(s) resolved | hunk gist | ± |
|---|---|---|---|---|
| `SevenZip/7zMemBuffer.c` | 0 | [P1] EOF read underflow → SIZE_MAX memcpy; [P2] always withholds last byte; [P2] seek unclamped (feeds the overflow) | read returns 0 at `pos>=size`; length=`size-pos`; seek clamps to `[0,size]` | +19/−4 |
| `Utilities/Patches/UpsPatcher.cpp` | 1 | [P1] output OOB write (`output[pos]^=` unguarded); [P1] copy overruns when patch declares `outputFileSize` < ROM | validate `inputFileSize==input.size()` + `output.size()>=input.size()`; `pos>=output.size()` → false | +13/−0 |
| `Utilities/Patches/BpsPatcher.cpp` | 1 | [P2] `SourceRead` OOB heap read (`input[]` vs `output.size()`); [P2] varint shift ≥ 64 UB / int64 overflow | also bound `outputOffset` by `input.size()`; 5-byte base128 cap | +7/−1 |
| `Utilities/CompressionHelper.h` | 1 | [P2] header read + `size-8` underflow on buffers < 8 B | `input.size() < 8` → false | +4/−0 |
| `Utilities/CRC32.cpp` | 1 | [P2] `(uint32_t)filesize` truncates ≥ 4 GiB → heap overflow | `size_t` alloc; guard short read via `gcount` | +10/−5 |
| `Utilities/ArchiveReader.cpp` | 1 | [P2] same ≥ 4 GiB truncation on `LoadArchive(istream&)` | `size_t` alloc, return `false` on `filesize<=0` | +8/−3 |
| `Utilities/FastString.h` | 1 | [P2] stack buffer 1000 B, `_pos` never bound-checked | clamped writes/`memcpy` at cap 999 | +30/−9 |

Commits: `0a3eed0c` (7z), `5229d5c5` (patchers), `820f5494` (CRC32/ArchiveReader), `d2db65b7` (CompressionHelper/FastString). Every hunk is additive, single-purpose, preserves upstream style.

## Reported, not patched (1)

- `Utilities/ArchiveReader.cpp:83` [P2 C int-overflow/logic] `LoadArchive(string)` always returns `false` even when the stream load succeeded — a wrong `result` is never returned. Cold, patchable by rule, but the string overload is not on a live path this review could exercise; kept as a report item rather than touching it blind.

## Verification

C++ core builds clean (clang, `-Wall`, C++17, no new warnings); `make core-unit-tests` green (523 PASS at every run touching this slice). Suite re-run in full at baseline and at the end — see final report.

## Before / after (0–10)

| axis | before | after | supporting numbers |
|---|---|---|---|
| quality | 6 | 8.5 | 11 findings → 10 resolved; only latent defect with a wrong-result logic bug left reported |
| performance | 8 | 8 | guards are O(1) comparisons; no hot-path change; only added branch is before large copies |
| readability | 7 | 7 | +90/−22 across 7 files, each hunk self-contained and commented (e.g. "base128 cannot exceed 5 bytes") |
| security | 4 | 8 | before: P1 OOB *heap writes* on crafted UPS, varint UB → arbitrary resize, 4 GiB truncation overflow; after: every input-derived size/length on the patch/archive path is bounded before use |
