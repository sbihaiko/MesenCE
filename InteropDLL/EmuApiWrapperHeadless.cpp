#include "Common.h"
#include "Core/Shared/Emulator.h"
#include "Core/Shared/HeadlessInputProvider.h"
#include "Core/Shared/MessageManager.h"
#include "Core/Shared/Video/VideoDecoder.h"
#include "Core/Shared/Video/VideoRenderer.h"
#include "Core/Shared/Video/FrameCapture.h"
#include "Core/NES/NesConsole.h"
#include "Core/NES/BaseNesPpu.h"
#include "Core/NES/BaseMapper.h"
#include "Core/NES/NesTypes.h"
#include "Utilities/StringUtilities.h"

//F9.14 (ADR-0157), F9.15 and ADR-0167: the DLL surface scripts/headless_record
//needs to drive a recording in emulated frames instead of wall-clock seconds,
//read the frame it stopped on without going through Screenshots/, capture the
//system HUD alone, and gate the OSD message queue. Sibling file to
//EmuApiWrapper.cpp (already at its 200-line-per-file guardrail, see
//EmuApiWrapperMep.cpp for the same call). The input exports are thin
//marshaling over HeadlessInputProvider; the capture and OSD exports marshal
//over VideoRenderer/MessageManager directly - no scheduling logic lives here.

extern unique_ptr<Emulator> _emu;

//Kept alive for the process' lifetime: NotificationManager holds listeners by
//weak_ptr, so dropping this would silently unsubscribe the provider from
//GameLoaded and reintroduce the "input= is a no-op after a game load" trap.
static shared_ptr<HeadlessInputProvider> _headlessInput;

//F9.15: the last capture taken by HeadlessCaptureFrame, kept here so the
//harness can ask for its size and then read the pixels of *that* capture -
//a second call into the emulator would answer about a different frame.
static vector<uint32_t> _headlessCapture;
static ScreenshotCapture _headlessCaptureInfo;

//ADR-0167: the last capture taken by HeadlessCaptureHud, same one-buffer-at-a-
//time rule as _headlessCapture above.
static vector<uint32_t> _headlessHudCapture;

static HeadlessInputProvider* GetHeadlessInput()
{
	if(!_headlessInput) {
		_headlessInput.reset(new HeadlessInputProvider(_emu.get()));
		_headlessInput->Init();
	}
	return _headlessInput.get();
}

extern "C"
{
	//scriptText is the whole script file; frameRate resolves its 's' steps
	//(NTSC 60.0988 / PAL 50.0070 - the caller knows which region it forced).
	//Returns false and writes an en-US message naming the offending line into
	//outError when the script does not parse.
	DllExport bool __stdcall HeadlessLoadInputScript(const char* scriptText, double frameRate, char* outError, uint32_t maxErrorLength)
	{
		string error;
		bool success = GetHeadlessInput()->LoadScript(scriptText ? scriptText : "", frameRate, error);
		StringUtilities::CopyToBuffer(error, outError, maxErrorLength);
		return success;
	}

	//Pause the emulator from inside the first frame whose number reaches
	//'frame' (UINT32_MAX never pauses). This is how the harness stops a run on
	//an exact frame count rather than on elapsed host time.
	DllExport void __stdcall HeadlessSetPauseFrame(uint32_t frame)
	{
		GetHeadlessInput()->SetPauseFrame(frame);
	}

	//Length of the loaded script, in frames.
	DllExport uint32_t __stdcall HeadlessGetScriptFrameCount()
	{
		return GetHeadlessInput()->GetScriptFrameCount();
	}

	//The core's own frame counter - the cross-check that the harness' frame
	//budget and the emulated console agree (ADR-0157 section 4).
	DllExport uint32_t __stdcall HeadlessGetFrameCount()
	{
		return _emu->GetFrameCount();
	}

	//ADR-0169 2026-09-08 update ("frame/state capture race"): HeadlessCaptureFrame
	//reads the video filter's own buffer without parking the emulation thread,
	//while HeadlessCaptureNesSpriteLayer does (Emulator::Lock). A caller taking
	//both back to back with nothing in between can have the console render one
	//or more further frames between the two, so the pixels and the PPU/OAM/
	//palette/VRAM state it reads next disagree about which frame they describe -
	//visible as a live recording's composite pane showing a different moment
	//(a screen transition, a cycled backdrop color) than its reconstruction.
	//These two exports let a caller (scripts/headless_record's CaptureLiveSnapshot)
	//park the thread first and read both under the same freeze; SimpleLock is
	//reentrant by thread (see Utilities/SimpleLock.cpp), so nesting this around
	//HeadlessCaptureNesSpriteLayer's own Lock/Unlock is safe.
	DllExport void __stdcall HeadlessLockEmulator()
	{
		_emu->Lock();
	}

	DllExport void __stdcall HeadlessUnlockEmulator()
	{
		_emu->Unlock();
	}

	//Capture the frame the emulator is currently showing into the DLL-side
	//buffer, filtered exactly like a saved screenshot would be. Returns false
	//when nothing has been decoded yet; the out parameters are always written.
	DllExport bool __stdcall HeadlessCaptureFrame(uint32_t* outWidth, uint32_t* outHeight, uint32_t* outFrameNumber, uint32_t* outPixelCount)
	{
		_headlessCaptureInfo = _emu->GetVideoDecoder()->CaptureScreenshot(_headlessCapture);
		if(outWidth) { *outWidth = _headlessCaptureInfo.Width; }
		if(outHeight) { *outHeight = _headlessCaptureInfo.Height; }
		if(outFrameNumber) { *outFrameNumber = _headlessCaptureInfo.FrameNumber; }
		if(outPixelCount) { *outPixelCount = (uint32_t)_headlessCapture.size(); }
		return !_headlessCaptureInfo.IsEmpty();
	}

	//Copy the pixels of the last HeadlessCaptureFrame into the caller's
	//buffer, 0xAARRGGBB, row-major. Returns how many pixels were copied
	//(never more than maxPixels, never more than the capture holds).
	DllExport uint32_t __stdcall HeadlessReadCapturedPixels(uint32_t* outPixels, uint32_t maxPixels)
	{
		if(!outPixels || _headlessCapture.empty()) {
			return 0;
		}
		uint32_t count = std::min(maxPixels, (uint32_t)_headlessCapture.size());
		memcpy(outPixels, _headlessCapture.data(), (size_t)count * sizeof(uint32_t));
		return count;
	}

	//ADR-0167: draw the system HUD alone (no game frame under it) into the
	//DLL-side buffer, at the caller-chosen size - unlike HeadlessCaptureFrame
	//there is no filter pipeline deciding the size, so the caller supplies one
	//(typically the base frame size) instead of reading it back. Returns false
	//on a degenerate size (zero, or over FrameCaptureMath::MaxCapturePixels)
	//without touching the emulator; the out parameters are always written.
	DllExport bool __stdcall HeadlessCaptureHud(uint32_t width, uint32_t height, uint32_t* outWidth, uint32_t* outHeight, uint32_t* outPixelCount)
	{
		uint64_t total = (uint64_t)width * (uint64_t)height;
		bool valid = width != 0 && height != 0 && total <= FrameCaptureMath::MaxCapturePixels;
		if(valid) {
			_emu->GetVideoRenderer()->CaptureSystemHud(width, height, _headlessHudCapture);
		} else {
			_headlessHudCapture.clear();
		}
		if(outWidth) { *outWidth = valid ? width : 0; }
		if(outHeight) { *outHeight = valid ? height : 0; }
		if(outPixelCount) { *outPixelCount = (uint32_t)_headlessHudCapture.size(); }
		return valid;
	}

	//Copy the pixels of the last HeadlessCaptureHud into the caller's buffer,
	//same contract as HeadlessReadCapturedPixels (0xAARRGGBB, row-major, never
	//more than maxPixels or the capture's own size).
	DllExport uint32_t __stdcall HeadlessReadCapturedHudPixels(uint32_t* outPixels, uint32_t maxPixels)
	{
		if(!outPixels || _headlessHudCapture.empty()) {
			return 0;
		}
		uint32_t count = std::min(maxPixels, (uint32_t)_headlessHudCapture.size());
		memcpy(outPixels, _headlessHudCapture.data(), (size_t)count * sizeof(uint32_t));
		return count;
	}

	//ADR-0167: gate MessageManager's OSD queue. With the OSD enabled (the
	//default), a ROM load enqueues a "game loaded" toast (Emulator.cpp) that
	//never ages out of a short headless run - UpdateHud only drops expired
	//messages on running frames, and the harness parks the emulator within a
	//few frames of load. That toast would make a HUD capture read non-blank
	//whether or not a message was queued, so the harness disables the OSD for
	//the load/run, then enables it for the instant it queues the one toast a
	//test wants to see. MessageManager::SetOptions also sets outputToStdout;
	//this keeps it false (the harness never enables stdout logging, and the
	//core's Log() lines would otherwise pollute the parsed capture output).
	DllExport void __stdcall HeadlessSetOsdEnabled(bool osdEnabled)
	{
		MessageManager::SetOptions(osdEnabled, false);
	}

	//ADR-0169 2026-09-08 update: does this run render through an HD pack that
	//replaces pixels? See LiveRecordFormat.h's HdPackActive comment - a
	//captured frame then shows the pack's art while the sprite/background layer
	//below still describes the original NES tiles, so the harness has to
	//publish the flag instead of letting a consumer score two panes that cannot
	//agree. Kept as its own export rather than another out-param on
	//HeadlessCaptureNesSpriteLayer: it is per-run, not per-capture. False for a
	//non-NES console.
	DllExport bool __stdcall HeadlessIsNesHdPackVideoActive()
	{
		NesConsole* nes = dynamic_cast<NesConsole*>(_emu->GetConsole().get());
		return nes ? nes->IsHdPackVideoActive() : false;
	}

	//ADR-0169: read a NES run's sprite layer straight off the console - OAM and
	//palette from their registered buffers (NesPpu.cpp), the mapper-resolved
	//pattern tables through NesConsole::DebugReadVram and the $2000 sprite-
	//control bits from NesPpu::GetState - WITHOUT constructing a Debugger.
	//GetMemoryState/GetPpuState (DebugApiWrapper) are not usable here: they
	//attach the debugger, and a run under a live debugger never parks on its
	//target frame (HeadlessInputEngine::ApplyFrame refuses to pause when
	//IsDebugging()).
	//
	//Lock() holds the emulation thread at an end-of-frame boundary (it spins in
	//WaitForLock with _threadPaused set) while this thread reads, so every byte
	//below is one consistent end-of-frame state. The run's own pause/stop
	//machinery (_paused, the input engine's pause latch) is never touched, so
	//the recording still parks on its target frame.
	//2026-09-08 ADR-0169 update ("capture every layer"): nametables is the
	//background's tile+attribute bytes, read the same instant as the sprite
	//layer so a viewer can multiplex sprites over the background the way the
	//PPU does. ppuState already carries everything else the background needs
	//(Control.BackgroundPatternAddr, Mask.BackgroundEnabled/BackgroundMask,
	//TmpVideoRamAddr - loopy "t", the base scroll at an end-of-frame boundary -
	//and ScrollX) - no new struct field required.
	DllExport bool __stdcall HeadlessCaptureNesSpriteLayer(uint8_t* oam, uint8_t* palette, uint8_t* chr, uint8_t* nametables, NesPpuState* ppuState,
		bool* outHasChrLatch, uint16_t* outChrLatchPageSize, uint8_t* outLeftFdBank, uint8_t* outLeftFeBank, uint8_t* outRightFdBank, uint8_t* outRightFeBank,
		uint8_t* outChrFull, uint32_t maxChrFullSize, uint32_t* outChrFullSize, uint32_t* outScanlineScroll, uint32_t* outScanlineChrBank)
	{
		_emu->Lock();

		NesConsole* nes = dynamic_cast<NesConsole*>(_emu->GetConsole().get());
		bool ready = nes != nullptr;
		if(ready) {
			if(ppuState) {
				nes->GetPpu()->GetState(*ppuState);
			}
			ConsoleMemoryInfo oamMem = _emu->GetMemory(MemoryType::NesSpriteRam);
			if(oam && oamMem.Memory) {
				memcpy(oam, oamMem.Memory, std::min(oamMem.Size, (uint32_t)0x100));
			}
			ConsoleMemoryInfo palMem = _emu->GetMemory(MemoryType::NesPaletteRam);
			if(palette && palMem.Memory) {
				memcpy(palette, palMem.Memory, std::min(palMem.Size, (uint32_t)0x20));
			}
			if(chr) {
				for(uint32_t i = 0; i < 0x2000; i++) {
					chr[i] = nes->DebugReadVram((uint16_t)i);
				}
			}
			if(nametables) {
				for(uint32_t i = 0; i < 0x1000; i++) {
					nametables[i] = nes->DebugReadVram((uint16_t)(0x2000 + i));
				}
			}
			//ADR-0169 2026-09-08 update ("mid-frame raster splits") - see
			//BaseNesPpu::GetScanlineScrollTrace's own comment.
			if(outScanlineScroll) {
				nes->GetPpu()->GetScanlineScrollTrace(outScanlineScroll);
			}

			//MMC2/MMC4 CHR-latch extension (BaseMapper::HasChrBankLatch,
			//ADR-0169 2026-09-08 update) - see LiveFrameRecorder.cpp's identical
			//block for why the plain chr[] above cannot be trusted for these.
			BaseMapper* mapper = nes->GetMapper();
			bool hasLatch = mapper && mapper->HasChrBankLatch();
			if(outHasChrLatch) {
				*outHasChrLatch = hasLatch;
			}
			if(hasLatch) {
				if(outChrLatchPageSize) {
					*outChrLatchPageSize = mapper->GetChrLatchPageSize();
				}
				if(outLeftFdBank && outLeftFeBank && outRightFdBank && outRightFeBank) {
					mapper->GetChrLatchBanks(*outLeftFdBank, *outLeftFeBank, *outRightFdBank, *outRightFeBank);
				}
			}

			//ADR-0169 2026-09-08 update ("mid-frame CHR bank splits") - see
			//LiveRecordFormat.h's ScanlineChrBank comment. Unlike the latch
			//case above, this covers ANY ROM-backed mapper's plain CHR bank
			//registers (Namco 108/mapper 206 has neither RAM nor a latch), so
			//outChrFull is populated whenever CHR-ROM exists at all, not just
			//when hasLatch is set.
			bool hasChrRom = mapper && mapper->GetChrRomSize() > 0;
			if(hasChrRom) {
				if(outScanlineChrBank) {
					nes->GetPpu()->GetScanlineChrBankTrace(outScanlineChrBank);
				}
				if(outChrFull && outChrFullSize) {
					uint32_t romSize = std::min(mapper->GetChrRomSize(), maxChrFullSize);
					memcpy(outChrFull, mapper->GetChrRomData(), romSize);
					*outChrFullSize = romSize;
				}
			} else if(outChrFullSize) {
				*outChrFullSize = 0;
			}
		}

		_emu->Unlock();
		return ready;
	}
}
