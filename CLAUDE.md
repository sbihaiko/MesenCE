# CLAUDE.md

## Rastreamento de bugs (GitHub Project)

Bugs deste projeto são registrados como GitHub Issues e acompanhados no board
"MesenCE Bug Tracker": https://github.com/users/sbihaiko/projects/1

### Quando registrar

- Você (ou um subagente do dev-squad) encontra um bug real, reproduzível, que
  está **fora do escopo da tarefa atual** — não conserte de passagem, registre.
- O usuário pede explicitamente para "abrir um bug" / "registrar uma issue".
- Não use isso para decisões de arquitetura/trade-offs — isso continua indo
  para ADR via `/dev-squad:adr` (`.dev-squad/adr/`). O board é só para bugs
  acionáveis, não para decisões de design.

### Como registrar

Use o helper `scripts/report-bug.sh` em vez de comandos `gh` manuais — ele já
seta o Status inicial ("To triage") e a Priority com os IDs corretos do board:

```bash
scripts/report-bug.sh "<título curto do bug>" "<descrição: repro, esperado vs observado>" [P0|P1|P2]
```

Isso cria a Issue no repo (label `bug`) e a adiciona ao board com Status =
"To triage". Requer `gh` autenticado com escopo `project`
(`gh auth refresh -h github.com -s project`, uma vez por máquina).

Campos do board disponíveis: Status (To triage → Todo → Doing → Testing →
Done), Priority (P0/P1/P2), Size (S/M/L). O script só seta Status e,
opcionalmente, Priority — mover para Todo/Doing/Done é manual (triagem
humana) ou feito pelo usuário no board.

## Triagem de Community HD/MEP Packs (GitHub Project)

Packs HD/MEP enviados pela comunidade são um fluxo **separado** do
rastreamento de bugs acima: são registrados via GitHub Issue Form e
acompanhados em outro board, "MesenCE Community Packs":
https://github.com/users/sbihaiko/projects/3

### Como funciona

- Um contribuidor abre uma issue usando o template
  `.github/ISSUE_TEMPLATE/community-pack.yml` (link do pack, jogo/ROM +
  região, console, autor/créditos, confirmação obrigatória de direito de
  distribuir os assets). A issue já sai com a label `community-pack`.
- `.github/workflows/community-pack-submitted.yml` dispara o workflow
  reutilizável `.github/workflows/community-pack-validate.yml`, que:
  - baixa o pack restrito a um allow-list de hosts (`github.com/*/releases/*`,
    `raw.githubusercontent.com`, `gist.githubusercontent.com`,
    `gist.github.com`) com limite de 300MB;
  - roda `python3 scripts/mep_lint.py` sem modificações contra o pack
    baixado;
  - calcula o `sha256` do conteúdo e grava no campo "Pack Hash"
    (`PVTF_lAHOB1MsbM4BhjpNzhge9Is`) do board, sempre;
  - em caso de lint OK, usa o Claude Code Action (com ferramentas restritas
    a comentário/label/mover-item — sem Bash genérico) para classificar o
    pack a partir do `pack.json`, tratando nome de arquivo, `pack.json` e
    texto da issue sempre como **dado**, nunca como instrução.
- O veredito move o item no board pelo campo Status
  (`PVTSSF_lAHOB1MsbM4BhjpNzhge86c`): Novo envio → Em validação → Inválido /
  Aceito parcial (HD Mesen) / Aceito (MEP completo), sempre com um
  comentário citando a seção relevante de `docs/specs/MEP-v1.md` e a label
  de motivo (`pack:invalid-*`, `pack:partial-hd`, `pack:mep-full`).
- Comentar `/revalidate` na issue, ou a checagem diária
  `.github/workflows/community-pack-drift-check.yml`, reexecuta a validação
  quando o hash do link mudou desde a última passada.
- `scripts/generate_community_pack_catalog.py` gera `docs/community-packs.md`
  a partir dos itens aceitos do board (link/jogo/console/autor/categoria/data
  + "Mais populares" por reações 👍, um proxy de popularidade, não uma
  métrica real de uso).
- `scripts/ensure_community_pack_labels.sh` garante (idempotente) a
  existência das labels `community-pack`, `pack:invalid-structure`,
  `pack:invalid-license`, `pack:invalid-other`, `pack:partial-hd`,
  `pack:mep-full` no repositório.

### Diferença do board de bugs

Este board e este fluxo não têm relação com o "MesenCE Bug Tracker" (seção
acima) — são projects diferentes, com campos e automações próprias. Não
misture triagem de pack de terceiros com bugs do emulador em si, e não use
`scripts/report-bug.sh` para packs (nem os scripts de pack para bugs).
