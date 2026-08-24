# Extensão hires.txt para GB/SMS — v1-draft (proposta)

**Status:** **v1-draft / proposta — pendente de revisão pela comunidade
HDNes/Mesen antes de qualquer congelamento** (ADR-0004). Nada aqui é final;
mudanças a partir de feedback são revisões do draft, não breaking changes. ·
**Licença desta spec:** CC0-1.0 ·
**Golden file:** [`golden/hires-gbsms/hires.txt`](golden/hires-gbsms/hires.txt) ·
**Validação:** `scripts/validate-specs.py`

As palavras-chave MUST/SHOULD/MAY (RFC 2119) expressam a *intenção da
proposta*, condicionada ao status de draft acima.

## 1. Motivação

O formato HDNes `hires.txt` (implementação de referência: Mesen,
`Core/NES/HdPacks/`, versão de formato corrente `<ver>109`) cobre apenas o
PPU do NES. GB e SMS são igualmente tile-based e não têm padrão de HD pack;
replacement de áudio OGG para GB/SMS também não tem padrão (MSU-MD cobre só
Mega Drive). Esta proposta estende o formato existente de forma
**retrocompatível**, usando o campo `<ver>` que o formato já possui, em vez
de criar um formato novo.

## 2. Estratégia de compatibilidade

1. A extensão é sinalizada por `<ver>200` ou maior (faixa 2xx reservada aos
   sistemas não-NES; a linha 1xx continua pertencendo ao NES/HDNes clássico).
2. Um novo tag obrigatório `<system>` declara o PPU alvo. Loaders NES antigos
   já rejeitam `<ver>` acima do que conhecem — nenhum pack antigo quebra e
   nenhum pack novo é meio-carregado por um loader velho.
3. Todos os tags existentes mantêm sintaxe e semântica
   (`<scale>`, `<img>`, `<tile>`, `<background>`, `<condition>`, `<bgm>`,
   `<sfx>`, `<options>`, `<overscan>`, `<patch>`, `<addition>`,
   `<fallback>`), reinterpretados apenas onde o hardware difere (§3).

## 3. Tags novos / reinterpretados

### 3.1 `<system>` (novo, MUST em `<ver>` ≥ 200)

```
<system>gb | gbc | sms | gg | sg1000 | coleco
```

### 3.2 `<tile>` — chave de tile por sistema

A chave de identidade do tile (hoje: dados do tile NES + paleta) passa a ser
definida por sistema. Decisão registrada em ADR-0036 (GB/GBC) e ADR-0037
(SMS/GG): a chave usa sempre os **valores** de paleta aplicados no momento da
captura (nunca índices/slots, que são realocados dinamicamente pelos jogos),
seguindo o precedente do formato NES — é isso que garante replacement 1:1.

| Sistema | Dados do tile | Chave de paleta (campo hex único) |
|---|---|---|
| `gb` (DMG) | 16 bytes 2bpp | `TTPP` — TT: `00`=BG, `01`=OBJ; PP: valor do registrador BGP/OBPx aplicado |
| `gbc` | 16 bytes 2bpp | `TT` + 4×RGB555 big-endian da paleta CGB aplicada (18 hex) |
| `sms` | 32 bytes 4bpp (VDP mode 4) | `TT` + base CRAM (`00`/`10`) + snapshot das 16 entradas CRAM RGB222 (36 hex) |
| `gg` | 32 bytes 4bpp (VDP mode 4) | `TT` + base CRAM (`00`/`10`) + snapshot das 16 entradas CRAM RGB444 big-endian (68 hex) |
| `sg1000`/`coleco` | 8 bytes 1bpp (TMS9918) | par cor-frente/cor-fundo do pattern (draft; fora da v1 do builder) |

Notas normativas (MUST): banco VRAM (GBC) e espelhamento H/V ficam **fora**
da chave de identidade — banco só organiza as folhas PNG dumpeadas e
espelhamento é atributo de exibição, como no NES. Os dados do tile são
gravados na orientação canônica (sem espelhos).

Formato textual: os mesmos campos separados por vírgula do formato atual —
`<tile>png,dadosHex,chavePaletaHex,x,y,brilho,defaultTile` — com os dados do
tile em hex e a chave de paleta conforme a tabela.

### 3.3 `<background>` / `<condition>`

Mantidos. Condições dependentes de endereço de PPU NES ganham equivalentes
por sistema (ex.: `spriteNearby`, `memoryCheck` sobre o barramento do
sistema alvo). Draft: a lista exata de condições portáveis será fechada com
a comunidade.

### 3.4 `<bgm>` / `<sfx>` (áudio OGG para GB/SMS — o vão do PRD §4.1)

Sintaxe idêntica à atual (`<bgm>id,arquivo.ogg[,loopPoint]`), com o gatilho
definido por sistema: endereço+valor de RAM/registrador que identifica a
faixa corrente (mesmo mecanismo `memoryCheck` das condições). O host toca o
OGG via seu mixer nativo (OggMixer no MesenCE), duckando o chip conforme já
faz no NES.

## 4. Fora de escopo deste draft

- Modos não-tile (SMS mode 0-3 legado além do TMS9918 básico).
- Normal/texture maps e shaders (território do SUPER ZSNES; ver PRD §6).
- Qualquer mudança no pipeline NES existente.

## 5. Processo

Discussão pública (issue no fork MesenCE + thread na comunidade
HDNes/Mesen) antes de congelar como `hires-gbsms-v1.md`. Implementações
experimentais MUST tratar `<ver>2xx` como instável até o congelamento.

## 6. Golden file

[`golden/hires-gbsms/hires.txt`](golden/hires-gbsms/hires.txt) — exemplo
canônico mínimo de um pack GB (validado sintaticamente por
`scripts/validate-specs.py`; a semântica permanece draft).
