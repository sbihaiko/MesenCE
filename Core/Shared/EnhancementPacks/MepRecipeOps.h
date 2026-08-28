#pragma once
#include "pch.h"

class JsonValue;

//Pre-declared split of MepRecipeInstaller (200-line-per-file guardrail,
//memory L-ff73acd33912-000, ADR-0138 Clarification §35): the pure,
//I/O-free MEP-recipe-v1 algorithms - the glob-pattern matcher (§4.2) and
//the rewrite-paths tag rewriting (§4.4) - plus the small path-safety
//helpers every op needs. The four op implementations that call into these
//sit in MepRecipeApply.h/.cpp (a further split of the same guardrail);
//neither file is a standalone public API, MepRecipeInstaller.cpp is the
//only caller of both.

//True when `rel` (already safe-normalized) is a patch destination that
//policy.apply_patch_only_if_complete withholds (MEP-recipe-v1 §6):
//under patches/ or ending in .ips/.bps.
bool IsPatchDest(const string& rel);

//MEP-recipe-v1 §5: normalizes `raw` (MepPack::NormalizeRelativePath) and
//additionally rejects the empty result - every path this interpreter
//writes or reads MUST be non-empty once normalized.
bool RequireSafeRel(const string& raw, string& out);

//MEP-recipe-v1 §4.2: '*' matches one path segment, '**' matches zero or
//more segments, '?' matches one character other than '/'.
bool GlobMatch(const string& pattern, const string& name);

//MEP-recipe-v1 §4.4: rewrites the bgm/sfx/img/background/patch file-path
//token of every matching tagged line of `text`; `tags` is the op's own
//tags list (only those tags are rewritten). Returns the rewritten text.
string RewriteHiresText(const string& text, const vector<string>& tags, const string& prefix);

//Every string entry of `parent`'s array member `key` (non-string entries
//skipped); "" when the member is absent or not an array. Shared by every
//op field that is a JSON array of strings (currently only rewrite-paths's
//"tags").
vector<string> CollectStringArray(const JsonValue& parent, const char* key);
