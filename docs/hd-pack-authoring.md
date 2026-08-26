# Autoria de HD/MEP Packs para submissão comunitária

Este guia é para quem vai preencher o formulário "Submissão de Community
HD/MEP Pack" (`.github/ISSUE_TEMPLATE/community-pack.yml`). Ele resume o que
faz um pack ser aceito, aceito parcialmente, ou rejeitado na triagem
automática do board "MesenCE Community Packs".

A especificação normativa completa é [`docs/specs/MEP-v1.md`](specs/MEP-v1.md)
(RFC 2119, licença CC0-1.0). Este documento não substitui a spec — só traduz
as seções relevantes para quem está preparando uma submissão.

## O que a triagem verifica

Ao abrir a issue de submissão, um workflow baixa o pack pelo link informado,
roda `scripts/mep_lint.py` sobre ele e classifica o conteúdo declarado em
`pack.json` (seção `sections`, ver MEP-v1.md §3). O veredito final é um dos
três abaixo.

### Aceito (MEP completo)

O pack traz, além de texturas, pelo menos uma seção de `synth` ou `audio`:

- **`synth`** (MEP-v1.md §5.3) — um arquivo no formato **ESP v1**, aplicado
  acima dos defaults embutidos e abaixo do ESP local do usuário.
- **`audio`** (MEP-v1.md §5.2) — um diretório de replacement de áudio em
  formato já suportado pelo sistema alvo (OGG por HD pack, ou MSU-1 no SNES).

### Aceito parcial (HD Mesen)

O pack só declara a seção **`textures`** (MEP-v1.md §5.1): um diretório
apontando para um HD Pack no formato HDNes `hires.txt`. É uma submissão
válida e completa dentro do escopo de texturas, mas não cobre áudio/synth,
então recebe o rótulo `pack:partial-hd` em vez de `pack:mep-full`.

### Inválido

A submissão é rejeitada quando:

- o link não está no allow-list de hosts aceitos, ou o download excede o
  limite de tamanho;
- `scripts/mep_lint.py` falha (estrutura do `pack.json`, seções ou caminhos
  inválidos);
- o pack viola a seção de segurança da spec (MEP-v1.md §6): entradas de zip
  que escapam do diretório do pack (zip-slip), ou qualquer indício de que o
  pack tenta empacotar bytes de execução em vez de dados declarativos;
- há um problema óbvio de conteúdo/licenciamento (ex.: assets extraídos da
  ROM sem direito de distribuição, ou créditos claramente ausentes).

## Antes de enviar

- **Direitos de distribuição.** O pack MUST NOT conter bytes da ROM nem
  assets extraídos dela sem direito de distribuição — a responsabilidade é
  do autor do pack (MEP-v1.md §1). É por isso que a caixa de confirmação no
  formulário de submissão é obrigatória.
- **`pack.json` válido.** Confira contra o exemplo em MEP-v1.md §3: campos
  `mep`, `name`, `version`, `targets` (com `sha1` No-Intro da ROM) e
  `sections` são obrigatórios.
- **Rode o lint localmente antes de submeter**, se possível:
  `python3 scripts/mep_lint.py <pasta-ou-zip-do-pack>`.
- **Link de download direto**, hospedado em um dos hosts aceitos: release
  do GitHub, `raw.githubusercontent.com`, ou gist. Links para páginas HTML
  (não para o arquivo em si) não são aceitos automaticamente.

## Depois de enviar

Um comentário automático na issue registra o veredito, a seção da spec que
o embasa, e move o item no board. Se você atualizar o pack no mesmo link
depois de um veredito, comente `/revalidate` na issue para disparar uma
nova checagem — o hash do conteúdo é sempre recomputado, então uma
mudança real no pack é detectada mesmo sem esse comando (checagem
periódica de drift).
