# MEI v1 — MesenCE Enhancement Index

**Status:** v1 (estável) ·
**Licença desta spec:** CC0-1.0 (domínio público) ·
**Versionamento:** semver — campo novo opcional = minor; mudança de semântica = major ·
**Golden file:** [`golden/mei/manifest.json`](golden/mei/manifest.json) ·
**Validação:** `scripts/validate-specs.py`

As palavras-chave MUST, MUST NOT, SHOULD e MAY seguem a RFC 2119.

## 1. Escopo

MEI é o manifest de **descoberta** de packs MEP: um `manifest.json` estático
(hospedável em qualquer HTTP server ou repositório GitHub) listando packs com
nome, jogo, hash No-Intro, URL do artefato e checksum. Índices são
**federados**: qualquer pessoa MAY publicar um MEI e o usuário aponta o
emulador para ele; o índice oficial de um projeto é apenas mais um MEI, sem
privilégio de protocolo.

Um índice MUST listar apenas conteúdo que seu mantenedor pode distribuir
(presets, mapeamentos, composições originais licenciadas); conteúdo derivado
de terceiros circula fora do índice, em hubs próprios.

## 2. `manifest.json`

```json
{
  "mei": "1.0.0",
  "name": "Índice oficial MesenCE",
  "maintainer": "sbihaiko",
  "updated": "2026-08-24",
  "packs": [
    {
      "name": "After Burner — Studio FM tuning",
      "version": "1.2.0",
      "game": "After Burner (World)",
      "system": "sms",
      "rom": { "sha1": "2A4E126D0286BEA0BF503C80A12352C57539F76B", "crc32": "1C851C7E" },
      "mep": "1.0.0",
      "license": "CC0-1.0",
      "url": "https://example.org/packs/after-burner-studio-1.2.0.zip",
      "size": 18342,
      "sha256": "a3f1c2… (64 hex minúsculos do artefato .zip)"
    }
  ]
}
```

### 2.1 Campos do índice

| Campo | Obrigação | Semântica |
|---|---|---|
| `mei` | MUST | versão da spec MEI (semver); major desconhecido MUST ser recusado |
| `name` | MUST | nome humano do índice |
| `maintainer` | SHOULD | responsável |
| `updated` | SHOULD | data ISO 8601 da última atualização |
| `packs` | MUST | lista (possivelmente vazia) de entradas |

### 2.2 Campos de cada pack

| Campo | Obrigação | Semântica |
|---|---|---|
| `name`, `version` | MUST | espelham o `pack.json` do artefato |
| `game`, `system` | MUST | jogo alvo e sistema (valores de `system` como no MEP §4) |
| `rom` | MUST | `sha1` (40 hex maiúsculos, faixa No-Intro do MEP §4) e opcionalmente `crc32` |
| `mep` | MUST | versão da spec MEP do artefato |
| `license` | MUST | SPDX do conteúdo |
| `url` | MUST | URL do artefato `.zip` — **HTTPS obrigatório** |
| `size` | SHOULD | tamanho em bytes do artefato |
| `sha256` | MUST | SHA-256 do artefato, 64 hex (case-insensitive na leitura; produtores SHOULD escrever minúsculas) |

Campos desconhecidos MUST ser ignorados.

## 3. Modelo de confiança (normativo — ADR-0006)

Clientes MEI (o browser de packs de um emulador, ou qualquer outro):

1. MUST verificar o `sha256` declarado **antes** de extrair, ativar ou
   persistir o artefato, e MUST rejeitar a instalação em caso de mismatch.
2. MUST exigir HTTPS tanto na URL do manifest quanto nas URLs de artefato;
   `http:` MUST ser recusado (sem downgrade com aviso).
3. MUST rejeitar, após normalização de caminho, qualquer entrada de zip que
   escape do diretório de instalação do pack (zip-slip).
4. MUST exigir confirmação explícita do usuário ao adicionar/instalar a
   partir de um manifest que não seja o índice default do host.
5. SHOULD apresentar `license` e `maintainer` antes da instalação.

Essas regras são **contrato da spec**, não detalhe de implementação: clientes
de terceiros herdam as mesmas obrigações.

## 4. Ranking e telemetria

MEI não define telemetria. Hosts MAY ordenar por sinais públicos da
hospedagem (downloads/estrelas de release do GitHub, por exemplo). Clientes
MUST NOT enviar dados do usuário ao mantenedor do índice além do próprio GET.

## 5. Golden file

[`golden/mei/manifest.json`](golden/mei/manifest.json) — validado por
`scripts/validate-specs.py` (campos obrigatórios, semver, HTTPS, formatos de
hash).
