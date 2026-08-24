#include "Shared/Interfaces/IAudioProvider.h"
#include "Utilities/Audio/HermiteResampler.h"
#include "Utilities/ISerializable.h"

class Emulator;
class SmsConsole;
typedef struct __OPLL OPLL;

//Live VGM capture note: Write() carries a VgmExporter::LogWrite tap for the
//YM2413 register-select ($F0) and data ($F1) ports - see VgmExporter.h for
//the log format and the 2-call latch/data protocol.
class SmsFmAudio final : public ISerializable, public IAudioProvider
{
private:
	Emulator* _emu = nullptr;
	SmsConsole* _console = nullptr;
	OPLL* _opll = nullptr;
	HermiteResampler _resampler;
	vector<int16_t> _samplesToPlay;
	uint64_t _prevMasterClock = 0;
	uint8_t _audioControl = 0;
	bool _fmEnabled = false;

public:
	SmsFmAudio(Emulator* emu, SmsConsole* console);
	~SmsFmAudio();

	void Run();

	bool IsPsgAudioMuted();

	//Copies the OPLL's raw register file (0x00-0x3F) out for
	//SmsEnhancedSynth to re-interpret, the same way it reads SmsPsg's live
	//channel state - see SmsEnhancedSynth::MixAudio.
	void GetRegisters(uint8_t out[0x40]) const;

	uint8_t Read();
	void Write(uint8_t port, uint8_t value);

	void MixAudio(int16_t* out, uint32_t sampleCount, uint32_t sampleRate) override;
	void Serialize(Serializer& s) override;
};