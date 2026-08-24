#pragma once
#include "pch.h"
#include "Shared/Audio/EnhancedSynthPreset.h"

//Built-in instrument presets. Order must match the EnhancedAudioPreset enum
//on the UI side (Synthwave = 0, ChipDeluxe = 1, OrchestralLite = 2, Dry = 3,
//Studio = 4). Values start as a copy of the NES engine's tuning
//(Core/NES/EnhancedSynth.cpp) - the SN76489's plain 50%-duty square/noise
//character differs enough from the 2A03 that these will likely need ear
//tuning once heard in-game; until then they're a reasonable starting point
//since the DSP itself is shared (EnhancedSynthEngine).
//
//Split out of SmsEnhancedSynth.cpp (which only ever includes this header
//once) to keep that file under the project's 200-line-per-file guardrail;
//"static constexpr" still gives this array internal linkage per translation
//unit, so there is no ODR risk even though it lives in a header.
static constexpr EnhancedSynthPreset _presets[5] = {
	//Synthwave: detuned pulse-width leads, saw+sub bass, tight drums
	{
		0.004, 0.002, false, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.16,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Chip deluxe: stays close to the PSG character - pure-ish pulses,
	//round bass, crisp drums, just a touch of space
	{
		0.0015, 0.001, false, 0.5, false, 0.10, 8000, 6000, 1.1,
		0.9, 0.1, 0.2, 1200, 1.0,
		1800, 7500, 7000, 1.0, 0.35, 0.045, 165,
		2, 3,
		0.12, 0.25, 0.35, 0.08,
		1.0, 0.6, 0.8, 0.85,
		0, 0, 0, 0, 0
	},
	//Orchestral lite: slow-attack string-like leads, low string bass,
	//timpani-weight drums, larger room
	{
		0.007, 0.005, false, 0.5, false, 0.35, 3800, 2600, 1.0,
		0.5, 0.6, 0.25, 700, 1.2,
		900, 4500, 6000, 1.0, 0.7, 0.12, 110,
		35, 80,
		0.30, 0.30, 0.45, 0.30,
		0.95, 0.65, 0.9, 0.6,
		0, 0, 0, 0, 0
	},
	//Dry: Synthwave voices with no echo/reverb tail - SFX stay tight
	{
		0.004, 0.002, false, 0.5, false, 0.25, 5200, 3200, 1.4,
		0.65, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		3, 4,
		0.05, 0.0, 0.0, 0.0,
		1.0, 0.56, 0.85, 0.75,
		0, 0, 0, 0, 0
	},
	//Studio: fixed detuned-saw stack lead (the SN76489 has no duty register to
	//ignore, but the always-saw lead still gives it a fuller, less "chip"
	//character), same tuned pan/bass/drum balance as Synthwave, plus a gentle
	//bus compressor.
	{
		0.003, 0.002, false, 0.5, true, 0.25, 5200, 3200, 1.4,
		0.70, 0.45, 0.35, 900, 1.3,
		1400, 6800, 6500, 1.2, 0.5, 0.06, 165,
		4, 4,
		0.24, 0.45, 0.65, 0.18,
		1.0, 0.56, 0.85, 0.75,
		0.55, 3.0, 8, 140, 1.18
	},
};
