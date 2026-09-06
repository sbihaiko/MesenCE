#include "pch.h"
#include "Shared/Audio/EnhancedSynthPreset.h"
#include "Utilities/FolderUtilities.h"
#include "Shared/MessageManager.h"
#include <algorithm>
#include <cmath>

//Field names accepted in EnhancedAudioPresets.cfg, mapped to the struct
//members they override. Keeping this table next to the struct means adding a
//new preset field only ever requires editing this one file (shared by every
//engine that uses EnhancedSynthPreset).
namespace
{
	//Min/Max bound what a preset file may set: a non-finite or out-of-range
	//value would otherwise reach the DSP as an infinite filter coefficient, a
	//negative delay or a 10^6 gain. The ranges are the widest the consumer
	//still handles sanely (see EnhancedSynthEngine::Render), not taste.
	struct PresetDoubleField
	{
		const char* Name;
		double EnhancedSynthPreset::* Field;
		double Min;
		double Max;
	};
	struct PresetBoolField
	{
		const char* Name;
		bool EnhancedSynthPreset::* Field;
	};

	static constexpr PresetDoubleField _presetDoubleFields[] = {
		{ "LeadDetune", &EnhancedSynthPreset::LeadDetune, 0.0, 0.5 },
		{ "HarmDetune", &EnhancedSynthPreset::HarmDetune, 0.0, 0.5 },
		{ "FixedWidth", &EnhancedSynthPreset::FixedWidth, 0.01, 0.99 },
		{ "LeadOctaveUpMix", &EnhancedSynthPreset::LeadOctaveUpMix, 0.0, 1.0 },
		{ "LeadLpHz", &EnhancedSynthPreset::LeadLpHz, 20.0, 22000.0 },
		{ "HarmLpHz", &EnhancedSynthPreset::HarmLpHz, 20.0, 22000.0 },
		{ "LeadDrive", &EnhancedSynthPreset::LeadDrive, 0.0, 10.0 },
		{ "BassSine", &EnhancedSynthPreset::BassSine, 0.0, 4.0 },
		{ "BassSaw", &EnhancedSynthPreset::BassSaw, 0.0, 4.0 },
		{ "BassSub", &EnhancedSynthPreset::BassSub, 0.0, 4.0 },
		{ "BassLpHz", &EnhancedSynthPreset::BassLpHz, 20.0, 22000.0 },
		{ "BassDrive", &EnhancedSynthPreset::BassDrive, 0.0, 10.0 },
		{ "DrumBodyLoHz", &EnhancedSynthPreset::DrumBodyLoHz, 20.0, 22000.0 },
		{ "DrumBodyHiHz", &EnhancedSynthPreset::DrumBodyHiHz, 20.0, 22000.0 },
		{ "DrumTopHz", &EnhancedSynthPreset::DrumTopHz, 20.0, 22000.0 },
		{ "DrumBodyGain", &EnhancedSynthPreset::DrumBodyGain, 0.0, 4.0 },
		{ "ThumpGain", &EnhancedSynthPreset::ThumpGain, 0.0, 4.0 },
		{ "ThumpDecayS", &EnhancedSynthPreset::ThumpDecayS, 0.001, 5.0 },
		{ "ThumpFreqHz", &EnhancedSynthPreset::ThumpFreqHz, 20.0, 2000.0 },
		{ "AttackMs", &EnhancedSynthPreset::AttackMs, 0.0, 5000.0 },
		{ "ReleaseMs", &EnhancedSynthPreset::ReleaseMs, 0.0, 5000.0 },
		{ "EchoDelayS", &EnhancedSynthPreset::EchoDelayS, 0.001, 2.0 },
		{ "EchoGainL", &EnhancedSynthPreset::EchoGainL, 0.0, 1.0 },
		{ "EchoGainR", &EnhancedSynthPreset::EchoGainR, 0.0, 1.0 },
		{ "ReverbWet", &EnhancedSynthPreset::ReverbWet, 0.0, 1.0 },
		{ "LeadGain", &EnhancedSynthPreset::LeadGain, 0.0, 4.0 },
		{ "HarmGain", &EnhancedSynthPreset::HarmGain, 0.0, 4.0 },
		{ "BassGain", &EnhancedSynthPreset::BassGain, 0.0, 4.0 },
		{ "DrumGain", &EnhancedSynthPreset::DrumGain, 0.0, 4.0 },
		{ "CompThreshold", &EnhancedSynthPreset::CompThreshold, 0.0, 4.0 },
		{ "CompRatio", &EnhancedSynthPreset::CompRatio, 1.0, 100.0 },
		{ "CompAttackMs", &EnhancedSynthPreset::CompAttackMs, 0.01, 5000.0 },
		{ "CompReleaseMs", &EnhancedSynthPreset::CompReleaseMs, 0.01, 5000.0 },
		{ "CompMakeup", &EnhancedSynthPreset::CompMakeup, 0.0, 8.0 },
		{ "GmLeadProgram", &EnhancedSynthPreset::GmLeadProgram, 0.0, 127.0 },
		{ "GmHarmProgram", &EnhancedSynthPreset::GmHarmProgram, 0.0, 127.0 },
		{ "GmBassProgram", &EnhancedSynthPreset::GmBassProgram, 0.0, 127.0 },
	};
	static constexpr PresetBoolField _presetBoolFields[] = {
		{ "FollowDuty", &EnhancedSynthPreset::FollowDuty },
		{ "LeadAlwaysSaw", &EnhancedSynthPreset::LeadAlwaysSaw },
		{ "GmDrums", &EnhancedSynthPreset::GmDrums },
	};
	static constexpr const char* _presetNames[5] = { "Synthwave", "ChipDeluxe", "OrchestralLite", "Dry", "Studio" };

	static void Trim(string& s)
	{
		size_t start = s.find_first_not_of(" \t\r\n");
		if(start == string::npos) {
			s.clear();
			return;
		}
		size_t end = s.find_last_not_of(" \t\r\n");
		s = s.substr(start, end - start + 1);
	}

	//F5.4g Bloco B item 6 (ADR-0052): parse one "FixedRole.<ch>=<value>" line
	//into outPresets[presetIndex].FixedRole[ch]. ch is a physical channel
	//0..3; value is -1 (auto) / 0..2 (Lead/Harmony/Bass) or their names.
	//Returns true when the key was a FixedRole line (even if malformed, which
	//is skipped silently like the other fields).
	bool ApplyFixedRole(const string& key, const string& value, EnhancedSynthPreset* outPresets, int presetIndex)
	{
		if(key.rfind("FixedRole.", 0) != 0) {
			return false;
		}
		if(presetIndex >= 0 && outPresets) {
			string chStr = key.substr(strlen("FixedRole."));
			int channel = -1;
			try {
				channel = std::stoi(chStr);
			} catch(const std::exception&) {
				return true; //malformed channel - skipped
			}
			if(channel >= 0 && channel < 4) {
				int role = -2;
				if(value == "auto" || value == "Auto") {
					role = -1;
				} else if(value == "lead" || value == "Lead") {
					role = 0;
				} else if(value == "harm" || value == "harmony" || value == "Harmony") {
					role = 1;
				} else if(value == "bass" || value == "Bass") {
					role = 2;
				} else {
					try {
						role = std::stoi(value);
					} catch(const std::exception&) {
						return true; //malformed value - skipped
					}
				}
				if(role >= -1 && role <= 2) {
					outPresets[presetIndex].FixedRole[channel] = role;
				}
			}
		}
		return true;
	}
}

//Optional per-field overrides, with no rebuild, for the built-in presets.
//Re-read on console reset / ROM load (never from the audio mix path - this
//does file I/O), so editing the file only needs a reset, not a restart.
//Create "EnhancedAudioPresets.cfg" in the Mesen home folder (same folder as
//the settings file) with one section per preset and "Field=value" lines,
//e.g.:
//   [Studio]
//   CompThreshold=0.6
//   LeadAlwaysSaw=false
//Section names are "<PresetName><sectionSuffix>" (see the header for why),
//e.g. the SMS engine reads "[Studio.Sms]" instead of "[Studio]" from the same
//file. Only the fields listed are overridden; anything else keeps its
//built-in default. Section/field names are case-sensitive and must match the
//names in EnhancedSynthPreset (see _presetDoubleFields/_presetBoolFields
//above and _presetNames for the section names). Blank lines and lines
//starting with '#' or ';' are ignored. Malformed lines/values are skipped
//silently.
void EnhancedSynthPresetLoader::Load(EnhancedSynthPreset outPresets[5], const EnhancedSynthPreset defaults[5], const char* sectionSuffix, const vector<string>& packPresetPaths)
{
	std::copy(defaults, defaults + 5, outPresets);

	string suffix = sectionSuffix ? sectionSuffix : "";
	for(const string& packPresetPath : packPresetPaths) {
		//MEP synth section: above the built-ins, below the user's file; the
		//pack's auto/ layer comes first so the human layer overrides it
		if(std::ifstream(packPresetPath)) {
			ApplyFile(packPresetPath, outPresets, suffix);
			MessageManager::Log("[MEP] synth: applied ESP overrides from '" + packPresetPath + "' (sections '<Preset>" + suffix + "')");
		} else {
			MessageManager::Log("[MEP] synth section file not found: " + packPresetPath);
		}
	}
	ApplyFile(FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), "EnhancedAudioPresets.cfg"), outPresets, suffix);
}

void EnhancedSynthPresetLoader::ApplyFile(const string& path, EnhancedSynthPreset outPresets[5], const string& suffix)
{
	std::ifstream file(path);
	if(!file) {
		return;
	}

	int presetIndex = -1;
	string line;
	while(std::getline(file, line)) {
		Trim(line);
		if(line.empty() || line[0] == '#' || line[0] == ';') {
			continue;
		}

		if(line.front() == '[' && line.back() == ']') {
			string name = line.substr(1, line.size() - 2);
			presetIndex = -1;
			for(int i = 0; i < 5; i++) {
				if(name == string(_presetNames[i]) + suffix) {
					presetIndex = i;
					break;
				}
			}
			continue;
		}

		if(presetIndex < 0) {
			continue;
		}

		size_t eq = line.find('=');
		if(eq == string::npos) {
			continue;
		}
		string key = line.substr(0, eq);
		string value = line.substr(eq + 1);
		Trim(key);
		Trim(value);

		//F5.4g Bloco B item 6 (ADR-0052): "FixedRole.<ch>=<value>" is handled
		//first - its key is dotted (not a plain field name) and its value is an
		//int/enum, not a double/bool.
		if(ApplyFixedRole(key, value, outPresets, presetIndex)) {
			continue;
		}

		bool applied = false;
		for(const PresetDoubleField& f : _presetDoubleFields) {
			if(key == f.Name) {
				try {
					double parsed = std::stod(value);
					//NaN/inf are skipped (the field keeps its value); a finite
					//value is clamped to the field's [Min, Max]
					if(std::isfinite(parsed)) {
						outPresets[presetIndex].*(f.Field) = std::clamp(parsed, f.Min, f.Max);
					}
				} catch(const std::exception&) {
					//malformed number - keep the current value
				}
				applied = true;
				break;
			}
		}
		if(!applied) {
			for(const PresetBoolField& f : _presetBoolFields) {
				if(key == f.Name) {
					outPresets[presetIndex].*(f.Field) = (value == "1" || value == "true" || value == "True");
					break;
				}
			}
		}
	}
}
