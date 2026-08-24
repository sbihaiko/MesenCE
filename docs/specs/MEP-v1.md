# MEP v1 — MesenCE Enhancement Pack

**Status:** v1 (estável) ·
**Licença desta spec:** CC0-1.0 (domínio público) ·
**Versionamento:** semver — campo novo opcional = minor; mudança de semântica = major ·
**Golden file:** [`golden/mep/pack.json`](golden/mep/pack.json) ·
**Validação:** `scripts/validate-specs.py`

As palavras-chave MUST, MUST NOT, SHOULD e MAY seguem a RFC 2119.

## 1. Escopo e filosofia

MEP é um **envelope fino** que só *compõe* formatos já existentes: um pack é
um `.zip` (ou diretório solto) com um `pack.json` na raiz, identificado por
hash No-Intro da ROM, contendo seções opcionais que apontam para conteúdo em
formatos já padronizados — texturas (hires.txt/HDNes), áudio (OGG/MSU-1) e
preset de synth (ESP v1). MEP não define nenhum formato de conteúdo próprio.

Um pack MUST NOT conter bytes da ROM nem assets extraídos dela sem direito de
distribuição; a responsabilidade pelo conteúdo é do autor do pack.

## 2. Contêiner

1. Um pack é **ou** um arquivo `.zip` **ou** um diretório; hosts MUST aceitar
   ambos com semântica idêntica.
2. `pack.json` MUST existir na raiz do contêiner, UTF-8, JSON estrito.
3. Caminhos internos referenciados por `pack.json` são relativos à raiz,
   separador `/`, e MUST NOT escapar da raiz (entradas com `..` ou caminho
   absoluto tornam o pack inválido).
4. Armazenamento local (não normativo, referência MesenCE): pasta central por
   ROM no diretório do emulador, espelhando o padrão dos HD Packs
   (`HdPacks/<nome-da-rom>/`).

## 3. `pack.json`

```json
{
  "mep": "1.0.0",
  "name": "After Burner — Studio FM tuning",
  "version": "1.2.0",
  "author": "exemplo",
  "license": "CC0-1.0",
  "targets": [
    { "system": "sms", "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B", "crc32": "1C851C7E", "name": "After Burner (World)" }
  ],
  "sections": {
    "textures": { "path": "textures/" },
    "audio":    { "path": "audio/" },
    "synth":    { "path": "synth/preset.cfg" }
  }
}
```

### 3.1 Campos raiz

| Campo | Obrigação | Semântica |
|---|---|---|
| `mep` | MUST | versão da spec MEP visada (semver). Hosts MUST recusar major desconhecido e MAY aceitar minor mais novo ignorando o que não conhecem |
| `name` | MUST | nome humano do pack |
| `version` | MUST | versão do pack, semver |
| `author` | SHOULD | autor(es) |
| `license` | MUST | identificador SPDX do conteúdo do pack (ex.: `CC0-1.0`, `CC-BY-4.0`) |
| `targets` | MUST, ≥1 | ROMs às quais o pack se aplica (ver §4) |
| `sections` | MUST, ≥1 seção | conteúdo do pack (ver §5) |

### 3.2 Regras gerais

- Campos desconhecidos MUST ser ignorados (compatibilidade futura).
- Um pack casa com a ROM carregada quando **qualquer** entrada de `targets`
  casa (§4).

## 4. Identificação da ROM (contrato de hash)

A chave de matching é a convenção **No-Intro**: o hash cobre o *payload* da
ROM, não o invólucro do arquivo.

| `system` | Faixa hasheada |
|---|---|
| `nes` | arquivo **menos** o header iNES de 16 bytes e **menos** o trainer de 512 bytes quando presente (flags6 bit 2) |
| `gb`, `gbc`, `sms`, `gg`, `sg1000`, `coleco` | arquivo inteiro (formatos sem header de invólucro) |
| `snes` | arquivo menos o copier header de 512 bytes quando presente (`tamanho % 1024 == 512`) |

Formato dos campos (pinado ao output observado das utilities da implementação
de referência — `SHA1::GetHash`/`CRC32::GetCRC` do MesenCE):

- `sha1` (MUST): 40 dígitos hex **maiúsculos**.
  Exemplo observado: `2A4E126D0286BEA0BF503C80A12352C57539F76B`.
- `crc32` (SHOULD): 8 dígitos hex **maiúsculos**, big-endian textual (o valor
  `0x1C851C7E` escreve-se `1C851C7E`).
- Matching: `sha1` decide; `crc32` MAY ser usado como pré-filtro barato.
  Comparações MUST ser case-insensitive na entrada, mas produtores MUST
  escrever maiúsculas.

> Nota de implementação (MesenCE): `VirtualFile::GetSha1Hash()` hasheia o
> arquivo **inteiro**; para `nes` o host precisa hashear a faixa No-Intro
> (payload PRG+CHR), não o arquivo com header. Este é um requisito do host,
> não do autor do pack.

## 5. Seções

Cada seção é opcional; um pack precisa de ao menos uma. Hosts MUST oferecer
um toggle **independente por seção** (e SHOULD por camada interna, quando o
formato subjacente permitir).

### 5.1 `textures`

- `path` aponta para um diretório contendo um HD Pack no formato **HDNes
  `hires.txt`** (Mesen é a implementação de referência; para GB/SMS ver a
  extensão proposta em [`hires-gbsms-v1-draft.md`](hires-gbsms-v1-draft.md)).
- O host MUST delegar o carregamento ao seu loader de HD Pack existente
  (envelope, não parser próprio — ADR-0005).
- **Precedência (MUST):** um HD Pack solto instalado no diretório
  convencional do host (ex.: `HdPacks/<rom>/`) **prevalece** sobre a seção
  `textures` de um pack MEP instalado. Entre múltiplos packs MEP, o host MUST
  definir uma ordem determinística e documentada (referência: ordem de
  instalação, mais recente vence).

### 5.2 `audio`

- `path` aponta para um diretório com replacement de áudio em formato já
  suportado pelo sistema alvo: OGG por HD pack (NES, e GB/SMS via a extensão
  draft) ou MSU-1 (`.msu` + `.pcm`, SNES).
- O host MUST delegar ao mecanismo nativo correspondente (OggMixer, MSU-1).

### 5.3 `synth`

- `path` aponta para um arquivo no formato **ESP v1**
  ([`ESP-v1.md`](ESP-v1.md)).
- Overrides do pack aplicam-se **acima** dos defaults embutidos e **abaixo**
  do arquivo ESP local do usuário (o usuário sempre ganha).

## 6. Segurança

- Hosts MUST rejeitar, após normalização de caminho, qualquer entrada de zip
  que escape do diretório do pack (zip-slip).
- Hosts MUST NOT executar conteúdo de packs; tudo é dado declarativo.

## 7. Golden file

[`golden/mep/pack.json`](golden/mep/pack.json) — validado por
`scripts/validate-specs.py` (campos obrigatórios, semver, formatos de hash,
caminhos relativos seguros).
