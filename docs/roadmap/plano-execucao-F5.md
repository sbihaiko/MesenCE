# Plano de execução — Fase 5: Bootstrap automático de packs (convenção sobre configuração)

**Status:** proposto (2026-08-25) — nenhum código iniciado; ADR-0044, 0047 e **0049** em `.dev-squad/adr/` com status `proposed` (0045/0046/0048 superseded pelo 0049), a resolver na F5.0 antes de qualquer implementação ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) §Fase 5 (re-escopada) ·
**Spec:** [MEP-v1.md](../specs/MEP-v1.md) (ganha `patches[]` e a convenção de pasta irmã; `pack.json` passa a ser opcional) ·
**Ordem:** proposta de antecipar a F5 à F4 (browser/MEI): sem packs bons e fáceis de produzir, um browser lista um catálogo vazio. A F4 fica intacta no PRD e entra depois.
**Processo:** ADRs primeiro (F5.0), depois blocos F5.1→F5.5, cada um com validação headless via `scripts/headless_record` como nas fases 1–3.

## Princípio: convenção sobre configuração (ADR-0049)

> Rodar um jogo gera, ao lado da ROM e com o mesmo nome, uma pasta com
> texturas e áudio otimizados automaticamente. Essa pasta **é** o pack e é o
> ponto de partida do artista.

Consequências de desenho, todas para eliminar mapeamento:

- **Sem `pack.json` obrigatório** — hash e sistema vêm da ROM ao lado; o
  `pack.json` só existe para publicar (`mep pack` gera).
- **Duas camadas por localização** — `auto/` é da máquina (regenerável à
  vontade); tudo fora de `auto/` é humano e nunca é tocado. Precedência por
  entrada: humano > `auto/`. Nada de ids de camada nem `provenance.json`.
- **Nomes são chaves** — `audio/bgm/<faixa>.ogg` substitui a faixa de mesmo
  nome em `auto/`; `textures/sheets/<objeto>.png` substitui as células do
  sheet gerado de mesmo nome. O `hires.txt` é sempre **gerado** (`mep build`).
- **Pasta local vence o zip** — ordem: pasta irmã > `HdPacks/<Game>/` (legado)
  > `EnhancementPacks/` (pastas e zips). O artista trabalha na pasta ao lado da
  ROM sem desinstalar/desligar nada; a pasta zipada tal como está (`<Game>.zip`,
  sem `pack.json`) instala no emulador como pack completo.
- **Gatilho automático** — setting "Bootstrap enhancement folder" (default on):
  no load, se a pasta não existe ou o gerador é mais novo, grava durante o jogo
  e materializa `auto/` no unload/power-off.

```
<dir>/Mega Man 3 (USA).nes
<dir>/Mega Man 3 (USA)/
  textures/  hires.txt (gerado)  sheets/*.png (editáveis)
  audio/     bgm/*.ogg  sfx/*.ogg  midi/*.mid  stems/*_ch<n>.wav
  synth/     preset.cfg
  auto/      textures/  audio/  synth/       ← regenerado, nunca editar
  .bootstrap (versão do gerador, sha1, timestamps)
```

## Origem: o que dois packs reais ensinaram (2026-08-24/25)

Instalamos e rodamos o **Contra80s** (HDNes, NES CHR RAM) e o **Zelda Remastered v1.3**
(HDNes, PRG0 + IPS + 10 BGM/42 SFX OGG) no MesenCE.

| Observação | Pack | Resposta neste plano |
|---|---|---|
| Jogo CHR RAM: exportação estática (ADR-0043) não cobre nada; só gravação | Contra | Bootstrap une **export + gravação** enquanto se joga; relatório de cobertura |
| `Stage1.png` inexistente e `tileNearby` sobre `<background>` só aparecem no log do load | Contra | **Linter** (F5.1) rodando no `mep build` e no Install da UI |
| 53 warnings ignorados por anos | Zelda | idem |
| `tileNearby` com offsets grandes para desambiguar tiles iguais em contextos diferentes | Zelda | Conditions candidatas **inferidas da gravação** (F5.4), comentadas `# inferred` |
| Offset 1 px além da tela derrubou o emulador (off-by-one upstream, corrigido) | Zelda | Linter valida coordenadas; host mantém as checagens |
| Áudio depende de **IPS** que altera o código do jogo; amarrado a um sha1 | Zelda | `patches[]` por hash + normalização de dump (ADR-0044); gatilho **sem patch** por fingerprint da APU (ADR-0047) |
| Pasta alternativa com SFX 8-bit = "níveis" na mão | Zelda | Camada humana vs. `auto/` por convenção (ADR-0049) |
| Nenhum arquivo diz de onde veio um asset | ambos | Proveniência **pela pasta**: `auto/` = máquina |

## Critério de sucesso (PRD §F5, reescrito)

> Jogar 5 minutos gera, ao lado da ROM, uma pasta com o jogo **melhorado**
> (imagem nível 2, som nível 2/3) sem nenhuma configuração; a partir dela um
> artista chega a um pack **publicável** em < 1 h editando só PNG/OGG.

Alvos de validação: **Mega Man 3** (NES CHR ROM), **Contra** (NES CHR RAM),
**Link's Awakening** (GB), **Sonic** (SMS). Cada bloco fecha com screenshot/log
headless comparável ao baseline.

## A escada de níveis

Imagem: 0 original · 1 filtro global (xBRZ runtime, sem pack) · **2 auto**
(tiles ROM + capturados → upscale por tile, em `auto/textures`) · **3 enhanced**
(tiles agrupados em objetos, upscale por objeto, sheets) · **4 conditions
inferidas** · **5 arte** (humano edita sheets).

Som: 0 APU · **1** Enhanced Audio tempo real (F1) · **2** preset ESP do jogo
(`synth/preset.cfg`) · **3 auto** (MIDI/VGM → soundfont → OGG em `auto/audio`)
· **4 arranjo semi-auto** (MIDI reinstrumentado) · **5 arte** (músico substitui
`audio/bgm/<faixa>.ogg` a partir de `midi/` e `stems/`).

Níveis 2–4 vivem em `auto/`; o 5 fora dela. Só isso.

## Estado do terreno (verificado no código em 2026-08-25)

| Ponto | Situação |
|---|---|
| Export estático de tiles | ✅ ADR-0043 |
| Gravação de tiles + merge | ✅ F2 (GB/SMS) e upstream (NES) |
| Upscale por tile em lote | ❌; xBRZ/HQx existem **em runtime** (`Core/Shared/Video/`) — reutilizáveis offline pelo core (sem dependência externa) |
| Exportar MIDI/VGM | ✅ F1, headless |
| Saber **qual música tocou quando** | ❌ MIDI contínuo; sem segmentação nem gatilho (ADR-0047) |
| Render MIDI → OGG | ❌ externo (fluidsynth + soundfont livre); sem ele `auto/audio` fica só com MIDI |
| `<bgm>/<sfx>` NES | ✅ `HdAudioDevice` + `OggMixer`; exige escrita em `$4100+` → hoje só com IPS |
| `<bgm>/<sfx>` GB/SMS | ❌ (ADR-0041) — fora até o freeze do draft |
| Descoberta de pack | `HdPacks/<rom>/` e `EnhancementPacks/`; ❌ pasta irmã da ROM |
| Alvos múltiplos MEP | ✅ `targets[]`; ❌ `patches[]`; ❌ normalização de dump |
| Linter | ❌ só logs no load |
| Gravação contínua em background durante o jogo | ❌ o builder grava só quando a janela está aberta |

## F5.0 — ADRs da fase (bloqueia o resto)

1. **ADR-0049 — Pasta irmã como pack** (localização, layout fixo, duas camadas
   por pasta, gatilho no load, fallback para `EnhancementPacks/<Game>/` quando
   a pasta da ROM não é gravável).
2. **ADR-0044 — Alvos permissivos**: normalização do dump (trailing `00` além
   do tamanho do header iNES) + `patches[]` por sha1; patch pulado com aviso
   quando não casa; toggle opt-in "ignorar hash do patch".
3. **ADR-0047 — Gatilho de BGM/SFX sem patch**: fingerprint das escritas da
   APU (mesmo tap do exportador F1) → eventos para `OggMixer`; confirmação em
   K frames; convive com o mecanismo IPS.
4. Decidir na F5.0: (a) o upscale roda **no core** (reuso do xBRZ, zero
   dependência) ou em `scripts/`; recomendação: core para imagem, `scripts/`
   para render de áudio (PRD: IA/ferramentas pesadas nunca embutidas).
   (b) política de gravação em background: buffer limitado (ex.: 10 min de
   tiles únicos + MIDI), custo de CPU medido no harness.

## F5.1 — Descoberta pela pasta irmã + linter + host permissivo

**Entrega:** uma pasta `<Game>/` criada à mão (só `textures/hires.txt`) já
carrega; linter offline; `patches[]`.

- `MepPackManager`: escaneamento da pasta irmã `<dir da ROM>/<nome sem extensão>/`
  → pack sintético (target = sha1 da ROM, sistema = da ROM, seções = pastas
  presentes, `auto/` como segunda fonte). Ordem: **irmã > `HdPacks/` > `EnhancementPacks/`**.
  Zips em `EnhancementPacks/` sem `pack.json` casam pelo nome (= nome da ROM),
  com o mesmo layout da pasta.
- Validação: pasta irmã + zip idêntico instalado → log mostra a pasta vencendo;
  apagar a pasta → zip assume, screenshot igual.
- Merge humano > `auto/` por entrada nos três loaders (NES hires.txt, GB/SMS
  `HdTilePack`, audio hires.txt, ESP: `auto/synth/preset.cfg` < `synth/preset.cfg` < usuário).
- `scripts/mep_lint.py <pasta|zip>`: pack.json (se houver), hires.txt (arquivos
  existem, conditions permitidas por tipo, coordenadas 256×240, offsets
  `*Nearby` no range), chaves duplicadas, PNG múltiplo do scale. Exit ≠ 0 em
  erro. Oráculo: Contra80s (4 erros) e Zelda (53 warnings + o offset do crash).
- ADR-0044 no core (`ComputeNoIntroSha1`, `MepPack::Parse`, `NesConsole::LoadHdPack`).
- Validação headless: Zelda com os três dumps do usuário → texturas nos três,
  patch só no trimmed; GB 1:1 com pack em pasta irmã; `mep-off` inalterado.

## F5.2 — Bootstrap de imagem (nível 2)

**Entrega:** jogar gera `auto/textures/` com tiles upscalados; setting on/off.

- Gravação em background (sem janela do builder): export ROM (ADR-0043) no
  load + captura de tiles únicos enquanto joga (buffer limitado).
- No unload/power-off: upscale xBRZ 4× tile a tile (core) → `auto/textures/hires.txt`
  + PNGs; `.bootstrap` com versão/sha1; `textures/sheets/` **vazio** ainda
  (F5.4) — mas `hires.txt` humano gerado como cópia editável? **Não**: o
  hires.txt humano só nasce do `mep build` a partir de sheets. Antes de F5.4,
  o artista pode editar os PNGs de `auto/` copiando-os para `textures/` com o
  mesmo nome (nome = chave).
- Relatório de cobertura no log e na janela HD Pack Builder (tiles vistos vs.
  com arte; aviso CHR RAM — lição Contra).
- Validação: MM3, Contra, LA, Sonic → segundo load carrega `auto/`; screenshot
  headless ≈ xBRZ runtime.

## F5.3 — Bootstrap de som (nível 3) + gatilho sem patch

**Entrega:** `auto/audio/` com MIDI por faixa (+ OGG quando fluidsynth existe) e
`fingerprints.json`; playback via fingerprint.

- Segmentação do MIDI/VGM gravado em faixas (silêncio / reinício de padrão /
  mudança de tempo) → `audio/midi/<faixa>.mid` + assinatura.
- `scripts/mep_render_audio.py` (fluidsynth + soundfont livre → OGG q5) chamado
  pelo emulador se disponível; senão log com instrução.
- Host: `FingerprintMatcher` (ADR-0047) alimenta `OggMixer`; `audio/bgm/<faixa>.ogg`
  (humano) vence `auto/audio/bgm/<faixa>.ogg`.
- Validação headless: MM3 título → `[MEP] audio: fingerprint match 'title'` em
  < 30 frames; APU silencia; zero falso positivo em 60 s.

## F5.4 — Sheets, objetos e conditions inferidas (níveis 3–4)

- Co-ocorrência espacial nos frames gravados → objetos; sprites via OAM.
- Upscale por objeto → `auto/textures`; `textures/sheets/<objeto>.png` gerados
  (editáveis) + ordem das células em comentário do hires.txt gerado.
- `scripts/mep_build.py <pasta>`: sheets → tiles → `textures/hires.txt`; OGG
  novos em `audio/`; roda o linter. `mep pack <pasta>` → zip MEP com `pack.json`.
- Tiles ambíguos → `tileNearby` candidatas `# inferred` para revisão.
- Validação: MM3 vira objetos coerentes; Zelda Remastered como oráculo de
  conditions (métrica, não gate).

## F5.5 — Fechamento

- UI: setting do bootstrap; HD Pack Builder com "Abrir pasta do jogo", cobertura,
  preview antes/depois; Enhancement Packs lista a pasta irmã com origem "sibling".
- Specs: MEP-v1 §pasta irmã e `patches[]` (minor 1.1; `pack.json` opcional só
  para a forma-pasta); golden atualizado; `validate-specs.py`.
- README/PRD §F5; regressões F1–F3; dotnet build 0 warnings.

## Riscos

| Risco | Mitigação |
|---|---|
| Poluir a biblioteca de ROMs com pastas | setting (default on, um clique para off); fallback para `EnhancementPacks/` quando não gravável |
| Custo de CPU da gravação em background | buffer limitado, medição no harness, desliga se frame time subir |
| Fingerprint com falso positivo | K frames, tolerância por faixa, fallback IPS, toggle |
| Upscale automático "genérico" | é bootstrap, não produto; sheets reduzem o custo do manual |
| Dependências externas para áudio | opcionais; sem elas o bootstrap entrega MIDI |
| Evoluir o formato quebrar v1 | tudo aditivo; pasta sem `auto/` = pack comum |

## Fora desta fase

- Browser/índice MEI (F4) — depois.
- OGG GB/SMS (freeze do draft).
- Upscale por modelo ML — entra como alternativa ao xBRZ em `scripts/`, depois.
- Realocação automática de IPS entre revisões.
