# PRD — Ecossistema de Enhancement Comunitário (MesenCE)

**Status:** rascunho · 
**Autor:** sbihaiko · 
**Data:** 2026-08-23
**Escopo:** fork MesenCE

---

## 1. Contexto e motivação

O MesenCE já possui o **Enhanced Audio** (synth paralelo ao APU acurado, presets por jogo em `EnhancedAudioPresets.cfg`, cobertura NES / GB / SMS+FM). O relançamento do **SUPER ZSNES** (zsnes.com, v0.300, 2026) validou comercialmente a mesma tese com seu
"Super Enhancement Engine": melhorias curadas jogo a jogo (hi-res manual, texture/normal maps, widescreen, overclock, replacement de áudio), todas individualmente desativáveis,
com dados de enhancement separados e livres de conteúdo copyrighted.

Este PRD define a evolução natural dessa tese no MesenCE: transformar o emulador em
**plataforma de extração, autoria e consumo de packs de enhancement**, com a comunidade
produzindo o conteúdo — mantendo o projeto juridicamente limpo.

O Mesen já traz duas fundações prontas:

| Fundação | Onde | O que dá de graça |
|---|---|---|
| NES HD Packs (formato HDNes) | `Core/NES/HdPacks/` | Replacement de tiles + áudio OGG (`OggMixer`), condições por contexto, **HD Pack Builder** (gravador de tiles) |
| MSU-1 | `Core/SNES/Coprocessors/MSU1/` | Padrão aberto de áudio em streaming p/ SNES, ecossistema comunitário existente (Zeldix) |
| Enhanced Synth Engine | `Core/Shared/Audio/EnhancedSynthEngine.*` | Tap que já converte estado de registradores em abstrações de nota/voz — ~90% de um exportador MIDI |

## 2. Objetivos

1. Permitir que qualquer usuário **extraia localmente** os assets visuais e musicais do
   jogo que está rodando (tiles → PNG; música → MIDI/VGM).
2. Definir um **formato de pack unificado** (texturas + áudio + preset de synth),
   identificado por hash da ROM, editável pela comunidade.
3. Oferecer **descoberta e instalação de packs dentro da UI** (browser de packs), com
   ranking por uso, consumindo manifests configuráveis.
4. Disponibilizar um **pipeline offline de AI** que gere o primeiro rascunho de packs
   (upscale de tiles, afinação assistida de presets), para a comunidade refinar à mão.

### Não-objetivos (explícitos)

- **Não** hospedar, embutir ou distribuir conteúdo derivado (MIDIs extraídos, covers,
  texturas redesenhadas de terceiros) em nenhum repositório do projeto.
- **Não** embutir qualquer mecanismo P2P/torrent de compartilhamento no emulador
  (risco de responsabilidade por indução — *MGM v. Grokster*, 2005; precedente Yuzu, 2024).
- **Não** monetizar packs ou o canal de distribuição.
- **Não** enviar nada para upstream (trabalho vive só no fork).

## 3. Princípios de arquitetura legal

O copyright musical tem duas camadas: a **gravação/código** (escapamos: MIDI gerado não
contém bytes da ROM) e a **composição** (não há escape por formato: MIDI extraído é
transcrição da obra, como partitura). O mesmo vale para tiles extraídos. Logo:

1. **Distribuir a ferramenta, nunca os arquivos.** Extratores são legais
   (interoperabilidade); os outputs ficam na máquina do usuário.
2. **Canal oficial só com conteúdo limpo:** presets de synth, mapeamentos por hash,
   manifests, ferramentas, composições originais licenciadas (CC).
3. **Conteúdo derivado circula nos hubs comunitários existentes** (Zeldix p/ áudio SNES,
   VGMusic p/ MIDIs, GitHub individual + romhack.ing p/ texturas), que já absorvem o
   risco de takedown há décadas. O emulador só consome manifests apontados pelo usuário.
4. **O emulador é burro em relação a conteúdo:** nenhum endosso, bundle ou default que
   aponte para material derivado.
5. Fatores de risco a policiar em qualquer hub associado: monetização, ROMs
   pré-patcheadas, assets originais empacotados, marcas no nome.

## 4. Padrões

Regra geral: **adotar padrão comunitário existente sempre que houver; formalizar como spec aberta apenas o que não existe** — para que outros emuladores e autores de packs possam implementar sem depender do MesenCE.

### 4.1 Padrões existentes adotados

| Área | Padrão | Aplicação | Benefício |
|---|---|---|---|
| Identificação de ROM | No-Intro (DATs Logiqx XML, CRC32/MD5/SHA-1) | Chave de packs e manifests (F3/F4) | Interop com RetroArch, coleções e bancos existentes |
| Hash por sistema | rcheevos `rhash` | Cálculo do hash quando o sistema hasheia só parte do arquivo | Compatibilidade futura com RetroAchievements |
| Log de áudio | VGM v1.71+ com tags GD3 | Exportador F1.1 | Toca em qualquer player VGM (foobar2000, in_vgm); metadados no padrão do vgmrips |
| Partitura/notas | SMF tipo 1 + General MIDI | Exportador F1.2 | Abre em MuseScore/DAWs sem conversão |
| Texturas | HDNes `hires.txt` (Mesen é a implementação de referência) | F2/F3 | Autores e ferramentas existentes já dominam o formato |
| Áudio SNES | MSU-1 (`.msu` + `.pcm`) | F3 (via `Msu1.cpp`, já suportado) | Uma década de packs do Zeldix funcionando no dia zero |
| Áudio NES | OGG via HD pack (`OggMixer`) | F3 | Já suportado; parte do padrão HDNes |
| Patches | BPS (beat) | Se packs incluírem patches de ROM | Valida checksum da ROM fonte — casa com o modelo keyed-por-hash |

Único vão sem padrão consolidado: áudio de replacement para **GB/SMS** (MSU-MD cobre só Mega Drive) — coberto pela extensão proposta em 4.2.3.

### 4.2 Novos padrões a formalizar (specs abertas)

Cada spec vive em `docs/specs/<sigla>-v<N>.md`, licenciada **CC0** (domínio público — qualquer emulador pode implementar), contendo: campos normativos em linguagem RFC 2119 (MUST/SHOULD/MAY), versionamento semver, arquivos-exemplo canônicos ("golden files") e script de validação. Mudanças via issue/PR no repositório da spec; breaking change = bump de versão maior.

**4.2.1 ESP — Enhanced Synth Preset (v1).** Formalização do atual `EnhancedAudioPresets.cfg`: gramática do arquivo, parâmetros de voz por chip (NES APU, GB APU, SMS PSG, YM2413), faixas válidas de cada parâmetro, comportamento default de campos omitidos e regras de fallback (por jogo → por chip → global). É o único formato 100% novo do ecossistema — não há equivalente no mercado.

**4.2.2 MEP — MesenCE Enhancement Pack (v1).** O envelope da Fase 3: um `.zip` com `pack.json` na raiz. Casca fina que só **compõe** padrões existentes: identificação por hash No-Intro, metadados (nome, autor, licença, versão semver) e seções opcionais apontando para formatos já padronizados — `textures/` (hires.txt), `audio/` (OGG/MSU-1), `synth/` (ESP). Cada seção declara-se individualmente desativável (toggle granular, F3.2).

**4.2.3 Extensão hires.txt para GB/SMS (proposta).** Extensão retrocompatível do formato HDNes usando o campo `<ver>` existente: novas tags para os PPUs de GB/SMS (paletas CGB, modos do VDP) e para replacement de áudio OGG nesses sistemas (o vão identificado em 4.1). A proposta deve ser discutida com a comunidade HDNes/Mesen antes de congelar a v1.

**4.2.4 MEI — MesenCE Enhancement Index (v1).** O manifest de descoberta da Fase 4: `manifest.json` com a lista de packs (nome, jogo, hash No-Intro, URL, checksum do artefato, licença). Índices são **federados**: qualquer um pode publicar um MEI e o usuário aponta o emulador para ele (F4.3) — o índice oficial é só mais um MEI.

## 5. Fases

Cada fase entrega valor sozinha e não depende da seguinte.

### Fase 1 — Exportador MIDI/VGM (Enhanced Synth tap)

*A peça mais barata e mais única do mercado.*

- **F1.1** Exportar VGM v1.71+ com tags GD3 (padrões da comunidade chiptune/vgmrips —
  ver 4.1): log bruto de escritas de registrador por chip. NES, GB, SMS (PSG + YM2413).
- **F1.2** Exportar MIDI (SMF tipo 1 + General MIDI — ver 4.1): reaproveitar as
  abstrações nota/voz do `EnhancedSynthEngine` (note-on/off, pitch, canal → track MIDI;
  mapear vozes do synth → programas GM aproximados a partir do preset ativo).
- **F1.3** UI: ação "Gravar música (MIDI/VGM)" no menu de áudio; grava enquanto joga.
- **Critério de sucesso:** MIDI de uma música do Mega Man 3 abre no MuseScore com
  pistas separadas por canal e notas corretas.

### Fase 2 — Generalizar o HD Pack Builder (GB / SMS)

- **F2.1** Portar o padrão `HdBuilderPpu` (gravação de tiles durante gameplay) para os
  PPUs de GB e SMS (ambos tile-based).
- **F2.2** Dump organizado: PNG folheados por bank/paleta + `hires.txt` compatível com
  o formato HDNes existente, estendido conforme a proposta 4.2.3 (retrocompatível via
  campo `<ver>`).
- **Critério de sucesso:** rodar um jogo de GB por 10 min gera um pack-esqueleto que,
  reinstalado, renderiza idêntico ao original (replacement 1:1 neutro).

### Fase 3 — Formato de pack unificado

- **F3.1** Implementar a spec **MEP v1** (4.2.2): `pack.json` com hash(es) No-Intro da
  ROM, versão, autor, licença, e seções opcionais `textures/` (hires.txt), `audio/`
  (OGG via OggMixer / MSU-1), `synth/` (preset ESP embutido).
- **F3.2** Toggles granulares: cada seção — e cada voz/camada dentro dela —
  individualmente desativável na UI (lição SUPER ZSNES: "to suit your play style").
- **F3.3** Carregamento por hash ao abrir a ROM; múltiplos packs com precedência.
- **Critério de sucesso:** um único .zip liga texturas + trilha OGG + preset de synth
  para um jogo, com cada peça desligável separadamente.

### Fase 4 — Browser de packs na UI + canal oficial

- **F4.1** Manifest remoto no formato **MEI v1** (4.2.4), hospedado em repo GitHub:
  lista de packs limpos (presets/mapeamentos/originais CC) com nome, jogo, hash
  No-Intro, URL, checksum e downloads.
- **F4.2** UI de descoberta: listar, instalar, atualizar; ranking por contagem de
  downloads/estrelas do GitHub (sem telemetria própria).
- **F4.3** URLs de manifest **configuráveis pelo usuário** (o default aponta só para o
  repo oficial limpo; a comunidade pode manter índices próprios em org separada).
- **F4.4** Contribuição = PR no repo do índice (curadoria via review).
- **Critério de sucesso:** instalar um preset de Enhanced Audio para After Burner em
  2 cliques a partir da UI, sem sair do emulador.

### Fase 5 — Pipeline offline de AI

*Ferramentas externas (scripts), nunca embutidas no emulador.*

- **F5.1** Upscale de tiles: batch ESRGAN (modelos treinados p/ pixel art) sobre o dump
  da Fase 2 → pack-rascunho 4x para refino manual da comunidade.
- **F5.2** Afinação assistida de presets: usar o template de ear-tuning
  (`docs/EnhancedAudioPresets.example.cfg`) como prompt — LLM recebe dump de
  registradores/VGM e propõe parâmetros de voz para revisão humana.
- **F5.3** (exploratório) Seleção/geração de samples de instrumento para vozes do synth.
- **Critério de sucesso:** do load do jogo ao pack-rascunho publicável em < 1h de
  trabalho humano.

## 6. Riscos e mitigações

| Risco | Prob. | Mitigação |
|---|---|---|
| Takedown do repo de índice | baixa | Índice contém só conteúdo limpo (princípio 2); derivados vivem em hubs externos |
| Projeto enquadrado como facilitador (padrão Yuzu) | baixa | Não-objetivos: sem P2P, sem hosting de derivados, sem monetização; emulador agnóstico a conteúdo |
| Formato SUPER ZSNES tentar virar alvo de compat. | — | Decidido: **não perseguir** — formato fechado, em fluxo, acoplado ao renderer deles |
| Escopo explodir (virar "segundo produto") | alta | Fases independentes; F4 usa GitHub como backend, sem servidor próprio |
| Comunidade pequena (fork pessoal) | média | Cada fase é útil solo p/ o autor; F1 (MIDI export) tem apelo além do fork |
| Specs novas não serem adotadas por terceiros | média | Specs em CC0, federadas e finas (MEP/MEI só compõem padrões existentes); ESP é útil mesmo só no MesenCE |

## 7. Referências

- SUPER ZSNES — https://www.zsnes.com/ (modelo de curadoria e claim legal dos dados)
- Zeldix (hub MSU-1) — https://www.zeldix.net/
- VGMusic (MIDIs desde 1996) — https://www.vgmusic.com/
- romhack.ing / RetroGameTalk (sucessores do RHDN); acervo RHDN no Internet Archive
- Formato VGM + tags GD3 — https://vgmrips.net/ · Formato HD Pack (hires.txt) — docs do Mesen
- No-Intro (DATs Logiqx XML) — https://no-intro.org/ · rcheevos `rhash` — https://github.com/RetroAchievements/rcheevos
- Formato de patch BPS — spec do beat (byuu/Near) · MSU-1 — spec do bsnes
- Precedentes: *MGM v. Grokster* (2005); acordo Yuzu/Nintendo (2024)
