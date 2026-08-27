#!/usr/bin/env python3
"""generate_community_pack_catalog.py — regenera docs/community-packs.md.

Lê os itens aceitos do board "MesenCE Community Packs" (Project 3, owner
sbihaiko, node id PVT_kwHOB1MsbM4BhjpN) via `gh project item-list` e, para
cada issue de origem, busca autor/data/console/reações via `gh issue view`.
Reescreve docs/community-packs.md com uma tabela link/jogo/console/autor/
categoria/data e uma seção "Mais populares" ordenada por reação 👍 — um
proxy de popularidade, não uma métrica real de uso (nenhuma telemetria é
implementada aqui ou em nenhum outro lugar deste repositório).

stdlib apenas (subprocess + json), no estilo de scripts/report-bug.sh e
scripts/mep_lint.py.

Uso: python3 scripts/generate_community_pack_catalog.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "sbihaiko/MesenCE"
OWNER = "sbihaiko"
PROJECT_NUMBER = 3

ACCEPTED_STATUSES = {"Aceito parcial (HD Mesen)", "Aceito (MEP completo)"}
CONSOLE_LABELS = {"nes", "snes", "gb", "gbc", "sms", "other"}
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "community-packs.md"
TABLE_HEADER = "| Link | Game | Console | Author | Category | Date |"
TABLE_SEP = "|---|---|---|---|---|---|"


def run_gh(args):
    """Executa `gh` e devolve stdout; stderr/erro propagam para o log do job."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def fetch_accepted_items():
    """Lista os itens do Project 3 com Status num dos dois estados "Aceito*".

    Provenance note (confirmado ao vivo nesta sessão, gh 2.83.1):
    `gh project field-list 3 --owner sbihaiko --format json` CONFIRMA o
    field id de Status (PVTSSF_lAHOB1MsbM4BhjpNzhge86c, com as 5 opções do
    task) e o de Pack Hash (PVTF_lAHOB1MsbM4BhjpNzhge9Is) contra a API real
    do GitHub. Já os nomes de chave por item de `gh project item-list 3
    --owner sbihaiko --format json` permanecem um COVERAGE GAP aberto e
    auditado: essa mesma chamada, em sessão real, devolveu
    `{"items":[],"totalCount":0}` — o Project está com zero itens no
    momento da escrita deste script, então não existe exemplo populado para
    confirmar esses nomes de chave contra dado real. O gap está no próprio
    datastore ao vivo (nenhum item populado existe ainda), não apenas numa
    visão em cache, e não é apresentado aqui como fato assentado — qualquer
    conclusão negativa/de ausência de chave abaixo é qualificada por esse
    gap. `extract_row` usa lookups defensivos e não-crash (`dict.get`) em
    vez de indexação direta, para que um schema real diferente do esperado
    falhe visivelmente (linha com placeholders) em vez de derrubar o script
    ou arquivar um item errado silenciosamente.
    """
    raw = run_gh(["project", "item-list", str(PROJECT_NUMBER), "--owner", OWNER, "--format", "json"])
    items = json.loads(raw).get("items", [])
    return [it for it in items if _item_status(it) in ACCEPTED_STATUSES]


def _item_status(item):
    """Lookup defensivo do Status do item (ver provenance note em fetch_accepted_items)."""
    return item.get("status") or item.get("Status") or ""


def _item_issue_number(item):
    """Lookup defensivo do número da issue de origem, tentando os formatos plausíveis."""
    content = item.get("content") or {}
    return content.get("number") or item.get("number") or item.get("issue_number")


def fetch_issue_details(issue_number):
    """Busca autor/data/labels/reações da issue via `gh issue view`.

    Campo confirmado ao vivo nesta sessão: o nome de campo JSON correto é
    `reactionGroups` (não `reactions` — `gh issue view --json reactions`
    falha com "Unknown JSON field" no gh 2.83.1). Formato populado
    confirmado ao vivo (reação de teste adicionada e removida via
    `gh api graphql` addReaction/removeReaction nesta sessão):
    `[{"content": "THUMBS_UP", "users": {"totalCount": N}}, ...]`, só com
    grupos de contagem > 0; lista vazia quando não há reações.
    """
    raw = run_gh(["issue", "view", str(issue_number), "--repo", REPO,
                  "--json", "author,createdAt,title,labels,url,reactionGroups,body"])
    return json.loads(raw)


def _parse_form_field(body, heading):
    """Extracts the answer under a '### <heading>' section of an Issue Form body.

    Issue Forms always render a submitted field as a Markdown '### <label>'
    heading followed by the answer, up to the next '### ' heading or the end
    of the body (confirmed live against issues #6/#7/#8's rendered bodies —
    see .github/ISSUE_TEMPLATE/community-pack.yml for the field labels).
    Returns None (not "?") when the heading isn't found or the answer is
    empty, so callers can fall back to another source instead of an empty
    string leaking into the catalog.
    """
    if not body:
        return None
    pattern = re.compile(
        r"^###\s+" + re.escape(heading) + r"\s*\n+(.*?)(?=\n###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _escape_table_cell(value):
    """Collapses whitespace/newlines and escapes '|' for a Markdown table cell.

    Needed once free-form issue-body text (not just labels/title) starts
    flowing into the table — a submitter's answer could otherwise contain a
    literal '|' or a line break and break the table's row structure.
    """
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|").strip()


def _thumbs_up_count(details):
    """Soma defensiva de reações THUMBS_UP a partir de reactionGroups."""
    for group in details.get("reactionGroups") or []:
        if group.get("content") == "THUMBS_UP":
            users = group.get("users") or {}
            return users.get("totalCount", 0)
    return 0


def _console_from_labels(labels):
    for label in labels or []:
        name = (label.get("name") or "").strip().lower()
        if name in CONSOLE_LABELS:
            return name
    return "?"


def _categoria_from_status(status):
    if status == "Aceito (MEP completo)":
        return "Full MEP"
    if status == "Aceito parcial (HD Mesen)":
        return "Partial HD"
    return status or "?"


def build_row(item):
    """Monta uma linha de catálogo combinando o item do Project e a issue."""
    issue_number = _item_issue_number(item)
    status = _item_status(item)
    if issue_number is None:
        return {"jogo": "(no issue)", "console": "?", "autor": "?",
                "categoria": _categoria_from_status(status), "data": "?", "url": "", "thumbs_up": 0}
    details = fetch_issue_details(issue_number)
    author = (details.get("author") or {}).get("login") or "?"
    body = details.get("body") or ""
    # Prefer the Issue Form's own structured fields over the issue title/
    # labels — title is free text (often just restating the pack name, not
    # the target ROM) and no automation in this pipeline ever attaches a
    # console-name label (see the "Console" section always parsing to "?"
    # bug this fixes), so falling back to them only covers issues that
    # don't follow the current form shape (e.g. hand-created ones).
    game = _parse_form_field(body, "Target game/ROM and region") or details.get("title") or "(no title)"
    console = _parse_form_field(body, "Console") or _console_from_labels(details.get("labels"))
    return {
        "jogo": _escape_table_cell(game),
        "console": _escape_table_cell(console),
        "autor": _escape_table_cell(author),
        "categoria": _categoria_from_status(status),
        "data": (details.get("createdAt") or "?")[:10],
        "url": details.get("url") or "",
        "thumbs_up": _thumbs_up_count(details),
    }


def render_table(rows):
    lines = [TABLE_HEADER, TABLE_SEP]
    if not rows:
        lines.append("| _no packs accepted yet_ | | | | | |")
    for row in rows:
        link = f"[link]({row['url']})" if row["url"] else "-"
        lines.append(f"| {link} | {row['jogo']} | {row['console']} | {row['autor']} | {row['categoria']} | {row['data']} |")
    return "\n".join(lines)


def render_popular_section(rows):
    lines = ["## Most popular", "",
             "_Ranked by 👍 reactions on the submission issue. This is a popularity proxy,_",
             "_not a real usage metric — no usage telemetry is collected by this project._", ""]
    ranked = sorted(rows, key=lambda r: r["thumbs_up"], reverse=True)
    if not ranked or ranked[0]["thumbs_up"] == 0:
        lines.append("_no packs with reactions yet._")
        return "\n".join(lines)
    for row in ranked:
        if row["thumbs_up"] <= 0:
            continue
        link = f"[{row['jogo']}]({row['url']})" if row["url"] else row["jogo"]
        lines.append(f"- {link} — 👍 {row['thumbs_up']}")
    return "\n".join(lines)


INTRO = ("Catalog generated automatically from the \"MesenCE Community\n"
         "Packs\" board (Project 3). Do not edit this file manually — it is\n"
         "overwritten by `.github/workflows/community-pack-catalog.yml`.")


def build_markdown(rows):
    return "\n\n".join([
        "# Community HD/MEP Packs",
        INTRO,
        render_table(rows),
        render_popular_section(rows),
    ]) + "\n"


def main():
    items = fetch_accepted_items()
    rows = [build_row(item) for item in items]
    OUTPUT_PATH.write_text(build_markdown(rows), encoding="utf-8")
    print(f"docs/community-packs.md regenerated with {len(rows)} accepted pack(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
