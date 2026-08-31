#include "pch.h"
#include "NES/NesConsole.h"
#include "NES/NesControlManager.h"
#include "NES/MapperFactory.h"
#include "NES/APU/NesApu.h"
#include "NES/NesCpu.h"
#include "NES/BaseMapper.h"
#include "NES/NesSoundMixer.h"
#include "NES/EnhancedSynth.h"
#include "NES/NesMemoryManager.h"
#include "NES/DefaultNesPpu.h"
#include "NES/NsfPpu.h"
#include "NES/HdPacks/HdAudioDevice.h"
#include "NES/HdPacks/HdData.h"
#include "NES/HdPacks/HdNesPpu.h"
#include "NES/HdPacks/HdPackLoader.h"
#include "NES/HdPacks/HdPackBuilder.h"
#include "NES/HdPacks/HdBuilderPpu.h"
#include "NES/HdPacks/HdVideoFilter.h"
#include "Shared/EnhancementPacks/MepPackManager.h"
#include "NES/HdPacks/NesAudioFingerprint.h"
#include "Shared/MessageManager.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/ProcessUtilities.h"
#include <cstdlib>
#include <filesystem>
#include "NES/NesDefaultVideoFilter.h"
#include "NES/NesNtscFilter.h"
#include "NES/BisqwitNtscFilter.h"
#include "NES/NesConstants.h"
#include "NES/Epsm.h"
#include "NES/Mappers/VsSystem/VsControlManager.h"
#include "NES/Mappers/NSF/NsfMapper.h"
#include "NES/Mappers/FDS/Fds.h"
#include "Shared/Emulator.h"
#include "Shared/Audio/SoundMixer.h"
#include "Shared/SaveStateManager.h"
#include "Shared/CheatManager.h"
#include "Shared/Movies/MovieManager.h"
#include "Shared/BaseControlManager.h"
#include "Shared/EmuSettings.h"
#include "Shared/NotificationManager.h"
#include "Netplay/GameClient.h"
#include "Debugger/DebugTypes.h"
#include "Utilities/Serializer.h"
#include "Utilities/sha1.h"

NesConsole::NesConsole(Emulator* emu)
{
	_emu = emu;
	_sharedSoundMixer = emu->GetSoundMixer();
}

NesConsole::~NesConsole()
{
	shared_ptr<HdPackData> hdData = _hdData.lock();
	if(hdData) {
		hdData->CancelLoad();
	}
}

Emulator* NesConsole::GetEmulator()
{
	return _emu;
}

NesConfig& NesConsole::GetNesConfig()
{
	return _emu->GetSettings()->GetNesConfig();
}

void NesConsole::ProcessCpuClock()
{
	if(_mapper->HasCpuClockHook()) {
		_mapper->ProcessCpuClock();
	}

	_apu->ProcessCpuClock();
	if(_controlManager->HasPendingWrites()) {
		_controlManager->ProcessWrites();
	}
}

uint8_t NesConsole::GetOpenBus()
{
	return _memoryManager->GetOpenBus();
}

Epsm* NesConsole::GetEpsm()
{
	return _mapper->GetEpsm();
}

NesConsole* NesConsole::GetVsMainConsole()
{
	return _vsMainConsole;
}

NesConsole* NesConsole::GetVsSubConsole()
{
	return _vsSubConsole.get();
}

bool NesConsole::IsVsMainConsole()
{
	return _vsMainConsole == nullptr;
}

void NesConsole::Serialize(Serializer& s)
{
	SV(_cpu);
	SV(_ppu);
	SV(_memoryManager);
	SV(_apu);
	SV(_mapper);

	if(s.GetFormat() != SerializeFormat::Map) {
		SV(_mixer);
	}

	if(_hdAudioDevice) {
		//For HD packs), save the state of the bgm playback
		SV(_hdAudioDevice);
	}

	if(_vsSubConsole) {
		//For VS Dualsystem, the sub console's savestate is appended to the end of the file
		SV(_vsSubConsole);
	}

	SV(_controlManager);

	if(!s.IsSaving()) {
		UpdateRegion(true);
		//Note: the enhanced synth is deliberately NOT reset here. Run-ahead
		//loads a state every frame, so resetting on deserialization would
		//wipe the synth's envelopes/delay lines 60 times per second. Letting
		//transient audio state (echo tail, phases) survive a state load is
		//harmless - it fades naturally within ~250ms.
	}
}

optional<SaveStateCompatInfo> NesConsole::ValidateSaveStateCompatibility(Serializer& s, ConsoleType stateConsoleType)
{
	if(_vsSubConsole && !s.ContainsPrefix("vsSubConsole")) {
		//Only allow loading VS DualSystem save states when a VS DualSystem game is loaded
		return SaveStateCompatInfo { false };
	}

	return {};
}

void NesConsole::Reset()
{
	_memoryManager->Reset(true);

	_ppu->Reset(true);
	_apu->Reset(true);
	_cpu->Reset(true, _region);
	_controlManager->Reset(true);
	_mixer->Reset();
	if(_enhancedSynth) {
		_enhancedSynth->Reset();
	}
	if(_vsSubConsole) {
		_vsSubConsole->Reset();
	}
	_mapper->OnAfterResetPowerOn();
	if(_mapper->GetEpsm()) {
		_mapper->GetEpsm()->Reset();
	}
}

LoadRomResult NesConsole::LoadRom(VirtualFile& romFile)
{
	RomData romData;

	LoadHdPack(romFile);

	LoadRomResult result = LoadRomResult::UnknownType;
	unique_ptr<BaseMapper> mapper = MapperFactory::InitializeFromFile(this, romFile, romData, result);
	if(mapper) {
		if(!_vsMainConsole && romData.Info.VsType == VsSystemType::VsDualSystem) {
			//Create 2nd console (sub) dualsystem games
			_vsSubConsole.reset(new NesConsole(_emu));
			_vsSubConsole->_vsMainConsole = this;
			_emu->SetDebuggerDisabled(true);
			result = _vsSubConsole->LoadRom(romFile);
			_emu->SetDebuggerDisabled(false);
			if(result != LoadRomResult::Success) {
				return result;
			}
		}

		if(GetNesConfig().AutoConfigureInput && romData.Info.InputType != GameInputType::Unspecified) {
			//Auto-configure the inputs (if option is enabled)
			InitializeInputDevices(romData.Info.InputType, romData.Info.System);
		}

		_mapper.swap(mapper);
		_mixer.reset(new NesSoundMixer(this));
		if(IsVsMainConsole()) {
			//Main console only: on VS DualSystem the sub console registering a
			//second synth would just double the enhanced audio output (same
			//rule as the GB link-cable secondary console - see Gameboy::PowerOn)
			_enhancedSynth.reset(new EnhancedSynth(_emu, this));
		}
		_memoryManager.reset(new NesMemoryManager(this, _mapper.get()));
		_cpu.reset(new NesCpu(this));
		_apu.reset(new NesApu(this));

		if(romData.Info.System == GameSystem::VsSystem) {
			_controlManager.reset(new VsControlManager(this));
		} else {
			_controlManager.reset(new NesControlManager(this));
		}

		if(_hdData && _hdData->HasVideoContent()) {
			_ppu.reset(new HdNesPpu(this, _hdData.get()));
		} else if(dynamic_cast<NsfMapper*>(_mapper.get())) {
			//Disable most of the PPU for NSFs
			_ppu.reset(new NsfPpu(this));
		} else {
			_ppu.reset(new DefaultNesPpu(this));
		}

		_mapper->InitSpecificMapper(romData);

		if(_mapper->GetEpsm()) {
			_memoryManager->RegisterIODevice(_mapper->GetEpsm());
		}
		_memoryManager->RegisterIODevice(_ppu.get());
		_memoryManager->RegisterIODevice(_apu.get());
		_memoryManager->RegisterIODevice(_controlManager.get());
		_memoryManager->RegisterIODevice(_mapper.get());

		if(_hdData) {
			_hdAudioDevice.reset(new HdAudioDevice(_emu, _hdData.get()));
			_memoryManager->RegisterIODevice(_hdAudioDevice.get());
		} else {
			_hdAudioDevice.reset();
			_audioReplacer.reset();
		}
		_audioBootstrap.reset();

		UpdateRegion();

		_mixer->Reset();

		_ppu->Reset(false);
		_apu->Reset(false);
		_memoryManager->Reset(false);
		_controlManager->Reset(false);
		_cpu->Reset(false, _region);
		_mapper->OnAfterResetPowerOn();
	}
	return result;
}

void NesConsole::LoadHdPack(VirtualFile& romFile)
{
	_hdData.reset();
	if(!GetNesConfig().EnableHdPacks) {
		return;
	}

	MepPackManager* mep = _emu->GetEnhancementPackManager();
	string mepTextures = mep->GetSectionPath(MepSectionType::Textures);
	string autoTextures = mep->GetSectionAutoPath(MepSectionType::Textures);
	string mepAudio = mep->GetSectionPath(MepSectionType::Audio);
	string autoAudio = mep->GetSectionAutoPath(MepSectionType::Audio);
	bool anyMepTextures = !mepTextures.empty() || !autoTextures.empty();

	_hdData.reset(new HdPackData());
	bool loaded = false;
	unique_ptr<HdPackData> looseAudioOnly;

	//1) Loose HdPacks/<rom>/ pack (MEP-v1 §5.1) - unless the ROM's sibling
	//folder provides *human-authored* textures, which comes first (ADR-0049).
	//An auto-only sibling (the F5 bootstrap's generic output, written before
	//any pack was installed) is only a base layer: it must not shadow a real
	//loose pack installed later (issue #142). An audio-only hires.txt (0 tiles,
	//LiQuiDz-style <bgm> pack) is not a texture pack: keep its tracks/patches
	//and still load auto/sibling tiles, otherwise HdVideoFilter runs on
	//DefaultNesPpu output and the screen goes black.
	bool siblingHasHumanTextures = mep->IsSectionFromSibling(MepSectionType::Textures) && !mepTextures.empty();
	if(siblingHasHumanTextures) {
		if(HdPackLoader::HasLoosePack(romFile)) {
			MessageManager::Log("[MEP] sibling folder beside the ROM overrides the loose HdPacks/ pack");
		}
	} else {
		unique_ptr<HdPackData> loose(new HdPackData());
		if(HdPackLoader::LoadHdNesPack(romFile, *loose)) {
			if(loose->HasVideoContent()) {
				_hdData.reset(loose.release());
				loaded = true;
				MessageManager::Log("[MEP] textures: loaded loose NES HD pack from HdPacks/" + FolderUtilities::GetFilename(romFile.GetFileName(), false) + "/hires.txt (" + std::to_string(_hdData->Tiles.size()) + " tiles, scale " + std::to_string(_hdData->Scale) + ")");
				if(anyMepTextures) {
					MessageManager::Log("[MEP] loose HD pack found for this ROM - it takes precedence over the pack's textures section");
				}
			} else {
				MessageManager::Log("[MEP] loose HdPacks pack is audio-only (" + std::to_string(loose->BgmFilesById.size()) + " BGM / " + std::to_string(loose->SfxFilesById.size()) + " SFX) - not used as textures");
				looseAudioOnly = std::move(loose);
			}
		}
	}

	//2) MEP textures section: human layer, then auto/ layer underneath
	if(!loaded && anyMepTextures) {
		if(!mepTextures.empty()) {
			loaded = HdPackLoader::LoadHdNesPack(FolderUtilities::CombinePath(mepTextures, "hires.txt"), *_hdData.get());
			MessageManager::Log(loaded ? "[MEP] textures: loaded NES HD pack from '" + mepTextures + "'" : "[MEP] textures section has no loadable hires.txt in " + mepTextures);
		}
		if(!autoTextures.empty()) {
			unique_ptr<HdPackData> autoData(new HdPackData());
			if(HdPackLoader::LoadHdNesPack(FolderUtilities::CombinePath(autoTextures, "hires.txt"), *autoData)) {
				if(loaded) {
					//auto/ screens would cover the artist's tiles: only the tiles merge under a human layer
					if(!autoData->BackgroundFileData.empty()) {
						MessageManager::Log("[MEP] textures: auto layer has " + std::to_string(autoData->BackgroundFileData.size()) + " captured screen(s) - not used under the human layer (copy the <background> lines you want into textures/hires.txt)");
					}
					HdPackLoader::MergeLowerLayer(*_hdData.get(), *autoData, false);
				} else {
					_hdData.reset(autoData.release());
					loaded = true;
				}
				MessageManager::Log("[MEP] textures: auto layer loaded from '" + autoTextures + "'");
			} else {
				MessageManager::Log("[MEP] textures auto layer has no loadable hires.txt in " + autoTextures);
			}
		}
	}

	//3) MEP audio section: NES OGG via a hires.txt with <bgm>/<sfx> tags
	//(ADR-0041). auto/ first, then the human layer, each overriding the
	//tracks already present (human > auto > textures pack).
	auto mergeAudio = [&](const string& folder, const char* label) {
		unique_ptr<HdPackData> audioData(new HdPackData());
		if(!ifstream(FolderUtilities::CombinePath(folder, "hires.txt"))) {
			//Fingerprint-only layer (F5.3) - handled in step 4, nothing to say here
			return;
		}
		if(!HdPackLoader::LoadHdNesPack(FolderUtilities::CombinePath(folder, "hires.txt"), *audioData)) {
			MessageManager::Log(string("[MEP] ") + label + " has no loadable hires.txt in " + folder);
			return;
		}
		if(loaded) {
			for(auto& bgm : audioData->BgmFilesById) {
				_hdData->BgmFilesById[bgm.first] = bgm.second;
			}
			for(auto& sfx : audioData->SfxFilesById) {
				_hdData->SfxFilesById[sfx.first] = sfx.second;
			}
		} else {
			_hdData.reset(audioData.release());
			loaded = true;
		}
		MessageManager::Log(string("[MEP] ") + label + ": " + std::to_string(_hdData->BgmFilesById.size()) + " BGM / " + std::to_string(_hdData->SfxFilesById.size()) + " SFX tracks after '" + folder + "'");
	};
	if(looseAudioOnly) {
		if(loaded) {
			for(auto& bgm : looseAudioOnly->BgmFilesById) {
				_hdData->BgmFilesById[bgm.first] = bgm.second;
			}
			for(auto& sfx : looseAudioOnly->SfxFilesById) {
				_hdData->SfxFilesById[sfx.first] = sfx.second;
			}
			for(auto& patch : looseAudioOnly->PatchesByHash) {
				_hdData->PatchesByHash.emplace(patch.first, patch.second);
			}
		} else {
			_hdData.reset(looseAudioOnly.release());
			loaded = true;
		}
	}

	if(!autoAudio.empty()) {
		mergeAudio(autoAudio, "audio auto layer");
	}
	if(!mepAudio.empty()) {
		mergeAudio(mepAudio, "audio");
	}

	//4) Fingerprint-triggered OGG (ADR-0047): auto/ layer first, human last
	_audioReplacer.reset();
	{
		vector<string> layers;
		if(!autoAudio.empty()) {
			layers.push_back(autoAudio);
		}
		if(!mepAudio.empty()) {
			layers.push_back(mepAudio);
		}
		bool anyFingerprints = false;
		for(const string& layer : layers) {
			if(ifstream(FolderUtilities::CombinePath(layer, "fingerprints.json"))) {
				anyFingerprints = true;
			}
		}
		bool humanFingerprints = !mepAudio.empty() && ifstream(FolderUtilities::CombinePath(mepAudio, "fingerprints.json")).good();
		if(anyFingerprints && !humanFingerprints && loaded && !_hdData->BgmFilesById.empty()) {
			//The artist's pack already replaces music the HDNes way (<bgm> + patched $41xx writes):
			//the machine-generated fingerprints would play a second OGG on top of it
			MessageManager::Log("[MEP] audio: pack already ships <bgm> tracks - auto/ fingerprints not used (add audio/fingerprints.json to opt in)");
			anyFingerprints = false;
		}
		if(anyFingerprints) {
			if(!loaded) {
				_hdData.reset(new HdPackData());
				loaded = true;
			}
			unique_ptr<NesAudioReplacer> replacer(new NesAudioReplacer(this));
			if(replacer->Load(layers, *_hdData.get()) > 0) {
				_audioReplacer = std::move(replacer);
			} else {
				MessageManager::Log("[MEP] audio: fingerprints present but no bgm/<id>.ogg to play - run scripts/mep_render_audio.py on the pack folder");
			}
		}
	}

	if(!loaded) {
		_hdData.reset();
		return;
	}

	//<patch> lines are keyed by the whole-file sha1 of the ROM they were made
	//for; ADR-0044 adds an explicit override for other revisions
	EnhancementPackConfig& mepCfg = _emu->GetSettings()->GetEnhancementPackConfig();
	//A pack that ships <bgm> uses its patch to route the game's music to those
	//OGG files, stripping it out of the PRG. Applying it with the audio layer
	//off would leave the game with no music at all and nothing for the
	//enhanced synth to re-interpret, so the audio layer being off also turns
	//this patch off - the player asked to hear the game, not silence.
	bool patchServesPackAudio = !_hdData->BgmFilesById.empty() && !mepCfg.EnableAudio;
	if(!_hdData->PatchesByHash.empty() && !mepCfg.EnablePatches) {
		MessageManager::Log("[HDPack] <patch> skipped: 'ROM patch' layer disabled in Tools > Enhancement Packs");
	} else if(!_hdData->PatchesByHash.empty() && patchServesPackAudio) {
		MessageManager::DisplayMessage("HDPack", "ROM patch skipped: it replaces the game's music with the pack's OGG tracks, which are turned off - the game's own music plays instead");
		MessageManager::Log("[HDPack] <patch> skipped: the pack's <bgm> patch would mute the game while 'Audio (OGG)' is off (turn the audio layer on to use the pack's music)");
	} else if(!_hdData->PatchesByHash.empty()) {
		//HDNes <patch> lines are keyed by a 40-hex ROM sha1. Community packs
		//typically store the No-Intro PRG+CHR hash (ADR-0044); VirtualFile::
		//GetSha1Hash is the whole file including the 16-byte iNES header.
		//Try both so a pack written for either convention still applies.
		string wholeFileSha1 = romFile.GetSha1Hash();
		string noIntroSha1 = MepPackManager::ComputeNoIntroSha1(romFile);
		auto result = _hdData->PatchesByHash.find(wholeFileSha1);
		if(result == _hdData->PatchesByHash.end() && noIntroSha1 != wholeFileSha1) {
			result = _hdData->PatchesByHash.find(noIntroSha1);
		}
		if(result != _hdData->PatchesByHash.end()) {
			VirtualFile patchFile = result->second;
			romFile.ApplyPatch(patchFile);
			MessageManager::Log("[HDPack] <patch> applied: '" + result->second + "' (ROM sha1 " + result->first + "; the running ROM's hash is now the patched one)");
			WarnAboutSilentPatchedMusic();
		} else if(mepCfg.ApplyPatchOnHashMismatch) {
			VirtualFile patchFile = _hdData->PatchesByHash.begin()->second;
			romFile.ApplyPatch(patchFile);
			MessageManager::DisplayMessage("HDPack", "Applying patch made for another ROM revision (hash override enabled)");
			WarnAboutSilentPatchedMusic();
			MessageManager::Log("[HDPack] <patch> hash mismatch - applied '" + _hdData->PatchesByHash.begin()->second + "' anyway (ApplyPatchOnHashMismatch)");
		} else {
			MessageManager::Log("[HDPack] <patch> skipped: no entry for this ROM's sha1 " + wholeFileSha1 +
				(noIntroSha1 != wholeFileSha1 ? (" / no-intro " + noIntroSha1) : "") +
				" (enable 'apply patches on hash mismatch' to force it)");
		}
	}

	shared_ptr<HdPackData> data = _hdData.lock();
	if(data) {
		thread asyncLoadData([data]() {
			data->LoadAsync();
		});
		asyncLoadData.detach();
	}
}

void NesConsole::WarnAboutSilentPatchedMusic()
{
	//An HDNes <patch> typically strips the game's music out of the PRG and
	//makes it ask the pack for an OGG instead. With the pack's audio layer
	//off that leaves the game with no music at all and nothing for the
	//enhanced synth to re-interpret - say so instead of just going quiet.
	if(_hdData->BgmFilesById.empty() || _emu->GetSettings()->GetEnhancementPackConfig().EnableAudio) {
		return;
	}
	MessageManager::DisplayMessage("HDPack", "The ROM patch removed the game's music (the pack plays it as OGG) - turn 'Audio (OGG)' on, or turn 'ROM patch' off to hear the original music");
	MessageManager::Log("[HDPack] <patch> applied with the pack's 'Audio (OGG)' layer off: the patched ROM has no music of its own");
}

void NesConsole::StartAudioBootstrap(const string& audioFolder)
{
	_audioBootstrap.reset(new NesAudioBootstrap(audioFolder));
}

void NesConsole::UpdateRegion(bool forceUpdate)
{
	ConsoleRegion region = GetNesConfig().Region;
	if(region == ConsoleRegion::Auto) {
		switch(_mapper->GetRomInfo().System) {
			case GameSystem::NesPal: region = ConsoleRegion::Pal; break;
			case GameSystem::Dendy: region = ConsoleRegion::Dendy; break;
			default: region = ConsoleRegion::Ntsc; break;
		}
	}

	if(_vsSubConsole) {
		_vsSubConsole->UpdateRegion(forceUpdate);
	}

	if(_region != region || forceUpdate) {
		_region = region;

		_cpu->SetMasterClockDivider(_region);
		_mapper->SetRegion(_region);
		_ppu->UpdateTimings(_region);
		_apu->SetRegion(_region);
		_mixer->SetRegion(_region);
	}
}
void NesConsole::RunFrame()
{
	if(_vsSubConsole) {
		InternalRunFrame<true>();
	} else {
		InternalRunFrame<false>();
	}
}

template<bool isDualSystem>
void NesConsole::InternalRunFrame()
{
	UpdateRegion();

	uint32_t frame = _ppu->GetFrameCount();

	if(_nextFrameOverclockDisabled) {
		//Disable overclocking for the next frame
		//This is used by the DMC when a sample is playing
		_ppu->UpdateTimings(_region, false);
		_nextFrameOverclockDisabled = false;
	}

	while(frame == _ppu->GetFrameCount()) {
		_cpu->Exec();
		if constexpr(isDualSystem) {
			RunVsSubConsole();
		}
	}

	_mapper->EndFrame();
	_apu->EndFrame();

	if(_hdPackBuilder) {
		_hdPackBuilder->OnFrameEnd();
	}

	if(_hdAudioDevice) {
		_hdAudioDevice->ProcessFrame();
	}

	if(_audioReplacer || _audioBootstrap) {
		ApuState apu = _apu->GetState();
		if(_audioReplacer) {
			_audioReplacer->OnFrame(apu);
		}
		if(_audioBootstrap) {
			_audioBootstrap->OnFrame(apu);
		}
	}

	if(!_nextFrameOverclockDisabled) {
		//Re-update timings to allow overclocking
		_ppu->UpdateTimings(_region, true);
	}
}

void NesConsole::RunVsSubConsole()
{
	_emu->SetDebuggerDisabled(true);
	int64_t cycleGap;
	while(true) {
		//Run the sub console until it catches up to the main CPU
		cycleGap = (int64_t)(_cpu->GetCycleCount() - _vsSubConsole->_cpu->GetCycleCount());
		if(cycleGap > 5 || _ppu->GetFrameCount() > _vsSubConsole->_ppu->GetFrameCount()) {
			_vsSubConsole->_cpu->Exec();
		} else {
			break;
		}
	}
	_emu->SetDebuggerDisabled(false);
}

void NesConsole::SetNextFrameOverclockStatus(bool disabled)
{
	//Disable overclocking for the next frame
	//This is used by the DMC when a sample is playing
	_nextFrameOverclockDisabled = disabled;
}

BaseControlManager* NesConsole::GetControlManager()
{
	return _controlManager.get();
}

double NesConsole::GetFps()
{
	UpdateRegion();
	if(_region == ConsoleRegion::Ntsc) {
		return 60.0988118623484;
	} else {
		return 50.0069789081886;
	}
}

uint32_t NesConsole::GetFrameCount()
{
	return _ppu->GetFrameCount();
}

PpuFrameInfo NesConsole::GetPpuFrame()
{
	PpuFrameInfo frame;
	frame.FrameBuffer = (uint8_t*)_ppu->GetScreenBuffer(false);
	frame.Width = NesConstants::ScreenWidth;
	frame.Height = NesConstants::ScreenHeight;
	frame.FrameBufferSize = frame.Width * frame.Height * sizeof(uint16_t);
	frame.FrameCount = _ppu->GetFrameCount();
	frame.FirstScanline = -1;
	frame.ScanlineCount = _ppu->GetScanlineCount();
	frame.CycleCount = 341;
	return frame;
}

ConsoleType NesConsole::GetConsoleType()
{
	return ConsoleType::Nes;
}

ConsoleRegion NesConsole::GetRegion()
{
	return _region;
}

vector<CpuType> NesConsole::GetCpuTypes()
{
	return { CpuType::Nes };
}

AddressInfo NesConsole::GetAbsoluteAddress(AddressInfo& relAddress)
{
	if(relAddress.Type == MemoryType::NesMemory) {
		return _mapper->GetAbsoluteAddress(relAddress.Address);
	} else {
		return _mapper->GetPpuAbsoluteAddress(relAddress.Address);
	}
}

AddressInfo NesConsole::GetRelativeAddress(AddressInfo& absAddress, CpuType cpuType)
{
	return _mapper->GetRelativeAddress(absAddress);
}

void NesConsole::GetConsoleState(BaseState& baseState, ConsoleType consoleType)
{
	NesState& state = (NesState&)baseState;

	state.ClockRate = GetMasterClockRate();
	state.Cpu = _cpu->GetState();
	_ppu->GetState(state.Ppu);
	state.Cartridge = _mapper->GetState();
	state.Apu = _apu->GetState();
}

uint64_t NesConsole::GetMasterClock()
{
	return _cpu->GetCycleCount();
}

uint32_t NesConsole::GetMasterClockRate()
{
	return NesConstants::GetClockRate(_region);
}

void NesConsole::SaveBattery()
{
	if(_mapper) {
		_mapper->SaveBattery();
	}
}

ShortcutState NesConsole::IsShortcutAllowed(EmulatorShortcut shortcut, uint32_t shortcutParam)
{
	bool isRunning = _emu->IsRunning();
	bool isNetplayClient = _emu->GetGameClient()->Connected();
	bool isMoviePlaying = _emu->GetMovieManager()->Playing();
	RomFormat romFormat = GetRomFormat();

	switch(shortcut) {
		case EmulatorShortcut::FdsEjectDisk:
		case EmulatorShortcut::FdsInsertNextDisk:
		case EmulatorShortcut::FdsSwitchDiskSide:
			return (ShortcutState)(isRunning && !isNetplayClient && !isMoviePlaying && romFormat == RomFormat::Fds);

		case EmulatorShortcut::FdsInsertDiskNumber:
			if(isRunning && !isNetplayClient && !isMoviePlaying && romFormat == RomFormat::Fds) {
				Fds* fds = dynamic_cast<Fds*>(_mapper.get());
				return (ShortcutState)(fds && shortcutParam < fds->GetSideCount());
			}
			return ShortcutState::Disabled;

		case EmulatorShortcut::VsInsertCoin1:
		case EmulatorShortcut::VsInsertCoin2:
		case EmulatorShortcut::VsServiceButton:
			return (ShortcutState)(isRunning && !isNetplayClient && !isMoviePlaying && (romFormat == RomFormat::VsSystem || romFormat == RomFormat::VsDualSystem));

		case EmulatorShortcut::VsInsertCoin3:
		case EmulatorShortcut::VsInsertCoin4:
		case EmulatorShortcut::VsServiceButton2:
			return (ShortcutState)(isRunning && !isNetplayClient && !isMoviePlaying && romFormat == RomFormat::VsDualSystem);
	}

	return ShortcutState::Default;
}

BaseVideoFilter* NesConsole::GetVideoFilter(bool getDefaultFilter)
{
	if(getDefaultFilter || GetRomFormat() == RomFormat::Nsf) {
		return new NesDefaultVideoFilter(_emu);
	} else if(_hdData && _hdData->HasVideoContent() && !_hdPackBuilder) {
		return new HdVideoFilter(this, _emu, _hdData.get());
	} else {
		VideoFilterType filterType = _emu->GetSettings()->GetVideoConfig().VideoFilter;

		switch(filterType) {
			case VideoFilterType::NtscBlargg: return new NesNtscFilter(_emu);
			case VideoFilterType::NtscBisqwit: return new BisqwitNtscFilter(_emu);
			default: return new NesDefaultVideoFilter(_emu);
		}
	}
}

string NesConsole::GetHash(HashType hashType)
{
	if(hashType == HashType::Sha1Cheat) {
		ConsoleMemoryInfo prgRom = _emu->GetMemory(MemoryType::NesPrgRom);
		if(prgRom.Size && prgRom.Memory) {
			return SHA1::GetHash((uint8_t*)prgRom.Memory, prgRom.Size);
		}
	}

	return "";
}

RomFormat NesConsole::GetRomFormat()
{
	return _mapper->GetRomInfo().Format;
}

AudioTrackInfo NesConsole::GetAudioTrackInfo()
{
	NsfMapper* nsfMapper = dynamic_cast<NsfMapper*>(_mapper.get());
	if(nsfMapper) {
		return nsfMapper->GetAudioTrackInfo();
	}
	return {};
}

void NesConsole::ProcessAudioPlayerAction(AudioPlayerActionParams p)
{
	NsfMapper* nsfMapper = dynamic_cast<NsfMapper*>(_mapper.get());
	if(nsfMapper) {
		return nsfMapper->ProcessAudioPlayerAction(p);
	}
}

uint8_t NesConsole::DebugRead(uint16_t addr)
{
	return _memoryManager->DebugRead(addr);
}

void NesConsole::DebugWrite(uint16_t addr, uint8_t value, bool disableSideEffects)
{
	_memoryManager->DebugWrite(addr, value, disableSideEffects);
}

uint8_t NesConsole::DebugReadVram(uint16_t addr)
{
	if(addr >= 0x3F00) {
		return _ppu->ReadPaletteRam(addr);
	} else {
		return _mapper->DebugReadVram(addr);
	}
}

void NesConsole::DebugWriteVram(uint16_t addr, uint8_t value)
{
	if(addr >= 0x3F00) {
		_ppu->WritePaletteRam(addr, value);
	} else {
		_mapper->DebugWriteVram(addr, value);
	}
}

void NesConsole::InitializeInputDevices(GameInputType inputType, GameSystem system)
{
	ControllerType port1 = ControllerType::NesController;
	ControllerType port2 = ControllerType::NesController;
	ControllerType expDevice = ControllerType::None;

	auto log = [](string text) {
		MessageManager::Log(text);
	};

	bool isFamicom = (system == GameSystem::Famicom || system == GameSystem::FDS || system == GameSystem::Dendy);

	if(inputType == GameInputType::VsZapper) {
		//VS Duck Hunt, etc. need the zapper in the first port
		log("[Input] VS Zapper connected");
		port1 = ControllerType::NesZapper;
	} else if(inputType == GameInputType::Zapper) {
		log("[Input] Zapper connected");
		if(isFamicom) {
			expDevice = ControllerType::FamicomZapper;
		} else {
			port2 = ControllerType::NesZapper;
		}
	} else if(inputType == GameInputType::FourScore) {
		log("[Input] Four score connected");
		port1 = ControllerType::FourScore;
		port2 = ControllerType::FourScore;
	} else if(inputType == GameInputType::FourPlayerAdapter) {
		log("[Input] Four player adapter connected");
		expDevice = ControllerType::TwoPlayerAdapter;
	} else if(inputType == GameInputType::ArkanoidControllerFamicom || inputType == GameInputType::DoubleArkanoidController) {
		log("[Input] Arkanoid controller (Famicom) connected");
		expDevice = ControllerType::FamicomArkanoidController;
	} else if(inputType == GameInputType::ArkanoidControllerNes) {
		log("[Input] Arkanoid controller (NES) connected");
		port2 = ControllerType::NesArkanoidController;
	} else if(inputType == GameInputType::OekaKidsTablet) {
		log("[Input] Oeka Kids Tablet connected");
		expDevice = ControllerType::OekaKidsTablet;
	} else if(inputType == GameInputType::KonamiHyperShot) {
		log("[Input] Konami Hyper Shot connected");
		expDevice = ControllerType::KonamiHyperShot;
	} else if(inputType == GameInputType::FamilyBasicKeyboard) {
		log("[Input] Family Basic Keyboard connected");
		expDevice = ControllerType::FamilyBasicKeyboard;
	} else if(inputType == GameInputType::PartyTap) {
		log("[Input] Party Tap connected");
		expDevice = ControllerType::PartyTap;
	} else if(inputType == GameInputType::PachinkoController) {
		log("[Input] Pachinko controller connected");
		expDevice = ControllerType::Pachinko;
	} else if(inputType == GameInputType::ExcitingBoxing) {
		log("[Input] Exciting Boxing controller connected");
		expDevice = ControllerType::ExcitingBoxing;
	} else if(inputType == GameInputType::SuborKeyboardMouse1) {
		log("[Input] Subor mouse connected");
		log("[Input] Subor keyboard connected");
		expDevice = ControllerType::SuborKeyboard;
		port2 = ControllerType::SuborMouse;
	} else if(inputType == GameInputType::JissenMahjong) {
		log("[Input] Jissen Mahjong controller connected");
		expDevice = ControllerType::JissenMahjong;
	} else if(inputType == GameInputType::BarcodeBattler) {
		log("[Input] Barcode Battler barcode reader connected");
		expDevice = ControllerType::BarcodeBattler;
	} else if(inputType == GameInputType::BandaiHypershot) {
		log("[Input] Bandai Hyper Shot gun connected");
		expDevice = ControllerType::BandaiHyperShot;
	} else if(inputType == GameInputType::BattleBox) {
		log("[Input] Battle Box connected");
		expDevice = ControllerType::BattleBox;
	} else if(inputType == GameInputType::TurboFile) {
		log("[Input] Ascii Turbo File connected");
		expDevice = ControllerType::AsciiTurboFile;
	} else if(inputType == GameInputType::FamilyTrainerSideA) {
		log("[Input] Family Trainer mat connected (Side A)");
		expDevice = ControllerType::FamilyTrainerMatSideA;
	} else if(inputType == GameInputType::FamilyTrainerSideB) {
		log("[Input] Family Trainer mat connected (Side B)");
		expDevice = ControllerType::FamilyTrainerMatSideB;
	} else if(inputType == GameInputType::PowerPadSideA) {
		log("[Input] Power Pad connected (Side A)");
		port2 = ControllerType::PowerPadSideA;
	} else if(inputType == GameInputType::PowerPadSideB) {
		log("[Input] Power Pad connected (Side B)");
		port2 = ControllerType::PowerPadSideB;
	} else if(inputType == GameInputType::SnesControllers) {
		log("[Input] 2 SNES controllers connected");
		port1 = ControllerType::SnesController;
		port2 = ControllerType::SnesController;
	} else if(inputType == GameInputType::FcnsController) {
		log("[Input] FCNS controller connected");
		expDevice = ControllerType::FcnsController;
	} else {
		log("[Input] 2 NES controllers connected");
	}

	isFamicom = (system == GameSystem::Famicom || system == GameSystem::FDS || system == GameSystem::Dendy);

	NesConfig& cfg = GetNesConfig();
	cfg.Port1.Type = port1;
	cfg.Port2.Type = port2;
	cfg.ExpPort.Type = expDevice;

	if(port1 == ControllerType::FourScore) {
		cfg.Port1SubPorts[0].Type = ControllerType::NesController;
		cfg.Port1SubPorts[1].Type = ControllerType::NesController;
		cfg.Port1SubPorts[2].Type = ControllerType::NesController;
		cfg.Port1SubPorts[3].Type = ControllerType::NesController;
	} else if(expDevice == ControllerType::TwoPlayerAdapter) {
		cfg.ExpPortSubPorts[0].Type = ControllerType::NesController;
		cfg.ExpPortSubPorts[1].Type = ControllerType::NesController;
	}
	_emu->GetNotificationManager()->SendNotification(ConsoleNotificationType::RequestConfigChange);
}

void NesConsole::ProcessCheatCode(InternalCheatCode& code, uint32_t addr, uint8_t& value)
{
	if(code.Type == CheatType::NesGameGenie && addr >= 0xC020) {
		if(GetNesConfig().DisableGameGenieBusConflicts || _mapper->HasDefaultWorkRam()) {
			return;
		}

		AddressInfo absAddr = _mapper->GetAbsoluteAddress(addr - 0x8000);
		if(absAddr.Address >= 0) {
			//Game Genie causes a bus conflict when the cartridge maps anything below $8000
			//Only processed when addr >= $C020 because the mapper implementation never maps anything below $4020
			value &= _mapper->DebugReadRam(addr - 0x8000);
		}
	}
}

void NesConsole::InitializeRam(void* data, uint32_t length)
{
	EmuSettings* settings = _emu->GetSettings();
	settings->InitializeRam(settings->GetNesConfig().RamPowerOnState, data, length);
}

DipSwitchInfo NesConsole::GetDipSwitchInfo()
{
	DipSwitchInfo info = {};
	info.DatabaseId = _mapper->GetRomInfo().Hash.PrgCrc32;

	switch(GetRomFormat()) {
		case RomFormat::VsSystem: info.DipSwitchCount = 8; break;
		case RomFormat::VsDualSystem: info.DipSwitchCount = 16; break;
		default: info.DipSwitchCount = _mapper->GetMapperDipSwitchCount(); break;
	}

	return info;
}

void NesConsole::ProcessNotification(ConsoleNotificationType type, void* parameter)
{
	if(type == ConsoleNotificationType::ExecuteShortcut) {
		ExecuteShortcutParams* params = (ExecuteShortcutParams*)parameter;
		switch(params->Shortcut) {
			default: break;
			case EmulatorShortcut::StartRecordHdPack: StartRecordingHdPack(*(HdPackBuilderOptions*)params->ParamPtr); break;
			case EmulatorShortcut::StopRecordHdPack: StopRecordingHdPack(); break;
			case EmulatorShortcut::ExportRomTilesHdPack: ExportRomTilesHdPack(*(HdPackBuilderOptions*)params->ParamPtr); break;
			case EmulatorShortcut::ExtractAudioHdPack: ExtractAudioHdPack(*(HdPackBuilderOptions*)params->ParamPtr); break;
		}
	}
}

//Static export of CHR ROM as defaultTile entries (no gameplay needed). CHR
//RAM games have no tile data in the ROM - only recording works for them.
void NesConsole::ExportRomTilesHdPack(HdPackBuilderOptions options)
{
	auto lock = _emu->AcquireLock();
	bool chrRam = !_mapper->HasChrRom() || _mapper->GetChrRomSize() == 0;

	uint32_t added;
	{
		HdPackBuilder builder(_emu, _ppu->GetPpuModel(), chrRam, options);
		if(chrRam) {
			//Tiles live somewhere in PRG ROM (copied to CHR RAM by code): heuristic scan
			added = builder.AddPrgScanTiles(_mapper->GetPrgRomData(), _mapper->GetPrgRomSize());
		} else {
			added = builder.AddRomTiles(_mapper->GetChrRomData(), _mapper->GetChrRomSize());
		}
	} //destructor writes the pack

	if(chrRam) {
		MessageManager::Log("[HDPack] ROM tile export: " + std::to_string(added) + " new defaultTile entries found by scanning " + std::to_string(_mapper->GetPrgRomSize() / 1024) + " KB of PRG ROM (CHR RAM game - heuristic, palettes only known at run time)");
	} else {
		MessageManager::Log("[HDPack] ROM tile export: " + std::to_string(added) + " new defaultTile entries from " + std::to_string(_mapper->GetChrRomSize() / 16) + " CHR ROM tiles");
	}
	MessageManager::DisplayMessage("HdPack", "HdPackExportDone", std::to_string(added));
}

//F5.4g Block D item 11: "Extract audio" — launches the headless extract-audio
//probe (ADR-0135) as its own process. The tool is NES/APU-specific, keeps a
//private home and a private copy of the ROM in a scratch workdir, and writes
//<pack-folder>/auto/audio/{fingerprints.json,midi/,enumeration.log}. The GUI
//action only resolves the tool binary and spawns it detached; the game keeps
//playing and the results are picked up from the pack folder afterwards.
static string ResolveExtractAudioToolPath()
{
	//1. Explicit override (dev builds, CI, custom installs).
	const char* env = getenv("MESEN_EXTRACT_AUDIO_TOOL");
	if(env && *env) {
		return env;
	}

	//2. Next to the app executable (shipped/bundled layout).
	string exeFolder = ProcessUtilities::GetExecutableFolder();
	if(!exeFolder.empty()) {
		string nextTo = FolderUtilities::CombinePath(exeFolder, "spike_sound_driver");
		if(std::filesystem::exists(nextTo)) {
			return nextTo;
		}
	}

	//3. ~/Tools (user-level install).
	string homeTools = FolderUtilities::CombinePath(
		FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), "Tools"), "spike_sound_driver");
	if(std::filesystem::exists(homeTools)) {
		return homeTools;
	}

	return "";
}

void NesConsole::ExtractAudioHdPack(HdPackBuilderOptions options)
{
	auto lock = _emu->AcquireLock();

	string toolPath = ResolveExtractAudioToolPath();
	if(toolPath.empty()) {
		MessageManager::Log("[HDPack] extract-audio: tool not found - build it with `make spike-sound-driver` and set MESEN_EXTRACT_AUDIO_TOOL (or drop the binary next to the Mesen executable / in ~/Tools)");
		MessageManager::DisplayMessage("HdPack", "HdPackExtractAudioToolMissing");
		return;
	}

	VirtualFile romFile = _emu->GetRomInfo().RomFile;
	string workdir = FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), "tmp/extract-audio");
	vector<string> args = {
		romFile.GetFilePath(),
		workdir,
		options.SaveFolder ? options.SaveFolder : FolderUtilities::CombinePath(FolderUtilities::GetHomeFolder(), "HdPacks")
	};

	if(!ProcessUtilities::StartDetached(toolPath, args)) {
		MessageManager::Log("[HDPack] extract-audio: failed to start " + toolPath);
		MessageManager::DisplayMessage("HdPack", "HdPackExtractAudioStartFailed");
		return;
	}

	MessageManager::Log("[HDPack] extract-audio: probe started (" + toolPath + ") on " + romFile.GetFilePath() + " - results will land in the pack folder's auto/audio/");
	MessageManager::DisplayMessage("HdPack", "HdPackExtractAudioStarted");
}

//F5.4d: coverage report for the builder window. Reads the live builder under the
//emulation lock (ProcessTile/AddTile mutate the maps on the emulation thread);
//zero-fills when not recording. Called from the UI thread via the interop layer.
void NesConsole::GetHdPackCoverageReport(HdPackCoverageReport& report) const
{
	report = {};
	auto lock = _emu->AcquireLock();
	if(_hdPackBuilder) {
		report = _hdPackBuilder->GetCoverageReport();
	}
}

void NesConsole::StartRecordingHdPack(HdPackBuilderOptions options)
{
	auto lock = _emu->AcquireLock();

	_emu->GetVideoDecoder()->WaitForAsyncFrameDecode();

	std::stringstream saveState;
	_emu->Serialize(saveState, false, 0);

	_hdPackBuilder.reset();
	_hdPackBuilder.reset(new HdPackBuilder(_emu, _ppu->GetPpuModel(), !_mapper->HasChrRom(), options));

	_memoryManager->UnregisterIODevice(_ppu.get());
	_ppu.reset(new HdBuilderPpu(this, _hdPackBuilder.get(), options.ChrRamBankSize));
	_memoryManager->RegisterIODevice(_ppu.get());

	_emu->Deserialize(saveState, SaveStateManager::FileFormatVersion, false);
	_emu->GetSoundMixer()->StopAudio();

	_emu->GetVideoDecoder()->ForceFilterUpdate();
}

void NesConsole::EnableBootstrapScreenCapture()
{
	if(_hdPackBuilder) {
		_hdPackBuilder->EnableScreenCapture();
	}
}

void NesConsole::StopRecordingHdPack()
{
	if(_hdPackBuilder) {
		auto lock = _emu->AcquireLock();

		_emu->GetVideoDecoder()->WaitForAsyncFrameDecode();

		std::stringstream saveState;
		_emu->Serialize(saveState, false, 0);

		_memoryManager->UnregisterIODevice(_ppu.get());
		if(_hdData) {
			_ppu.reset(new HdNesPpu(this, _hdData.get()));
		} else {
			_ppu.reset(new DefaultNesPpu(this));
		}
		_memoryManager->RegisterIODevice(_ppu.get());
		_hdPackBuilder.reset();

		_emu->Deserialize(saveState, SaveStateManager::FileFormatVersion, false);
		_emu->GetSoundMixer()->StopAudio();
		_emu->GetVideoDecoder()->ForceFilterUpdate();
	}
}
