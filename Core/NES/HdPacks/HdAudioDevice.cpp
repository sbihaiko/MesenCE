#include "pch.h"
#include "NES/HdPacks/HdAudioDevice.h"
#include "NES/HdPacks/HdData.h"
#include "NES/HdPacks/OggMixer.h"
#include "NES/HdPacks/OggReader.h"
#include "NES/NesConsole.h"
#include "Shared/MessageManager.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Audio/SoundMixer.h"
#include "Utilities/Serializer.h"

HdAudioDevice::HdAudioDevice(Emulator* emu, HdPackData* hdData)
{
	_emu = emu;
	_hdData = hdData;
	_album = 0;
	_playbackOptions = 0;
	_trackError = false;
	_sfxVolume = 128;
	_bgmVolume = 128;

	//ADR-0142: the mixer is host-free; this is the one site that binds it to the
	//emulator (run-ahead probe) and to the real stb_vorbis-backed source.
	std::function<bool()> isRunAheadFrame = [emu]() { return emu->IsRunAheadFrame(); };
	OggMixer::SourceFactory createSource = [isRunAheadFrame](string filename, bool loop, uint32_t sampleRate, uint32_t startOffset, uint32_t loopPosition) -> shared_ptr<IOggSource> {
		shared_ptr<OggReader> reader(new OggReader(isRunAheadFrame));
		return reader->Init(filename, loop, sampleRate, startOffset, loopPosition) ? reader : nullptr;
	};
	_oggMixer.reset(new OggMixer(isRunAheadFrame, createSource));
	_oggMixer->SetBgmVolume(_bgmVolume);
	_oggMixer->SetSfxVolume(_sfxVolume);
	_emu->GetSoundMixer()->RegisterAudioProvider(_oggMixer.get());
}

HdAudioDevice::~HdAudioDevice()
{
	_emu->GetSoundMixer()->UnregisterAudioProvider(_oggMixer.get());
}

void HdAudioDevice::Serialize(Serializer& s)
{
	int32_t trackOffset = 0;
	if(s.IsSaving()) {
		trackOffset = _oggMixer->GetBgmOffset();
		if(trackOffset < 0) {
			_lastBgmTrack = -1;
		}
		SV(_album);
		SV(_lastBgmTrack);
		SV(trackOffset);
		SV(_sfxVolume);
		SV(_bgmVolume);
		SV(_playbackOptions);
	} else {
		SV(_album);
		SV(_lastBgmTrack);
		SV(trackOffset);
		SV(_sfxVolume);
		SV(_bgmVolume);
		SV(_playbackOptions);

		if(!_emu->IsRunAheadFrame()) {
			if(_lastBgmTrack != -1 && trackOffset > 0) {
				PlayBgmTrack(_lastBgmTrack, trackOffset);
			}
			_oggMixer->SetBgmVolume(_bgmVolume);
			_oggMixer->SetSfxVolume(_sfxVolume);
			_oggMixer->SetPlaybackOptions(_playbackOptions);
		}
	}
}

bool HdAudioDevice::IsPackAudioEnabled()
{
	EnhancementPackConfig& cfg = _emu->GetSettings()->GetEnhancementPackConfig();
	return cfg.EnableMepPacks && cfg.EnableAudio;
}

bool HdAudioDevice::IsPlaying()
{
	return _oggMixer->IsBgmPlaying() || _oggMixer->IsSfxPlaying();
}

void HdAudioDevice::ProcessFrame()
{
	if(!IsPackAudioEnabled() && IsPlaying()) {
		_oggMixer->StopBgm();
		_oggMixer->StopSfx();
		_lastBgmTrack = -1;
		MessageManager::Log("[HDPack] pack audio disabled in settings - OGG playback stopped");
	}
}

bool HdAudioDevice::PlayBgmTrack(int trackId, uint32_t startOffset)
{
	if(!IsPackAudioEnabled()) {
		return false;
	}
	auto result = _hdData->BgmFilesById.find(trackId);
	if(result != _hdData->BgmFilesById.end()) {
		if(_oggMixer->Play(result->second.Filename, false, startOffset, result->second.LoopPosition)) {
			_lastBgmTrack = trackId;
			if(!_noticeShown) {
				//Tell the player where the music comes from - otherwise the
				//Enhanced Audio toggle seems to do nothing while a pack's OGG plays
				_noticeShown = true;
				MessageManager::DisplayMessage("HDPack", "Pack music is replacing the game's music - Tools > Enhancement Packs: turn off 'Audio (OGG)' (and 'ROM patch' if the game then goes silent)");
				MessageManager::Log("[HDPack] pack OGG replacing the game's music: " + result->second.Filename);
			}
			return true;
		}
	} else {
		MessageManager::Log("[HDPack] Invalid album+track combination: " + std::to_string(_album) + ":" + std::to_string(trackId & 0xFF));
	}
	return false;
}

bool HdAudioDevice::PlayReplacementBgm(int trackId, bool loop)
{
	_oggMixer->SetPlaybackOptions(loop ? (_playbackOptions | 0x01) : _playbackOptions);
	if(_bgmVolume == 0) {
		//Games that never wrote the HD registers leave the volume at 0
		_oggMixer->SetBgmVolume(255);
	}
	return PlayBgmTrack(trackId, 0);
}

void HdAudioDevice::StopReplacementBgm()
{
	_oggMixer->StopBgm();
	_oggMixer->SetPlaybackOptions(_playbackOptions);
	_lastBgmTrack = -1;
}

bool HdAudioDevice::PlaySfx(uint8_t sfxNumber)
{
	if(!IsPackAudioEnabled()) {
		return false;
	}
	auto result = _hdData->SfxFilesById.find(_album * 256 + sfxNumber);
	if(result != _hdData->SfxFilesById.end()) {
		return !_oggMixer->Play(result->second, true, 0, 0);
	} else {
		MessageManager::Log("[HDPack] Invalid album+sfx number combination: " + std::to_string(_album) + ":" + std::to_string(sfxNumber));
		return false;
	}
}

void HdAudioDevice::ProcessControlFlags(uint8_t flags)
{
	_oggMixer->SetPausedFlag((flags & 0x01) == 0x01);
	if(flags & 0x02) {
		_oggMixer->StopBgm();
	}
	if(flags & 0x04) {
		_oggMixer->StopSfx();
	}
}

void HdAudioDevice::GetMemoryRanges(MemoryRanges& ranges)
{
	bool useAlternateRegisters = (_hdData->OptionFlags & (int)HdPackOptions::AlternateRegisterRange) == (int)HdPackOptions::AlternateRegisterRange;
	ranges.SetAllowOverride();

	if(useAlternateRegisters) {
		for(int i = 0; i < 7; i++) {
			ranges.AddHandler(MemoryOperation::Write, 0x3002 + i * 0x10);
		}
		ranges.AddHandler(MemoryOperation::Read, 0x4018);
		ranges.AddHandler(MemoryOperation::Read, 0x4019);
	} else {
		ranges.AddHandler(MemoryOperation::Any, 0x4100, 0x4106);
	}
}

void HdAudioDevice::WriteRam(uint16_t addr, uint8_t value)
{
	//$4100/$3002: Playback Options
	//$4101/$3012: Playback Control
	//$4102/$3022: BGM Volume
	//$4103/$3032: SFX Volume
	//$4104/$3042: Album Number
	//$4105/$3052: Play BGM Track
	//$4106/$3062: Play SFX Track
	int regNumber = addr > 0x4100 ? (addr & 0xF) : ((addr & 0xF0) >> 4);

	switch(regNumber) {
		//Playback Options
		//Bit 0: Loop BGM
		//Bit 1-7: Unused, reserved - must be 0
		case 0:
			_playbackOptions = value;
			_oggMixer->SetPlaybackOptions(_playbackOptions);
			break;

		//Playback Control
		//Bit 0: Toggle Pause/Resume (only affects BGM)
		//Bit 1: Stop BGM
		//Bit 2: Stop all SFX
		//Bit 3-7: Unused, reserved - must be 0
		case 1: ProcessControlFlags(value); break;

		//BGM Volume: 0 = mute, 255 = max
		//Also has an immediate effect on currently playing BGM
		case 2:
			_bgmVolume = value;
			_oggMixer->SetBgmVolume(value);
			break;

		//SFX Volume: 0 = mute, 255 = max
		//Also has an immediate effect on all currently playing SFX
		case 3:
			_sfxVolume = value;
			_oggMixer->SetSfxVolume(value);
			break;

		//Album number: 0-255 (Allows for up to 64k BGM and SFX tracks)
		//No immediate effect - only affects subsequent $4FFE/$4FFF writes
		case 4: _album = value; break;

		//Play BGM track (0-255 = track number)
		//Stop the current BGM and starts a new track
		case 5: _trackError = PlayBgmTrack(_album * 256 + value, 0); break;

		//Play sound effect (0-255 = sfx number)
		//Plays a new sound effect (no limit to the number of simultaneous sound effects)
		case 6: _trackError = PlaySfx(value); break;
	}
}

uint8_t HdAudioDevice::ReadRam(uint16_t addr)
{
	//$4100/$4018: Status
	//$4101/$4019: Revision
	//$4102: 'N' (signature to help detection)
	//$4103: 'E'
	//$4103: 'A'
	switch(addr & 0x7) {
		case 0:
			//Status
			return (
				(_oggMixer->IsBgmPlaying() ? 1 : 0) |
				(_oggMixer->IsSfxPlaying() ? 2 : 0) |
				(_trackError ? 4 : 0));

		case 1: return 1; //Revision
		case 2: return 'N'; //NES
		case 3: return 'E'; //Enhanced
		case 4: return 'A'; //Audio
	}

	return 0;
}
