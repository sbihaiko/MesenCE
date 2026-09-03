# ADR-0149: Enhancement pack border layer (border/overlay frame) format and Core rendering architecture

- Status: accepted
- Date: 2026-09-02
- Related: MEP-v1 (§3.1, §5), PRD Part A §4 (Phase 8), PRD Part B §6.1 (Enhancements quick-toggle panel), ADR-0005 (MEP envelope), ADR-0040 (storage/precedence), ADR-0050 (auto screen backgrounds).
- Supersedes / amends: MEP-v1 §3.1 & §5 (adds optional `border` section and layout specification in v1.5).

## Context

Many retro gaming communities and contemporary emulators/enhancement projects (such as Super Game Boy, SGB borders, RetroArch overlay bezels, and custom artwork packs) provide decorative framing, bezels, or arcade cabinet art around the 4:3 or original aspect-ratio game viewport.

In MesenCE, Phase 7 established the "faithful, then enhanced, on by default" thesis and introduced the Player Shell with an "Enhancements" quick-toggle panel (Part B §6.1). The roadmap specifies Phase 8 as the Enhancement pack border layer:
1. A declarative asset format for packs to supply a decorative border frame.
2. A clean Core compositing and rendering pipeline that does not distort or degrade core game rendering or HUD overlays.
3. An explicit configuration gate (`EnhancementPackConfig.EnableBorder`) toggleable both in the Player Shell quick-toggle panel and in Advanced preferences.

Non-goals:
- Automatic heuristic generation of borders (borders are authored pack assets, not engine-generated).
- Emulation of Super Game Boy SNES core hardware (SGB SNES core was removed on 2026-08-26 per repo policy; only game borders as static/semi-static overlay assets are supported).
- Distorting the game view: game aspect ratio is preserved within the designated viewport.

## Decision

### 1. MEP Specification Extension: `border` Section (MEP v1.5)

MEP-v1 is amended to v1.5 to introduce an optional root section under `sections`:
```json
{
  "mep": "1.5.0",
  "name": "Super Mario Bros. Deluxe Bezel",
  "version": "1.0.0",
  "id": "smb-deluxe-bezel",
  "targets": [
    { "system": "nes", "sha1": "3337A01683DE92F05103E994B6982F2494E80D21" }
  ],
  "sections": {
    "textures": { "path": "textures/" },
    "border": { "path": "border/" }
  }
}
```

#### Border Section Structure
Under the directory pointed to by `sections.border.path` (or `<Game>/border/` or `<Game>/mep/border/` in folder convention):
- `border.png`: The primary 32-bit RGBA image representing the border frame.
- `border.json` (optional): Viewport layout and configuration. When omitted, default layout heuristics apply (16:9 canvas with centered original aspect ratio viewport).

#### `border.json` Specification
```json
{
  "version": 1,
  "width": 1920,
  "height": 1080,
  "viewport": {
    "x": 240,
    "y": 0,
    "width": 1440,
    "height": 1080
  },
  "scale_mode": "fit",
  "underlay": false
}
```

Fields:
- `width`, `height` (MUST, integer > 0): Intended design resolution of `border.png` (typically 1920x1080 or 16:9 / 16:10 target).
- `viewport` (MUST, object): Target rectangle where the game frame is positioned within `width` × `height`:
  - `x`, `y`, `width`, `height` (integers >= 0).
- `scale_mode` (optional, default `"fit"`):
  - `"fit"`: Scales the composite canvas to fill the window while preserving canvas aspect ratio (adding neutral outer letterboxing if needed).
  - `"stretch"`: Stretches the border canvas to the output surface.
- `underlay` (optional, boolean, default `false`):
  - `false` (default): The border is composited as an overlay on top of the game frame, allowing ornate bezel edges with alpha transparency to softly overlap the game border.
  - `true`: The border is composited behind the game frame (game drawn strictly over viewport).

#### Convention Layout Probing
`MepPack::DetectConventionLayout` is extended to probe:
- `border/border.png` (human layer) and `auto/border/border.png` (if generated).
- Like other sections, human layer in `mep/` or root takes precedence.

### 2. Core Rendering and Compositing Architecture

#### Rendering Pipeline Integration
The border compositing path is integrated cleanly into `VideoRenderer` and `BaseVideoFilter`:
1. **Separation of Concerns:**
   - Emulation video decoding, PPU rendering, and filters (`BaseVideoFilter`, `ScaleFilter`, `ScanlineFilter`) continue to output the raw emulated frame at native or upscaled game resolution.
   - The game aspect ratio calculation (`EmuSettings::GetAspectRatio`) remains faithful.
2. **Compositing in VideoRenderer:**
   - In `VideoRenderer::RenderThread`, when `EnhancementPackConfig.EnableBorder` is active and the active MEP pack provides a valid border:
     - The game frame is rendered into the destination viewport defined by `border.json`.
     - The `border.png` surface is blended with standard source-over alpha blending onto the output frame.
     - HUD layers (`SystemHud`, `DebugHud`, `ScriptHud`) are rendered on top of the final composited frame or mapped to the game viewport depending on HUD settings.
3. **Thread Safety & Asset Caching:**
   - Border image decoding is performed once at pack load time (`MepPackManager` / `BorderManager`) and cached as a 32-bit ARGB surface (`RenderSurfaceInfo` or raw buffer).
   - If `border.png` fails to decode or has invalid dimensions, the border is gracefully skipped without interrupting gameplay.

### 3. Configuration & UI Exposure

1. **`EnhancementPackConfig` (Core C++ & UI C#):**
   - New field: `bool EnableBorder = true;`
   - Added to `Core/Shared/SettingTypes.h` and `UI/Config/EnhancementPackConfig.cs` (struct `InteropEnhancementPackConfig` kept in exact ABI lockstep).
2. **Player Shell Quick-Toggle Panel (Part B §6.1):**
   - The 7th toggle "Border" is added to `PlayerEnhancementsPanel` in `MainWindow.axaml` and `MainWindowViewModel.cs`.
   - Directly toggles `EnhancementPackConfig.EnableBorder`.
   - Disabled/grayed out when the active game/pack does not provide a border.
3. **Advanced Mode:**
   - Checkbox "Enable pack border" added to `EnhancementPacksWindow`.

### 4. Validation and Tooling (`scripts/`)

1. **`scripts/mep_lint.py`:**
   - Added validation for `sections.border`:
     - Verifies `path` exists and contains `border.png`.
     - Validates PNG header, resolution, and optional `border.json` schema.
     - Warns if `viewport` exceeds canvas bounds or has negative coordinates.
2. **`scripts/validate-specs.py`:**
   - Updated `validate_mep` to recognize `"border"` as a valid known section name alongside `"textures"`, `"audio"`, `"synth"`.

## Consequences

- Authors can ship high-fidelity borders/bezels without needing complex emulator-specific overlay hacks.
- `EnableBorder` allows players to toggle borders off instantly if they prefer pure black bars or stretch modes.
- ABI safety: `InteropEnhancementPackConfig` is updated symmetrically in C++ and C#.
- Zero performance impact when no border is present or when `EnableBorder == false`.
