#include "pch.h"
#include <algorithm>
#include "Debugger/DisassemblyInfo.h"
#include "Debugger/Debugger.h"
#include "Debugger/MemoryDumper.h"
#include "Debugger/DebugUtilities.h"
#include "Utilities/HexUtilities.h"
#include "Utilities/FastString.h"
#include "Gameboy/Gameboy.h"
#include "Gameboy/GbTypes.h"
#include "Gameboy/Debugger/GameboyDisUtils.h"
#include "NES/NesTypes.h"
#include "NES/Debugger/NesDisUtils.h"
#include "SMS/SmsConsole.h"
#include "SMS/SmsTypes.h"
#include "SMS/Debugger/SmsDisUtils.h"
#include "GBA/GbaConsole.h"
#include "GBA/GbaTypes.h"
#include "GBA/Debugger/GbaDisUtils.h"
#include "Shared/EmuSettings.h"

DisassemblyInfo::DisassemblyInfo()
{
}

DisassemblyInfo::DisassemblyInfo(uint32_t cpuAddress, uint8_t cpuFlags, CpuType cpuType, MemoryType memType, MemoryDumper* memoryDumper)
{
	Initialize(cpuAddress, cpuFlags, cpuType, memType, memoryDumper);
}

void DisassemblyInfo::Initialize(uint32_t cpuAddress, uint8_t cpuFlags, CpuType cpuType, MemoryType memType, MemoryDumper* memoryDumper)
{
	_cpuType = cpuType;
	_flags = cpuFlags;

	_byteCode[0] = memoryDumper->GetMemoryValue(memType, cpuAddress);

	_opSize = GetOpSize(_byteCode[0], _flags, _cpuType, cpuAddress, memType, memoryDumper);

	for(int i = 1; i < _opSize && i < 8; i++) {
		_byteCode[i] = memoryDumper->GetMemoryValue(memType, cpuAddress + i);
	}

	_initialized = true;
}

bool DisassemblyInfo::IsInitialized()
{
	return _initialized;
}

bool DisassemblyInfo::IsValid(uint8_t cpuFlags)
{
	return _flags == cpuFlags;
}

void DisassemblyInfo::Reset()
{
	_initialized = false;
}

void DisassemblyInfo::GetDisassembly(string& out, uint32_t memoryAddr, LabelManager* labelManager, EmuSettings* settings)
{
	switch(_cpuType) {
		case CpuType::Gameboy: GameboyDisUtils::GetDisassembly(*this, out, memoryAddr, labelManager, settings); break;
		case CpuType::Nes: NesDisUtils::GetDisassembly(*this, out, memoryAddr, labelManager, settings); break;
		case CpuType::Sms: SmsDisUtils::GetDisassembly(*this, out, memoryAddr, labelManager, settings); break;
		case CpuType::Gba: GbaDisUtils::GetDisassembly(*this, out, memoryAddr, labelManager, settings); break;

		default:
			throw std::runtime_error("GetDisassembly - Unsupported CPU type");
	}
}

EffectiveAddressInfo DisassemblyInfo::GetEffectiveAddress(Debugger* debugger, void* cpuState, CpuType cpuType)
{
	switch(_cpuType) {
		case CpuType::Gameboy:
			return GameboyDisUtils::GetEffectiveAddress(*this, (Gameboy*)debugger->GetConsole(), *(GbCpuState*)cpuState);

		case CpuType::Nes: return NesDisUtils::GetEffectiveAddress(*this, *(NesCpuState*)cpuState, debugger->GetMemoryDumper());
		case CpuType::Sms: return SmsDisUtils::GetEffectiveAddress(*this, (SmsConsole*)debugger->GetConsole(), *(SmsCpuState*)cpuState);
		case CpuType::Gba: return GbaDisUtils::GetEffectiveAddress(*this, (GbaConsole*)debugger->GetConsole(), *(GbaCpuState*)cpuState);
	}

	throw std::runtime_error("GetEffectiveAddress - Unsupported CPU type");
}

CpuType DisassemblyInfo::GetCpuType()
{
	return _cpuType;
}

uint8_t DisassemblyInfo::GetOpCode()
{
	return _byteCode[0];
}

template<CpuType type>
uint32_t DisassemblyInfo::GetFullOpCode()
{
	switch(type) {
		default: return _byteCode[0];
		case CpuType::Gba: return _byteCode[0] | (_byteCode[1] << 8) | (_opSize == 4 ? ((_byteCode[2] << 16) | (_byteCode[3] << 24)) : 0);
	}
}

uint8_t DisassemblyInfo::GetOpSize()
{
	return _opSize;
}

uint8_t DisassemblyInfo::GetFlags()
{
	return _flags;
}

uint8_t* DisassemblyInfo::GetByteCode()
{
	return _byteCode;
}

void DisassemblyInfo::GetByteCode(uint8_t copyBuffer[8])
{
	memcpy(copyBuffer, _byteCode, _opSize);
}

void DisassemblyInfo::GetByteCode(string& out, bool lowerCase)
{
	FastString str(lowerCase);
	if(DebugUtilities::GetByteCodeFormat(_cpuType) == ByteCodeFormat::HexValue) {
		for(int i = _opSize - 1; i >= 0; i--) {
			str.WriteAll(HexUtilities::ToHex(_byteCode[i]));
		}
	} else {
		for(int i = 0; i < _opSize; i++) {
			str.WriteAll('$', HexUtilities::ToHex(_byteCode[i]));
			if(i < _opSize - 1) {
				str.Write(' ');
			}
		}
	}
	out += str.ToString();
}

uint8_t DisassemblyInfo::GetOpSize(uint32_t opCode, uint8_t flags, CpuType type, uint32_t cpuAddress, MemoryType memType, MemoryDumper* memoryDumper)
{
	switch(type) {
		case CpuType::Gameboy: return GameboyDisUtils::GetOpSize(opCode);
		case CpuType::Nes: return NesDisUtils::GetOpSize(opCode);
		case CpuType::Sms: return SmsDisUtils::GetOpSize(opCode, cpuAddress, memType, memoryDumper);
		case CpuType::Gba: return GbaDisUtils::GetOpSize(opCode, flags);
	}

	throw std::runtime_error("GetOpSize - Unsupported CPU type");
}

bool DisassemblyInfo::IsJumpToSub()
{
	switch(_cpuType) {
		case CpuType::Gameboy: return GameboyDisUtils::IsJumpToSub(GetOpCode());
		case CpuType::Nes: return NesDisUtils::IsJumpToSub(GetOpCode());
		case CpuType::Sms: return SmsDisUtils::IsJumpToSub(GetOpCode());
		case CpuType::Gba: return GbaDisUtils::IsJumpToSub(GetFullOpCode<CpuType::Gba>(), _flags);
	}

	throw std::runtime_error("IsJumpToSub - Unsupported CPU type");
}

bool DisassemblyInfo::IsReturnInstruction()
{
	switch(_cpuType) {
		case CpuType::Gameboy: return GameboyDisUtils::IsReturnInstruction(GetOpCode());
		case CpuType::Nes: return NesDisUtils::IsReturnInstruction(GetOpCode());
		case CpuType::Sms: return SmsDisUtils::IsReturnInstruction(_byteCode[0] | (_byteCode[1] << 8));
		case CpuType::Gba: return GbaDisUtils::IsReturnInstruction(GetFullOpCode<CpuType::Gba>(), _flags);
	}

	throw std::runtime_error("IsReturnInstruction - Unsupported CPU type");
}

bool DisassemblyInfo::CanDisassembleNextOp()
{
	if(IsUnconditionalJump()) {
		return false;
	}

	return true;
}

bool DisassemblyInfo::IsUnconditionalJump()
{
	switch(_cpuType) {
		case CpuType::Gameboy: return GameboyDisUtils::IsUnconditionalJump(GetOpCode());
		case CpuType::Nes: return NesDisUtils::IsUnconditionalJump(GetOpCode());
		case CpuType::Sms: return SmsDisUtils::IsUnconditionalJump(GetOpCode());
		case CpuType::Gba: return GbaDisUtils::IsUnconditionalJump(GetFullOpCode<CpuType::Gba>(), _flags);
	}

	throw std::runtime_error("IsUnconditionalJump - Unsupported CPU type");
}

bool DisassemblyInfo::IsJump()
{
	if(IsUnconditionalJump()) {
		return true;
	}

	//Check for conditional jumps
	switch(_cpuType) {
		case CpuType::Gameboy: return GameboyDisUtils::IsConditionalJump(GetOpCode());
		case CpuType::Nes: return NesDisUtils::IsConditionalJump(GetOpCode());
		case CpuType::Sms: return SmsDisUtils::IsConditionalJump(GetOpCode());
		case CpuType::Gba: return GbaDisUtils::IsConditionalJump(GetFullOpCode<CpuType::Gba>(), _flags);
	}

	throw std::runtime_error("IsJump - Unsupported CPU type");
}

void DisassemblyInfo::UpdateCpuFlags(uint8_t& cpuFlags)
{
}

uint32_t DisassemblyInfo::GetMemoryValue(EffectiveAddressInfo effectiveAddress, MemoryDumper* memoryDumper, MemoryType memType)
{
	MemoryType effectiveMemType = effectiveAddress.Type == MemoryType::None ? memType : effectiveAddress.Type;
	switch(effectiveAddress.ValueSize) {
		default:
		case 1: return memoryDumper->GetMemoryValue(effectiveMemType, effectiveAddress.Address);
		case 2: return memoryDumper->GetMemoryValue16(effectiveMemType, effectiveAddress.Address);
		case 4: return memoryDumper->GetMemoryValue32(effectiveMemType, effectiveAddress.Address);
	}
}
