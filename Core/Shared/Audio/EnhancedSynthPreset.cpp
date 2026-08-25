#include "pch.h"
#include "Shared/Audio/EnhancedSynthPreset.h"
#include "Utilities/FolderUtilities.h"
#include "Shared/MessageManager.h"

//Field names accepted in EnhancedAudioPresets.cfg, mapped to the struct
//members they override. Keeping this table next to the struct means adding a
//new preset field only ever requires editing this one file (shared by every
//engine that uses EnhancedSynthPreset).
namespace
{
	struct PresetDoubleField
	{
		const char* Name;
		double EnhancedSynthPreset::* Field;
	};
	struct PresetBoolField
	{
		const char* Name;
		bool EnhancedSynthPreset::* Field;
	};

	static constexpr PresetDoubleField _presetDoubleFields[] = {
		{ "LeadDetune", &EnhancedSynthPreset::LeadDetune },
		{ "HarmDetune", &EnhancedSynthPreset::HarmDetune },
		{ "FixedWidth", &EnhancedSynthPreset::FixedWidth },
		{ "LeadOctaveUpMix", &EnhancedSynthPreset::LeadOctaveUpMix },
		{ "LeadLpHz", &EnhancedSynthPreset::LeadLpHz },
		{ "HarmLpHz", &EnhancedSynthPreset::HarmLpHz },
		{ "LeadDrive", &EnhancedSynthPreset::LeadDrive },
		{ "BassSine", &EnhancedSynthPreset::BassSine },
		{ "BassSaw", &EnhancedSynthPreset::BassSaw },
		{ "BassSub", &EnhancedSynthPreset::BassSub },
		{ "BassLpHz", &EnhancedSynthPreset::BassLpHz },
		{ "BassDrive", &EnhancedSynthPreset::BassDrive },
		{ "DrumBodyLoHz", &EnhancedSynthPreset::DrumBodyLoHz },
		{ "DrumBodyHiHz", &EnhancedSynthPreset::DrumBodyHiHz },
		{ "DrumTopHz", &EnhancedSynthPreset::DrumTopHz },
		{ "DrumBodyGain", &EnhancedSynthPreset::DrumBodyGain },
		{ "ThumpGain", &EnhancedSynthPreset::ThumpGain },
		{ "ThumpDecayS", &EnhancedSynthPreset::ThumpDecayS },
		{ "ThumpFreqHz", &EnhancedSynthPreset::ThumpFreqHz },
		{ "AttackMs", &EnhancedSynthPreset::AttackMs },
		{ "ReleaseMs", &EnhancedSynthPreset::ReleaseMs },
		{ "EchoDelayS", &EnhancedSynthPreset::EchoDelayS },
		{ "EchoGainL", &EnhancedSynthPreset::EchoGainL },
		{ "EchoGainR", &EnhancedSynthPreset::EchoGainR },
		{ "ReverbWet", &EnhancedSynthPreset::ReverbWet },
		{ "LeadGain", &EnhancedSynthPreset::LeadGain },
		{ "HarmGain", &EnhancedSynthPreset::HarmGain },
		{ "BassGain", &EnhancedSynthPreset::BassGain },
		{ "DrumGain", &EnhancedSynthPreset::DrumGain },
		{ "CompThreshold", &EnhancedSynthPreset::CompThreshold },
		{ "CompRatio", &EnhancedSynthPreset::CompRatio },
		{ "CompAttackMs", &EnhancedSynthPreset::CompAttackMs },
		{ "CompReleaseMs", &EnhancedSynthPreset::CompReleaseMs },
		{ "CompMakeup", &EnhancedSynthPreset::CompMakeup },
	};
	static constexpr PresetBoolField _presetBoolFields[] = {
		{ "FollowDuty", &EnhancedSynthPreset::FollowDuty },
		{ "LeadAlwaysSaw", &EnhancedSynthPreset::LeadAlwaysSaw },
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
void EnhancedSynthPresetLoader::Load(EnhancedSynthPreset outPresets[5], const EnhancedSynthPreset defaults[5], const char* sectionSuffix, const string& packPresetPath)
{
	std::copy(defaults, defaults + 5, outPresets);

	string suffix = sectionSuffix ? sectionSuffix : "";
	if(!packPresetPath.empty()) {
		//MEP synth section: above the built-ins, below the user's file
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

		bool applied = false;
		for(const PresetDoubleField& f : _presetDoubleFields) {
			if(key == f.Name) {
				try {
					outPresets[presetIndex].*(f.Field) = std::stod(value);
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
