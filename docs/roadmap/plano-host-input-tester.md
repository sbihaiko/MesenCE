# Plano — tester de input host

**Status:** rascunho (2026-08-26) ·
**PRD:** fora (UX de host; não é pack/enhancement) ·
**Referência:** [hardwaretester.com/gamepad](https://hardwaretester.com/gamepad) ·
**Fora de spec:** diagnóstico do gamepad no host, não formato de pack.
**Processo:** contrato do interop vive neste plano até divergir do código. Sem ADR obrigatório.

Os cores restantes (NES, GB/GBC/GBS, SMS/GG/SG-1000, GBA) são digitais. Analog no Mesen é D-pad, tilt/acelerômetro e rumble — não FPS. Copiar o Hardware Tester **por inteiro** é fora de escopo. Copiar o que fecha o diagnóstico do host.

Pad físico com layout SNES (USB, 8BitDo, BlueRetro no **host**) é um gamepad como qualquer outro nesta aba. O tipo de console `SnesController` (protocolo de 12 botões na porta do NES) é outra camada — ver `plano-reducao-cores.md`. O tester não precisa de emulação SNES.

## Critério de sucesso

Um usuário com pad USB/Bluetooth conectado, **sem ROM carregada**, abre Settings → Input → aba Test e vê:

- quais dispositivos o Mesen enxerga (nome, backend, slot `PadN` / `JoyN`);
- cada botão e eixo ao vivo, com o **mesmo nome de keycode** usado no mapping (`Pad1 A`, `Pad1 LT Up`);
- o anel da deadzone atual sobre os sticks, e aviso se o stick parado não está em (0,0);
- um botão que dispara rumble naquele pad.

A janela de mapping (`ControllerConfigWindow`) acende o botão do **console** cujo keycode está pressionado. Drift, deadzone errada e “o Mesen não vê meu pad” deixam de exigir o site externo.

O HUD in-game (`InputHud`) continua sendo a verdade do **console**. Este plano não o substitui.

## Três camadas (não misturar)

| Camada | Onde | O que mostra | Hoje |
|---|---|---|---|
| 1. Host | XInput / DInput / evdev / GameController | Pad físico, eixos crus, rumble | Só logs `[Input Connected]` |
| 2. Binarização | `IsPressed` + `ControllerDeadzoneSize` | `Pad1 X+` etc. depois da deadzone | Invisível na UI |
| 3. Console | `KeyMapping` → NES/GB/SMS/GBA | A/B/Start do sistema | HUD in-game + janela de mapping cega |

O Hardware Tester é a camada 1. O Mesen só expõe a 3. O tester deste plano é a 1 + a 2 (keycode Mesen), lado a lado.

## Estado do terreno (verificado no código em 2026-08-26)

| Ponto | Situação |
|---|---|
| Mapping UI | `ControllerConfigWindow` + `KeyBindingButton` + modal `GetKeyWindow` (poll 25 ms, single-key pega o maior scancode) |
| HUD console | `Core/Shared/InputHud.cpp` — botões digitais do dispositivo emulado, overlay opcional por porta |
| Deadzone | Slider global 0–4 (`InputConfig.ControllerDeadzoneSize` → `GetControllerDeadzoneRatio()`), aplicada no host ao binarizar |
| Analog cru | `IKeyManager::GetAxisPosition` existe; uso só em `GbMbc7Accelerometer` e `GbaTiltSensor` (ambos `TODO add configuration in UI`) |
| Pressed keys → UI | `InputApi.GetPressedKeys()` copia **no máximo 3** keycodes (`InputApiWrapper.cpp` + buffer de 3 em `InputApi.cs`) |
| Identidade do pad | Nome/vendor só em `MessageManager::Log`; bindings por **slot** (`Pad1`…), não por VID/PID |
| Rumble | `SetForceFeedback` no host; intensidade global; só no pad que já mandou input (`_enableForceFeedback`) |
| Hotplug Linux | `LinuxKeyManager::UpdateDevices()` é TODO; scan a cada 5 s |
| macOS | Pad sem `extendedGamepad` é ignorado |
| Presets | Xbox / PS4 / WASD / setas no setup wizard e na janela de mapping — permanece |

## O que não copiar

- Coleta de stats da indústria.
- Gamepad API do browser — backends nativos já existem.
- Tester como substituto do mapping.
- Precisão analógica de fighting game / circularidade como entrega do primeiro corte.
- Giroscópio, adaptive triggers DualSense.

## Fases

### I.0 — Contrato de host na UI (bloqueia o resto)

Não dá para montar o tester em cima de `GetPressedKeys` de 3 slots. Expor estado **antes** da binarização, sem mudar o modelo de mapping.

**Entrega:** a UI consulta a lista de pads e o estado live sem truncar.

Interop novo (nomes provisórios — ajustar ao estilo de `InputApi`):

- `GetConnectedGamepadCount()` / `GetConnectedGamepadInfo(index, out InteropGamepadInfo)`
  - `Name`, `Backend` (`XInput` / `DirectInput` / `Evdev` / `GameController`), `SlotLabel` (`Pad1` / `Joy2`), `VendorId`, `ProductId`, `HasRumble`
- `GetGamepadState(index, out InteropGamepadState)`
  - botões digitais (pressed + keycode + `GetKeyName`)
  - eixos `int16` **crus** (sticks LX/LY/RX/RY, triggers L2/R2), sem deadzone
- `TestForceFeedback(index, durationMs)` — ignora `_enableForceFeedback` para o teste

Arquivos: `IKeyManager` (+ impls `Windows` / `Linux` / `MacOS`), `InteropDLL/InputApiWrapper.cpp`, `UI/Interop/InputApi.cs`.

Não quebrar `GetPressedKeys` (Lua, `GetKeyWindow`, `ShortcutKeyHandler`, `StateGrid`). Estender ou adicionar API paralela.

Eixos crus **não** passam pela deadzone. A UI desenha o anel usando o slider atual.

### I.1 — Aba Test na config de Input

**Entrega:** Settings → Input ganha aba **Test** (ao lado de General / Display). Sem ROM. Sem modal.

Por pad conectado:

- identidade (nome, backend, slot Mesen, VID/PID se houver);
- silhueta genérica / Xbox com botões acendendo;
- dois círculos de stick + ponto ao vivo + anel da deadzone (`ControllerDeadzoneSize`);
- barras L2/R2;
- lista dos keycodes Mesen ativos (`Pad1 A`, `Pad1 X+`);
- aviso se stick parado fora de ~0 (drift);
- botão Test rumble.

ViewModel novo: dados via `Refresh(...)` injetado pelo code-behind / timer — construtor **não** chama `InputApi` (contrato Fase 3 de `UI/AGENTS.md`). Não extrair para `UI/Logic/` (depende de interop nativo). Timer ~16–33 ms só com a aba visível.

Poll: `InputApi.UpdateInputDevices()` no open da aba.

### I.2 — Highlight live na janela de mapping

**Entrega:** com `ControllerConfigWindow` aberta, o `KeyBindingButton` cujo `KeyBinding` está em `GetPressedKeys` (ou na nova API) acende. Continua sendo preciso clicar para rebind.

Não substitui o `GetKeyWindow`. Complementa: o usuário vê *qual* botão do console o pad está acionando **antes** de rebindar.

### I.3 — Follow-ups (fora do primeiro corte)

Ordem sugerida, cada um isolável:

1. Deadzone per-device (o preview da I.1 já justifica o slider global).
2. Binding por VID/PID em vez de slot `Pad1` (hotplug deixa de quebrar mapping).
3. UI dos eixos MBC7 / GBA tilt (os dois TODOs).
4. Teste de circularidade (stick que nunca sai da deadzone).
5. Linux: `UpdateDevices()` de verdade. macOS: não descartar pad sem `extendedGamepad`.

## Fora deste plano

- Redesign dos presets Xbox/PS4/WASD.
- Overlay HUD in-game (camada 3).
- Dispositivos especiais (Zapper, Power Pad, Phaser, tablet) — o tester é de **gamepad host**.
- Remap automático a partir do tester.

## Verificação

Planos não têm check automático (`docs/AGENTS.md`). Fechar cada fase com:

| Fase | Check |
|---|---|
| I.0 | Build Core+Interop+UI nas três plataformas alvo; Lua `emu.getPressedKeys` e atalho de teclado inalterados; `GetGamepadState` devolve eixos com o stick no canto (não só 0/1) |
| I.1 | Manual: 0 pads → empty state; 1 pad Xbox/generic → botões, sticks, deadzone, rumble; 2 pads → dois painéis; slider de deadzone move o anel ao vivo |
| I.2 | Manual: mapping NES/GB/GBA/SMS — apertar o pad acende o botão do console já bound; rebind pelo modal continua funcionando |
| Drift | Stick com drift visível no tester em repouso; se dentro da deadzone, HUD in-game **não** acende D-pad |

Não há ROM de teste para I.0–I.2. I.3 tilt/MBC7 usa ROM com sensor quando essa fase entrar.
