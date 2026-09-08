#include "pch.h"
#include <filesystem>
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
#include "Shared/MessageManager.h"

LiveFrameRecorder::LiveFrameRecorder(Emulator* emu) : _emu(emu)
{
	_stopFlag = true;
}

LiveFrameRecorder::~LiveFrameRecorder()
{
	StopRecording();
}

void LiveFrameRecorder::ClearSlot(const string& liveDir)
{
	//The slot is one directory by convention (ADR-0169 section 4), reused by
	//every run, and a run only writes the files its own ROM has data for. Left
	//alone, a run inherits the previous ROM's leftovers for everything it does
	//not rewrite - and the viewer cannot tell the difference, because presence
	//is the signal it selects a reconstruction path with. Observed: a CHR-latch
	//ROM (Punch-Out, MMC2) left chrlatch.json + chrfull.bin behind, the next run
	//(Bubble Bobble, no latch) never rewrote either, and record_viewer.py took
	//the latch path resolving Bubble Bobble's tiles against Punch-Out's CHR-ROM,
	//rendering garbage. So the slot is emptied of the whole publish set here,
	//before the first tick: whatever a file's presence means to the viewer, it
	//now means it about THIS run. The .tmp siblings go too - AtomicWrite renames
	//over the target, but a run killed mid-write can leave one.
	static const char* kPublishFiles[] = {
		"frame.ppm", "sprites.json", "chr.bin", "palette.json", "nametables.bin",
		"background.json", "scanlinescroll.bin", "scanlinechrbank.bin",
		"chrfull.bin", "chrlatch.json", "status.json"
	};
	for(const char* name : kPublishFiles) {
		string path = FolderUtilities::CombinePath(liveDir, name);
		std::error_code ignored;
		std::filesystem::remove(path, ignored);
		std::filesystem::remove(path + ".tmp", ignored);
	}
	//palette.json is written once per run from the first capture that fills it
	//(see ThreadLoop) - clearing the file has to clear that latch too, or the
	//next run publishes nothing and the viewer colors it with no palette at all.
	_paletteJson.clear();
}

bool LiveFrameRecorder::StartRecording(string liveDir, int intervalMs)
{
	//Every exit is logged: an empty slot has three very different causes (the
	//click never reached here, this refused, or the thread ran and never got a
	//decoded frame) and they are indistinguishable from the filesystem alone.
	if(intervalMs < 50 || IsRecording()) {
		MessageManager::Log("[LiveRecording] start refused: intervalMs=" + std::to_string(intervalMs) + (IsRecording() ? " (already recording)" : " (below the 50ms floor)"));
		return false;
	}

	auto lock = _stopStartLock.AcquireSafe();
	if(_thread) {
		MessageManager::Log("[LiveRecording] start refused: a thread is already running");
		return false;
	}

	FolderUtilities::CreateFolder(liveDir);
	ClearSlot(liveDir);
	_liveDir = liveDir;
	_intervalMs = intervalMs;
	_wallClock.Reset();
	_stopFlag = false;
	_thread.reset(new std::thread(&LiveFrameRecorder::ThreadLoop, this));
	MessageManager::Log("[LiveRecording] started, publishing to " + liveDir + " every " + std::to_string(intervalMs) + "ms");
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
					LiveRecordFormat::ComposeStatusJson(true, _emu->GetFrameCount(), 0, _wallClock.GetElapsedMS() / 1000.0, _hdPackActive.load()));
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
	//Same channel scripts/headless_record uses (ADR-0169 Decision section 2):
	//Emulator::Lock() parks the emulation thread at an end-of-frame boundary
	//without attaching a debugger, so a live recording never stalls the game
	//the way GetMemoryState/GetPpuState would. Called here from this
	//recorder's own thread - never the emulation thread itself.
	//
	//Locked *before* CaptureScreenshot (2026-09-08 ADR-0169 update, "frame/state
	//capture race"): CaptureScreenshot doesn't park the thread on its own, so
	//taking it first and locking afterwards let the console render further
	//frames in between, publishing pixels and PPU/OAM/palette/VRAM state that
	//describe two different frames - visible as the composite pane showing a
	//screen transition or a cycled color the reconstruction pane never sees.
	_emu->Lock();
	vector<uint32_t> pixels;
	ScreenshotCapture info = _emu->GetVideoDecoder()->CaptureScreenshot(pixels);
	if(info.IsEmpty()) {
		_emu->Unlock();
		return false; //nothing decoded yet
	}
	snapshot.Width = info.Width;
	snapshot.Height = info.Height;
	snapshot.CaptureFrame = info.FrameNumber;
	snapshot.Pixels = std::move(pixels);
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
		//See LiveRecordFormat.h's HdPackActive comment: with texture
		//substitution on, frame.ppm carries the pack's art while the CHR /
		//nametable / OAM bytes above carry the original tiles, so the viewer
		//must warn instead of scoring the two panes against each other.
		snapshot.HdPackActive = nes->IsHdPackVideoActive();

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

		//Per-scanline loopy v (2026-09-08 ADR-0169 update, "mid-frame raster
		//splits") - see BaseNesPpu::GetScanlineScrollTrace's own comment for why
		//TmpVideoRamAddr alone is not enough whenever the game rewrites scroll
		//mid-frame (a status-bar split, raster parallax).
		snapshot.ScanlineScroll.assign(240, 0);
		nes->GetPpu()->GetScanlineScrollTrace(snapshot.ScanlineScroll.data());

		//ADR-0169 2026-09-08 update ("mid-frame CHR bank splits") - see
		//LiveRecordFormat.h's ScanlineChrBank comment. Any ROM-backed mapper
		//(not just the MMC2/4 latch case below) can rewrite its CHR bank
		//registers mid-frame, so this is captured unconditionally whenever
		//CHR-ROM exists, regardless of HasChrBankLatch.
		BaseMapper* mapper = nes->GetMapper();
		bool chrBankTraceNeeded = mapper && mapper->GetChrRomSize() > 0;
		if(chrBankTraceNeeded) {
			snapshot.ScanlineChrBank.assign(240 * 0x20, 0);
			nes->GetPpu()->GetScanlineChrBankTrace(snapshot.ScanlineChrBank.data());
		}

		//MMC2/MMC4 CHR-latch extension (BaseMapper::HasChrBankLatch): the raw
		//CHR-ROM plus both banks per half, published for a mapper that
		//actually has the latch (Mike Tyson's Punch-Out and its sequel) - see
		//BaseMapper.h's comment for why the plain Chr[] snapshot above cannot
		//be trusted for these. Also published (2026-09-08 update) whenever
		//chrBankTraceNeeded above is true, even without a latch - the raw dump
		//backs ScanlineChrBank's offsets the same way it backs the latch banks.
		if(mapper && (mapper->HasChrBankLatch() || chrBankTraceNeeded)) {
			snapshot.HasChrLatch = mapper->HasChrBankLatch();
			if(snapshot.HasChrLatch) {
				snapshot.ChrLatchPageSize = mapper->GetChrLatchPageSize();
				mapper->GetChrLatchBanks(snapshot.LeftChrFdBank, snapshot.LeftChrFeBank, snapshot.RightChrFdBank, snapshot.RightChrFeBank);
			}
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
	//One line for the first tick that publishes and one for the first that does
	//not: "the loop is alive but nothing has been decoded yet" is the failure
	//mode that looks exactly like "the recorder never started" from outside.
	bool loggedFirstPublish = false;
	bool loggedFirstSkip = false;
	while(!_stopFlag.load()) {
		double elapsed = _wallClock.GetElapsedMS();
		LiveSnapshot snapshot;
		bool captured = CaptureSnapshot(snapshot);
		if(!captured && !loggedFirstSkip) {
			MessageManager::Log("[LiveRecording] tick skipped: nothing decoded yet (no frame to publish)");
			loggedFirstSkip = true;
		}
		if(captured) {
			if(!loggedFirstPublish) {
				MessageManager::Log("[LiveRecording] first frame published: " + std::to_string(snapshot.Width) + "x" + std::to_string(snapshot.Height) + ", sprites=" + (snapshot.HasSprites ? "yes" : "no") + ", background=" + (snapshot.HasBackground ? "yes" : "no") + ", hdPack=" + (snapshot.HdPackActive ? "on" : "off"));
				loggedFirstPublish = true;
			}
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
				LiveRecordFormat::AtomicWrite(_liveDir + "/scanlinescroll.bin", snapshot.ScanlineScroll.data(), snapshot.ScanlineScroll.size() * sizeof(uint32_t));
				if(!snapshot.ScanlineChrBank.empty()) {
					LiveRecordFormat::AtomicWrite(_liveDir + "/scanlinechrbank.bin", snapshot.ScanlineChrBank.data(), snapshot.ScanlineChrBank.size() * sizeof(uint32_t));
				}
			}
			//ADR-0169 2026-09-08 update: chrfull.bin is written whenever
			//ChrRomFull got populated - either the MMC2/4 latch case
			//(HasChrLatch) or any other ROM-backed mapper's plain CHR bank
			//registers (ScanlineChrBank non-empty) - both need the raw dump to
			//resolve a non-current bank. chrlatch.json stays gated on the
			//actual latch flag; ComposeChrLatchJson already no-ops otherwise.
			if(!snapshot.ChrRomFull.empty()) {
				LiveRecordFormat::AtomicWrite(_liveDir + "/chrfull.bin", snapshot.ChrRomFull.data(), snapshot.ChrRomFull.size());
				LiveRecordFormat::AtomicWrite(_liveDir + "/chrlatch.json", LiveRecordFormat::ComposeChrLatchJson(snapshot));
			}
			_hdPackActive.store(snapshot.HdPackActive);
			LiveRecordFormat::AtomicWrite(_liveDir + "/status.json",
				LiveRecordFormat::ComposeStatusJson(false, _emu->GetFrameCount(), 0, elapsed / 1000.0, snapshot.HdPackActive));
		}

		//Sleep the remainder of the interval, not the whole interval - the
		//capture itself has a cost (ADR-0169 Consequences bullet 2).
		double captureCost = _wallClock.GetElapsedMS() - elapsed;
		int sleepMs = _intervalMs - (int)captureCost;
		std::this_thread::sleep_for(std::chrono::milliseconds(std::max(1, sleepMs)));
	}
}
