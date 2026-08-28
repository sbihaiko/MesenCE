#!/usr/bin/env bash
# ADR-0138 §37/§4: the network boundary for the MEP-recipe community-pack
# flow stays entirely inside UI/Services/ (F6.4b) - Core/ is the offline,
# local-files-only MEP-recipe-v1 interpreter and must never grow HTTP-client
# code. Fails loudly, never vacuously, when Core/ contains an actual
# HttpClient/libcurl code construct (a #include of curl's header, a
# curl_easy_*/CURLOPT_* call, a CURL* handle, or a C++ class literally named
# HttpClient) - NOT when a comment merely *mentions* those words in prose,
# such as MepRecipeInstaller.h's own "no HTTP, no network, no libcurl"
# disclaimer, which this check must not flag as a violation. C-style (// and
# /* */) comments are stripped before matching, line-for-line, so reported
# line numbers still point at the real file. No mocks: reads the real
# Core/ tree from disk.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CORE_DIR="$REPO_ROOT/Core"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

[ -d "$CORE_DIR" ] || fail "directory not found: $CORE_DIR"

# Strips // line comments and /* ... */ block comments (including ones
# spanning multiple lines) while preserving one output line per input line,
# so a later `grep -n` on the result still reports the real source line.
strip_comments() {
  awk '
    {
      line = $0
      if (in_block) {
        end = index(line, "*/")
        if (end > 0) {
          line = substr(line, end + 2)
          in_block = 0
        } else {
          print ""
          next
        }
      }
      while ((start = index(line, "/*")) > 0) {
        rest = substr(line, start)
        end = index(rest, "*/")
        if (end > 0) {
          line = substr(line, 1, start - 1) substr(rest, end + 2)
        } else {
          line = substr(line, 1, start - 1)
          in_block = 1
          break
        }
      }
      pos = index(line, "//")
      if (pos > 0) {
        line = substr(line, 1, pos - 1)
      }
      print line
    }
  ' "$1"
}

# Forbidden code-shape patterns (not prose): libcurl API/header, a curl
# handle type/option macro, or an actual HttpClient identifier usage.
PATTERN='#[[:space:]]*include[[:space:]]*[<"]curl|curl_easy_|CURLOPT_|\bCURL[[:space:]]*\*|\bHttpClient\b'

VIOLATIONS=""
while IFS= read -r -d '' file; do
  MATCH="$(strip_comments "$file" | grep -nE "$PATTERN" || true)"
  if [ -n "$MATCH" ]; then
    while IFS= read -r line; do
      VIOLATIONS="$VIOLATIONS$file:$line"$'\n'
    done <<<"$MATCH"
  fi
done < <(find "$CORE_DIR" -type f \( -name '*.h' -o -name '*.hpp' -o -name '*.cpp' -o -name '*.cc' -o -name '*.c' \) -print0)

if [ -n "$VIOLATIONS" ]; then
  echo "FAIL: Core/ must stay HTTP-client-free (ADR-0138 §37); found HttpClient/libcurl code in:" >&2
  echo "$VIOLATIONS" >&2
  exit 1
fi

echo "PASS: Core/ contains no HttpClient/libcurl code (network boundary stays in UI/Services/, ADR-0138 §37)"
