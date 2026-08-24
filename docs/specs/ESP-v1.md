# ESP v1 — Enhanced Synth Preset

**Status:** v1 (estável) ·
**Licença desta spec:** CC0-1.0 (domínio público) ·
**Versionamento:** semver — campo novo = minor; mudança de semântica ou remoção = major ·
**Golden file:** [`golden/esp/EnhancedAudioPresets.cfg`](golden/esp/EnhancedAudioPresets.cfg) ·
**Validação:** `scripts/validate-specs.py`

As palavras-chave MUST, MUST NOT, SHOULD, SHOULD NOT e MAY seguem a
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

## 1. Escopo

ESP descreve o formato do arquivo de *presets* do Enhanced Audio: os
parâmetros de voz que um sintetizador paralelo usa para reinterpretar, em
tempo real, o estado dos chips de som clássicos (NES APU/2A03, Game Boy APU,
SN76489 do SMS/GG/SG-1000/ColecoVision e o bus melódico do YM2413). A
implementação de referência é o MesenCE (`Core/Shared/Audio/
EnhancedSynthPreset.*`), mas qualquer emulador MAY implementar o formato.

O arquivo NÃO contém dados derivados de nenhuma ROM — apenas parâmetros de
síntese — e portanto é sempre distribuível.

## 2. Modelo de dados

Uma implementação expõe **5 presets nomeados**, cada um existindo por
**engine** (chip/família). O arquivo ESP contém *overrides parciais* aplicados
sobre os defaults embutidos da implementação.

- Nomes de preset (MUST, sensíveis a maiúsculas): `Synthwave`, `ChipDeluxe`,
  `OrchestralLite`, `Dry`, `Studio`.
- Sufixos de engine (MUST): vazio = NES APU, `.Gb` = Game Boy APU,
  `.Sms` = família SMS (SN76489 + YM2413).
- Implementações que suportem outros chips MAY definir novos sufixos; um
  sufixo desconhecido MUST ser ignorado pelo parser (compatibilidade futura).

## 3. Gramática

Arquivo de texto orientado a linhas, codificação ASCII/UTF-8.

```
arquivo   := linha*
linha     := em-branco | comentário | seção | campo
comentário:= ('#' | ';') qualquer-texto
seção     := '[' NomePreset SufixoEngine ']'
campo     := Nome '=' Valor
```

Regras normativas:

1. Espaços em branco nas pontas de cada linha MUST ser aparados antes do parse.
2. Linhas em branco e comentários MUST ser ignorados.
3. Um `campo` só tem efeito dentro de uma `seção` reconhecida; campos antes da
   primeira seção MUST ser ignorados.
4. Nome de seção e de campo são **sensíveis a maiúsculas** (MUST).
5. Campo desconhecido, linha malformada ou valor não numérico (para campos
   numéricos) MUST ser ignorado silenciosamente — o arquivo nunca é rejeitado
   por inteiro.
6. Campo omitido MUST manter o default embutido do preset/engine
   (override parcial). Regra de fallback v1: **campo → default embutido do
   par (preset, engine)**. Fallback por jogo (hash) fica reservado para uma
   versão futura (ver §6).
7. Booleanos aceitam `true`/`false` (MUST).

## 4. Campos

Todos os campos numéricos são ponto-flutuante decimais (`0.25`, `5200`).

### 4.1 Vozes de pulso (lead / harmonia)

| Campo | Tipo | Unidade / semântica |
|---|---|---|
| `LeadDetune` | double | razão de detune entre os 2 osciladores do lead (0.003 = ±0,3%) |
| `HarmDetune` | double | idem, voz de harmonia |
| `FollowDuty` | bool | true: largura de pulso segue o registrador de duty do jogo (sem efeito em chips sem duty) |
| `FixedWidth` | double | largura de pulso 0..1 usada quando `FollowDuty=false` |
| `LeadAlwaysSaw` | bool | true: lead vira pilha de serras detunadas; duty ignorado |
| `LeadOctaveUpMix` | double | mistura 0..1 de uma cópia +1 oitava no lead |
| `LeadLpHz` | double | corte do low-pass do lead, Hz |
| `HarmLpHz` | double | corte do low-pass da harmonia, Hz |
| `LeadDrive` | double | ganho de saturação do lead (1 = neutro) |

### 4.2 Baixo (canal triângulo / tone 2)

| Campo | Tipo | Semântica |
|---|---|---|
| `BassSine` | double | nível do componente senoidal |
| `BassSaw` | double | nível do componente serra |
| `BassSub` | double | nível do sub-oscilador (−1 oitava) |
| `BassLpHz` | double | corte do low-pass do baixo, Hz |
| `BassDrive` | double | saturação do baixo (1 = neutro) |

### 4.3 Bateria (canal de ruído)

| Campo | Tipo | Semântica |
|---|---|---|
| `DrumBodyLoHz` | double | banda inferior do corpo, Hz |
| `DrumBodyHiHz` | double | banda superior do corpo, Hz |
| `DrumTopHz` | double | high-pass do "top" (chimbal), Hz |
| `DrumBodyGain` | double | nível do corpo |
| `ThumpGain` | double | nível do bumbo sintético disparado por ataque grave |
| `ThumpDecayS` | double | decay do bumbo, segundos |
| `ThumpFreqHz` | double | frequência do bumbo, Hz |

### 4.4 Envelope, FX e mix

| Campo | Tipo | Semântica |
|---|---|---|
| `AttackMs` / `ReleaseMs` | double | constantes de suavização de volume, ms |
| `EchoDelayS` | double | delay do eco do lead, segundos |
| `EchoGainL` / `EchoGainR` | double | nível do eco por lado (imagem estéreo) |
| `ReverbWet` | double | nível do reverb feedforward de 3 taps |
| `LeadGain` / `HarmGain` / `BassGain` / `DrumGain` | double | níveis das vozes no mix |

### 4.5 Compressor do bus master

| Campo | Tipo | Semântica |
|---|---|---|
| `CompThreshold` | double | nível onde a compressão começa; **0 desliga o compressor** |
| `CompRatio` | double | razão de compressão; valores < 1 MUST ser tratados como 1 |
| `CompAttackMs` / `CompReleaseMs` | double | constantes do detector, ms |
| `CompMakeup` | double | ganho de compensação na saída |

## 5. Semântica de recarga

Implementações SHOULD reler o arquivo em reset de console / troca de ROM e
MUST NOT fazer I/O de arquivo no caminho de mixagem de áudio.

## 6. Reservado para versões futuras (não normativo em v1)

- Seções por jogo, propostas como `[<NomePreset><SufixoEngine>@<SHA1>]`
  (fallback jogo → engine → default). Parsers v1 já as ignoram naturalmente
  pela regra §3.5.
- Sufixos de engine adicionais (ex.: `.Pce`, `.Snes`).

## 7. Golden file

[`golden/esp/EnhancedAudioPresets.cfg`](golden/esp/EnhancedAudioPresets.cfg)
é o exemplo canônico: contém todas as seções de engine, todos os campos v1 com
valores dentro das faixas usuais, comentários e um campo desconhecido
deliberado (que parsers conformes ignoram). `scripts/validate-specs.py` o
valida contra a gramática e a lista de campos desta spec.
