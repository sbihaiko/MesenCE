#include "pch.h"
#include "Shared/LiveFrameRecorder.h"
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/Video/VideoDecoder.h"
#include "Shared/Video/FrameCapture.h"
#include "NES/NesConsole.h"
#include "NES/BaseNesPpu.h"
#include "NES/BaseMapper.h"
#include "NES/NesTypes.h"
#include "Utilities/LiveRecordFormat.h"
#include "Utilities/FolderUtilities.h"

LiveFrameRecorder::LiveFrameRecorder(Emulator* emu) : _emu(emu)
{
	_stopFlag = true;
}

LiveFrameRecorder::~LiveFrameRecorder()
{
	StopRecording();
}

bool LiveFrameRecorder::StartRecording(string liveDir, int intervalMs)
{
	if(intervalMs < 50 || IsRecording()) {
		return false;
	}

	auto lock = _stopStartLock.AcquireSafe();
	if(_thread) {
		return false;
	}

	FolderUtilities::CreateFolder(liveDir);
	_liveDir = liveDir;
	_intervalMs = intervalMs;
	_wallClock.Reset();
	_stopFlag = false;
	_thread.reset(new std::thread(&LiveFrameRecorder::ThreadLoop, this));
	return true;
}

void LiveFrameRecorder::StopRecording()
{
	_stopFlag = true;
	if(_thread) {
		auto lock = _stopStartLock.AcquireSafe();
		if(_thread) {
			_thread->join();
			_thread.reset();
			//ADR-0169 section 1: a final status so the viewer shows "stopped"
			//rather than stale progress - the human-driven equivalent of the
			//scripted run reaching its target frame. There is no target here,
			//so targetFrames stays 0 (the viewer reads that as "no target").
			if(!_liveDir.empty()) {
				LiveRecordFormat::AtomicWrite(_liveDir + "/status.json",
					LiveRecordFormat::ComposeStatusJson(true, _emu->GetFrameCount(), 0, _wallClock.GetElapsedMS() / 1000.0));
			}
		}
	}
}

bool LiveFrameRecorder::IsRecording()
{
	return _thread != nullptr;
}

bool LiveFrameRecorder::CaptureSnapshot(LiveSnapshot& snapshot)
{
	vector<uint32_t> pixels;
	ScreenshotCapture info = _emu->GetVideoDecoder()->CaptureScreenshot(pixels);
	if(info.IsEmpty()) {
		return false; //nothing decoded yet
	}
	snapshot.Width = info.Width;
	snapshot.Height = info.Height;
	snapshot.CaptureFrame = info.FrameNumber;
	snapshot.Pixels = std::move(pixels);

	//Same channel scripts/headless_record uses (ADR-0169 Decision section 2):
	//Emulator::Lock() parks the emulation thread at an end-of-frame boundary
	//without attaching a debugger, so a live recording never stalls the game
	//the way GetMemoryState/GetPpuState would. Called here from this
	//recorder's own thread - never the emulation thread itself.
	_emu->Lock();
	NesConsole* nes = dynamic_cast<NesConsole*>(_emu->GetConsole().get());
	if(nes) {
		NesPpuState ppu = {};
		nes->GetPpu()->GetState(ppu);
		ConsoleMemoryInfo oamMem = _emu->GetMemory(MemoryType::NesSpriteRam);
		if(oamMem.Memory) {
			memcpy(snapshot.Oam, oamMem.Memory, std::min(oamMem.Size, (uint32_t)0x100));
		}
		ConsoleMemoryInfo palMem = _emu->GetMemory(MemoryType::NesPaletteRam);
		if(palMem.Memory) {
			memcpy(snapshot.Palette, palMem.Memory, std::min(palMem.Size, (uint32_t)0x20));
		}
		snapshot.Chr.assign(0x2000, 0);
		for(uint32_t i = 0; i < 0x2000; i++) {
			snapshot.Chr[i] = nes->DebugReadVram((uint16_t)i);
		}
		snapshot.SpritePatternAddr = ppu.Control.SpritePatternAddr;
		snapshot.LargeSprites = ppu.Control.LargeSprites;
		snapshot.SpritesEnabled = ppu.Mask.SpritesEnabled;
		//Mask.SpriteMask/BackgroundMask are a "show" flag, not a "clip" one
		//(NesPpu.cpp's own comment: "BackgroundMask = false: Hide background in
		//leftmost 8 pixels") - LeftColumnClip/BackgroundLeftColumnClip name the
		//wire field for what it actually gates (clipping), so the polarity is
		//inverted here rather than at every reader.
		snapshot.LeftColumnClip = !ppu.Mask.SpriteMask;
		snapshot.HasSprites = true;

		//The background layer, read the same instant as the sprite layer above
		//(2026-09-08 ADR-0169 update: "capture every layer" so the viewer can
		//multiplex sprites over it the way the PPU does, instead of drawing
		//sprites over a plain backdrop). DebugReadVram resolves mirroring, so a
		//flat $2000-$2FFF read already lands each nametable in its hardware slot.
		snapshot.Nametables.assign(0x1000, 0);
		for(uint32_t i = 0; i < 0x1000; i++) {
			snapshot.Nametables[i] = nes->DebugReadVram((uint16_t)(0x2000 + i));
		}
		snapshot.BackgroundPatternAddr = ppu.Control.BackgroundPatternAddr;
		snapshot.BackgroundEnabled = ppu.Mask.BackgroundEnabled;
		snapshot.BackgroundLeftColumnClip = !ppu.Mask.BackgroundMask;
		//The end-of-frame boundary this capture runs on has loopy "v" already
		//scanned through the whole frame, so the base scroll comes from loopy "t"
		//(TmpVideoRamAddr) - the scroll the game wrote and the next frame renders
		//with (see LiveRecordFormat.h's field comment).
		snapshot.TmpVideoRamAddr = ppu.TmpVideoRamAddr;
		snapshot.FineScrollX = ppu.ScrollX;
		snapshot.HasBackground = true;

		//MMC2/MMC4 CHR-latch extension (BaseMapper::HasChrBankLatch): the raw
		//CHR-ROM plus both banks per half, published only for a mapper that
		//actually has the latch (Mike Tyson's Punch-Out and its sequel) - see
		//BaseMapper.h's comment for why the plain Chr[] snapshot above cannot
		//be trusted for these.
		BaseMapper* mapper = nes->GetMapper();
		if(mapper && mapper->HasChrBankLatch()) {
			snapshot.HasChrLatch = true;
			snapshot.ChrLatchPageSize = mapper->GetChrLatchPageSize();
			mapper->GetChrLatchBanks(snapshot.LeftChrFdBank, snapshot.LeftChrFeBank, snapshot.RightChrFdBank, snapshot.RightChrFeBank);
			uint8_t* romData = mapper->GetChrRomData();
			uint32_t romSize = mapper->GetChrRomSize();
			snapshot.ChrRomFull.assign(romData, romData + romSize);
		}

		//palette.json, captured once: the exact RGB this run renders with, so
		//the viewer colors reconstructed sprites like the composed frame
		//(ADR-0169 section 2). The NES config's UserPalette[0..64) is the base
		//64-color table the 2C02 filter copies verbatim at zero emphasis - i.e.
		//the table palette.json must carry, whether default or user-customized.
		//Read under the same lock as the sprite bytes, then cached; it never
		//changes mid-run. Mirrors headless_record's own one-time palette write.
		if(_paletteJson.empty()) {
			NesConfig& nesCfg = _emu->GetSettings()->GetNesConfig();
			char hex[16];
			string json = "{\n  \"colors\": [";
			for(int i = 0; i < 64; i++) {
				if(i) json += ",";
				snprintf(hex, sizeof(hex), "\"#%06X\"", nesCfg.UserPalette[i] & 0xFFFFFF);
				json += hex;
			}
			json += "]\n}\n";
			_paletteJson = std::move(json);
		}
	}
	_emu->Unlock();

	return true;
}

void LiveFrameRecorder::ThreadLoop()
{
	bool paletteWritten = false;
	while(!_stopFlag.load()) {
		double elapsed = _wallClock.GetElapsedMS();
		LiveSnapshot snapshot;
		if(CaptureSnapshot(snapshot)) {
			LiveRecordFormat::AtomicWrite(_liveDir + "/frame.ppm", LiveRecordFormat::ComposePpm(snapshot));
			if(snapshot.HasSprites) {
				LiveRecordFormat::AtomicWrite(_liveDir + "/sprites.json", LiveRecordFormat::ComposeSpritesJson(snapshot, _emu->GetFrameCount()));
				LiveRecordFormat::AtomicWrite(_liveDir + "/chr.bin", snapshot.Chr.data(), snapshot.Chr.size());

				//palette.json is immutable for the run (ADR-0169 section 2), so
				//write it once, on the first capture that filled it.
				if(!paletteWritten && !_paletteJson.empty()) {
					LiveRecordFormat::AtomicWrite(_liveDir + "/palette.json", _paletteJson);
					paletteWritten = true;
				}
			}
			if(snapshot.HasBackground) {
				LiveRecordFormat::AtomicWrite(_liveDir + "/nametables.bin", snapshot.Nametables.data(), snapshot.Nametables.size());
				LiveRecordFormat::AtomicWrite(_liveDir + "/background.json", LiveRecordFormat::ComposeBackgroundJson(snapshot));
			}
			if(snapshot.HasChrLatch) {
				LiveRecordFormat::AtomicWrite(_liveDir + "/chrfull.bin", snapshot.ChrRomFull.data(), snapshot.ChrRomFull.size());
				LiveRecordFormat::AtomicWrite(_liveDir + "/chrlatch.json", LiveRecordFormat::ComposeChrLatchJson(snapshot));
			}
			LiveRecordFormat::AtomicWrite(_liveDir + "/status.json",
				LiveRecordFormat::ComposeStatusJson(false, _emu->GetFrameCount(), 0, elapsed / 1000.0));
		}

		//Sleep the remainder of the interval, not the whole interval - the
		//capture itself has a cost (ADR-0169 Consequences bullet 2).
		double captureCost = _wallClock.GetElapsedMS() - elapsed;
		int sleepMs = _intervalMs - (int)captureCost;
		std::this_thread::sleep_for(std::chrono::milliseconds(std::max(1, sleepMs)));
	}
}
