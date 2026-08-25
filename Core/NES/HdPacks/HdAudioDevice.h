#pragma once
#include "pch.h"
#include "NES/INesMemoryHandler.h"
#include "Utilities/ISerializable.h"

struct HdPackData;
class Emulator;
class OggMixer;

class HdAudioDevice : public INesMemoryHandler, public ISerializable
{
private:
	Emulator* _emu = nullptr;
	HdPackData* _hdData = nullptr;
	uint8_t _album = 0;
	uint8_t _playbackOptions = 0;
	bool _trackError = false;
	unique_ptr<OggMixer> _oggMixer;
	int32_t _lastBgmTrack = 0;
	uint8_t _bgmVolume = 0;
	uint8_t _sfxVolume = 0;
	bool _noticeShown = false;

	bool PlayBgmTrack(int trackId, uint32_t startOffset);
	bool PlaySfx(uint8_t sfxNumber);
	void ProcessControlFlags(uint8_t flags);

protected:
	void Serialize(Serializer& s) override;

public:
	HdAudioDevice(Emulator* emu, HdPackData* hdData);
	~HdAudioDevice();

	//F5.3 (ADR-0047): playback driven by the fingerprint matcher instead of
	//game writes to $41xx. Loop is forced on for BGM; stop restores the
	//game's own playback options.
	bool PlayReplacementBgm(int trackId, bool loop);
	void StopReplacementBgm();

	//Once per frame: stops any OGG still playing after the user turned pack
	//audio off, so the toggle takes effect live instead of on the next track
	void ProcessFrame();
	bool IsPlaying();
	//Tools > Enhancement Packs > "Audio (OGG)" (EnhancementPackConfig.EnableAudio)
	//gates every OGG the pack plays - the HDNes-style <bgm>/<sfx> driven by
	//$41xx writes as well as the F5.3 fingerprint replacement
	bool IsPackAudioEnabled();

	void GetMemoryRanges(MemoryRanges& ranges) override;
	void WriteRam(uint16_t addr, uint8_t value) override;
	uint8_t ReadRam(uint16_t addr) override;
};