# Plano de execução — Fase 5: Bootstrap automático de packs (convenção sobre configuração)

**Status:** em execução (2026-08-25) — F5.0 ✅ parcial (ADR-0044 e ADR-0049 aceitos; ADR-0047 aceito na F5.3; 0045/0046/0048 superseded), **F5.1 ✅** (pasta irmã > `HdPacks/` > `EnhancementPacks/`; zip/pasta nomeados como a ROM sem `pack.json`; merge humano > `auto/` nos loaders NES/GB/SMS/ESP; `patches[]` + normalização do hash iNES + override `ApplyPatchOnHashMismatch` na UI; `scripts/mep_lint.py`; 28 checagens headless — GB 1:1 em 5 cenários, Zelda com 3 dumps, patch skip/apply; dotnet 0 warnings) · **F5.2 ✅** (setting `BootstrapEnhancementFolder`, default on: no load sem nenhum pack de texturas, exporta tiles da ROM + grava os tiles jogados com xBRZ 4× em `<Game>/auto/textures/` (+ `.bootstrap`); fallback `EnhancementPacks/<Game>/` quando a pasta da ROM é somente-leitura; segundo load já usa a camada; botão *Open Game Folder*; 18 checagens headless — GB, SMB3 CHR ROM 8275 tiles, Zelda CHR RAM, opt-in, pasta RO) · **F5.3 ✅** (gravador de música no bootstrap NES: `NoteFrame` por frame a partir do estado do APU → `TrackSegmenter` (silêncio 60 frames fecha; ≥180 frames = `bgm`, senão `sfx`) → `auto/audio/fingerprints.json` + `midi/<id>.mid` (SMF/GM); `scripts/mep_render_audio.py` renderiza `bgm/<id>.ogg` (fluidsynth+SoundFont ou sintetizador interno numpy → ffmpeg libvorbis); no load, `NesAudioReplacer` carrega as camadas `auto/audio` → `audio` (id humano vence), reconhece a faixa pelos primeiros onsets (±3 frames, confirma em 8) e toca o OGG pelo `HdAudioDevice` silenciando pulse/triangle/noise; 90 frames de silêncio restauram o APU; 12 checagens headless com Zelda — grava, renderiza, segundo load `fingerprint match 'track01' … APU muted`, camada humana, aviso sem OGG) · **F5.4 em progresso** — reordenada pela evidência do `mep_compare.py` (ADR-0050): **F5.4a ✅ telas estáticas** (`auto/textures/backgrounds/screenNNN.png` de tela inteira sem sprites + 3 âncoras `tileAtPosition` + `<background>…,20`; não mesclada sob camada humana; 21 checagens headless em Zelda/Mega Man/Excitebike; bugs de serialização de `<background>`/`<condition>` corrigidos) · **F5.4a′ ✅ assets sem jogar**: export estático agora cobre jogos CHR RAM por varredura da PRG (alinhamento votado por banco + churn da silhueta; 87–91 % dos tiles do Zelda, 80–83 % Castlevania, 99 % Mega Man) e a rampa cinza é recolorida com a paleta real ao desenhar (antes um pack só-export renderizava o jogo em cinza); `*.orig.png` como referência sem filtro; 24 checagens headless (emenda da ADR-0043) · **F5.4f spike ✅ (ADR-0051, proposto)**: `scripts/spike_sound_driver` descobre o driver de som do jogo com o debugger (breakpoints de escrita no APU → tick; scan de `JSR` por endereço absoluto → entrada "tocar N" + registrador do id) e enumera as faixas chamando a entrada com cada id sobre um save state do título — Mega Man: `S=$9003`, `A=id`, ids 0–50 → 18 bgm + 22 sfx + 11 curtíssimos, 40 assinaturas distintas, sem jogar; com `SPIKE_BOOTSTRAP=1` o gravador F5.3 escreveu 50 faixas (18 bgm + 32 sfx) em `fingerprints.json` + 50 MIDI numa rodada de 5 min · F5.4b variantes de paleta, F5.4c `mep_build.py`, F5.4d cobertura na UI, F5.4e sheets/objetos pendentes · **F5.4g Bloco A ✅** (som nível 2, ADR-0052: `ChannelRoleClassifier` decide por janela qual canal é lead/harmonia/baixo e quais estão tocando SFX — sweep de hardware rápido, glissando ≥ 7 st, retriggers não periódicos ≥ 3 st, agudo > A7 — com histerese e troca só em fronteira de nota; SFX renderizados secos fora dos sends; `EnhancedSynthEngine` toca as vozes de música e a percussão por **TinySoundFont** quando há `.sf2` (`EnhancedAudio.SoundFontPath` ou `<home>/EnhancedAudio.sf2`), fallback ao DSP; settings/UI `EnhancedAudioAutoRoles`/`EnhancedAudioSfxSeparation`/SoundFont; `scripts/roles_probe` valida headless: SMB 18/18 pulos como SFX, Zelda título 1 falso positivo de 0,08 s em 30 s, Mega Man/Castlevania papéis coerentes; GB/SMS passam pelo mesmo roteamento) · Blocos B–D pendentes · F5.5 pendente ·
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

Som (revisada em 25/08, ver F5.4g): 0 APU · **1** Enhanced Audio tempo real
(F1: papéis fixos pulse1=lead / pulse2=harmonia / triangle=baixo, timbres DSP)
· **2 cover GM automático** (papel do canal por janela, SFX separados da música,
arpejo→acorde, expressão do APU → instrumento GM via SoundFont em tempo real;
ajuste humano opcional em `synth/preset.cfg`) · **3a faixas identificadas**
(máquina: fingerprint + MIDI-semente em `auto/audio`, gravando enquanto se joga
ou dirigindo o driver do jogo — F5.3/F5.4f; não muda o som por si) · **3b arte**
(músico substitui `audio/bgm/<faixa>.ogg`; o host troca no momento certo).

O nível 2 é o que todo usuário ouve no primeiro load de qualquer ROM; 3a alimenta
3b; 3b sobrepõe o 2 só nas faixas que existirem. Nível 3a vive em `auto/`; 3b fora
dela. Só isso.

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
   **Decidido na F5.2:** (a) upscale **no core** — o HD Pack Builder já
   aplica xBRZ/HQx/Scale2x por tile ao salvar, então o bootstrap é o builder
   existente apontado para `auto/textures` com xBRZ 4×; (b) a gravação usa o
   builder tal como está (dedup por chave, sem buffer extra) e só roda quando
   **nenhum** pack de texturas se aplica — com a camada `auto/` presente o
   segundo load não regrava (o builder troca o PPU e esconderia o pack).

## F5.1 — Descoberta pela pasta irmã + linter + host permissivo ✅

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

## F5.2 — Bootstrap de imagem (nível 2) ✅

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

**Como ficou (✅):** o gravador vive no core (`NesAudioBootstrap`, alimentado
após `_apu->EndFrame()`), não no exportador F1 — sem GUI e sem depender do
Enhanced Synth estar ligado. Faixas recebem ids `track01…`/`sfx01…` (o artista
renomeia no `fingerprints.json` humano). O render em OGG fica fora do emulador
(`mep_render_audio.py`; sem fluidsynth usa um chip-synth interno como
placeholder). MM3 e SMB3 não tocam música nos primeiros segundos sem input, por
isso a validação usa Zelda (título com música desde o frame ~60). Latência de
reconhecimento = 8 onsets (~1 s no tema do Zelda) — o começo da faixa sai do
APU, o OGG entra a partir daí; ADR-0047 registra a troca.

## F5.4 — Sheets, objetos e conditions inferidas (níveis 3–4)

**Ordem revisada em 25/08 (ADR-0050)** — a comparação com Castlevania/Contra80s/
Zelda Remastered (`scripts/mep_compare.py`) mostrou que o artista trabalha em
telas e contexto, não em tiles: (a) ✅ capturar telas estáticas como
`<background>` com âncoras `tileAtPosition`; (b) variantes de paleta
automáticas (7,6 paletas por bitmap no Zelda); (c) `mep_build.py`; (d)
cobertura "do que você jogou" na UI; (e) só então sheets/objetos — exigem
mais cobertura do que 12–29 % de poucos minutos de jogo.

- Co-ocorrência espacial nos frames gravados → objetos; sprites via OAM.
- Upscale por objeto → `auto/textures`; `textures/sheets/<objeto>.png` gerados
  (editáveis) + ordem das células em comentário do hires.txt gerado.
- `scripts/mep_build.py <pasta>`: sheets → tiles → `textures/hires.txt`; OGG
  novos em `audio/`; roda o linter. `mep pack <pasta>` → zip MEP com `pack.json`.
- Tiles ambíguos → `tileNearby` candidatas `# inferred` para revisão.
- Validação: MM3 vira objetos coerentes; Zelda Remastered como oráculo de
  conditions (métrica, não gate).

### F5.4f — Áudio sem jogar (spike ✅ Mega Man, ADR-0051)

O gravador F5.3 só vê o que o jogador toca. `scripts/spike_sound_driver`
(`make spike-sound-driver`) mostra que dá para **dirigir o driver de som do
próprio jogo** sem conhecimento por jogo: (A) breakpoints de escrita em
`$4000–$4017` + callstack → rotina de tick `P` e região do driver; (B) `JSR`s
de fora do banco do driver para dentro dele, quebrados por endereço absoluto
durante um Start pulsado → entrada `S` e registrador do id; (C) para cada id,
recarrega o save state do título, para em `P`, `PC=S`, `A=id`, retorno para um
`JMP` em RAM, e amostra o APU por 4 s. Mega Man: 18 bgm, 22 sfx, 11 curtíssimos
nos 51 ids válidos; o gravador F5.3 produziu 50 faixas + MIDI na mesma rodada.
Generalização (12 ROMs da biblioteca, validação empírica: ≥3 ids distintos e
mesmo id reprodutível em dois save states, por onsets *novos*): Mega Man,
Castlevania (`JSR`), Zelda `$0600/$0602`, Punch-Out `$0722`, SMB3 `$04F5/$04F1`
(caixa postal via trace) ✅; Ninja Gaiden ⚠️; 1943/Contra/Excitebike/Gauntlet/
SMB1/Bomberman ❌ (pedido não acontece na janela título→Start). Decisão
proposta (ADR-0051): entregar como ferramenta opt-in (*Extract audio*), não
automática no load — item 11 da F5.4g.

### F5.4g — Som nível 2: cover GM automático (ADR-0052; Bloco A ✅ 25/08)

Hoje o `EnhancedSynth` (F1) ressintetiza o APU com papéis fixos e timbres DSP:
funciona em qualquer jogo, mas o pulo do Mario toca com timbre de lead e o baixo
vira melodia quando o compositor troca os canais. O nível 2 é o teto do que dá
para fazer **sem saber a música** — um cover GM decente, automático, com SFX
intactos. Tudo em tempo de execução, sem `auto/`, sem passo humano.

| # | Item | Automático | Como |
|---|---|---|---|
| 1 | Papel do canal por janela | ✅ feito | `ChannelRoleClassifier` (Core/Shared/Audio): média exponencial ~1 s de registro, onsets/s e fração audível; baixo = canal mais grave se ≤ C4 e ≥ 5 st abaixo do seguinte (senão o canal padrão), lead = maior `registro + 2·onsets/s` com margem de 4 sobre o atual; troca só após 3 decisões (0,75 s) e na fronteira de nota dos canais envolvidos |
| 2 | SFX × música | ✅ feito | cues: sweep de hardware rápido (≥ 12 st/s, ≥ 4 st), glissando por software ≥ 7 st a ≥ 12 st/s (o título do Zelda desliza 6 st), ≥ 5 retriggers em 140 ms cobrindo ≥ 3 st sem ciclo de 2–4 notas (arpejo/vibrato ficam música), nota > A7; segura até 40 ms de silêncio ou 1,5 s de som contínuo; canal SFX vai para `Input::Sfx[]` = pulso seco sem eco/reverb; features do canal congelam durante o SFX. "Canal roubado e devolvido" ficou para o Bloco B |
| 3 | Arpejo → acorde | ✅ | alternância periódica de 2–4 notas a 20–60 Hz vira acorde sustentado |
| 4 | Expressão | ✅ | decay, vibrato, portamento extraídos do APU → escolha (pluck × sustentado × strings) e modulação da voz; hoje o `Input` só leva freq/vol/duty |
| 5 | Timbres reais | ✅ feito | `Utilities/Audio/tsf.h` (TinySoundFont, MIT) dentro do `EnhancedSynthEngine`: canais 0/1/2 = lead/harmonia/baixo (note on por ataque ou salto > 0,6 st, pitch wheel ±24 st segue o chip, volume do canal segue o envelope), canal 9 = percussão (hi-hat 42 / bumbo 36 / tom 45 por ataque do noise); programas por preset (`GmLeadProgram`/`GmHarmProgram`/`GmBassProgram`/`GmDrums`, harmonia com ataque rápido porque carrega arpejos); `.sf2` de `EnhancedAudio.SoundFontPath` ou `<home>/EnhancedAudio.sf2`, carregado no construtor/reset (nunca no mix); sem arquivo → DSP de antes. **Pendente (decisão do usuário):** embutir um SoundFont no repo/instalador — GeneralUser GS (31 MB, licença própria permissiva, procedência de algumas amostras incerta) ou MuseScore General (206 MB, MIT) |
| 6 | Override humano | parcial | os programas GM já são campos do preset, logo `synth/preset.cfg` (ESP) e `EnhancedAudioPresets.cfg` os sobrescrevem; papel fixo por canal fica para o Bloco B |
| 7 | Validação | ✅ feito | `scripts/roles_probe` (`make roles-probe`): roda a ROM headless com save state e input scriptado, alimenta o mesmo classificador com o APU amostrado e imprime timeline (papéis, segmentos SFX com o cue que disparou) + estatísticas; `--wav`/`--sf2` gravam a mixagem. Resultados 25/08: SMB1 18/18 pulos (sweep+glide+retrig), Castlevania chicote 3/3, Zelda título 1 falso positivo de 0,08 s/30 s (era 10 antes de calibrar sweep/glide), Mega Man 2 trocas de papel na transição título→stage select; WAV sem clipping, GM ~ mesmo RMS do DSP. Falta o ouvido na GUI |

Emendas ao 3a/3b (F5.3/F5.4f) que faltam para a substituição por OGG ser usável:
**8** ponto de loop no fingerprint (`LoopPosition` hoje é 0); **9** SFX
audíveis durante o OGG (hoje pulse/triangle/noise são mutados inteiros — depende
do item 2); **10** transição direta música→música e fade (hoje só 90 frames de
silêncio restauram o APU); **11** extração sem jogar como ferramenta opt-in
(*Open Game Folder → Extract audio*), janela mais longa/estímulos para Contra/SMB1
e gatilhos separados de música e SFX; **12** nomear/limpar ids enumerados; **13**
`mep_build.py`/`pack` com `audio/`, lint de áudio e tutorial "do MIDI-semente ao OGG".

Ordem: **Bloco A** 2→1→5→7 ✅ (muda o que todo usuário ouve) · **Bloco B** 3, 4, 6
(+ "canal roubado e devolvido", papel fixo por canal no ESP) · **Bloco C** 8, 9, 10 ·
**Bloco D** 11, 12, 13. Cada bloco do porte da F5.3.

Lições do Bloco A: o sweep de hardware **não** é sinal seguro de SFX (o driver do
Zelda o usa para slides musicais de 2 st); distância percorrida separa melhor que
velocidade (slides musicais ficam ≤ 6 st, efeitos passam de 8); um pad de ataque
lento na harmonia engole arpejos (RMS caiu 5× no Zelda até trocar o programa); o
makefile não rastreia headers — crescer `AudioConfig`/`EnhancedSynth` sem apagar
os `.o` dependentes deu `new` com `sizeof` velho e SIGSEGV no mix.

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
