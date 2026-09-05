#include "pch.h"
#include "Shared/HeadlessInputProvider.h"
#include "Shared/BaseControlDevice.h"
#include "Shared/Emulator.h"
#include "Shared/MessageManager.h"
#include "Shared/NotificationManager.h"

namespace
{
	//The live control device, seen through the engine's narrow interface.
	//Stack-allocated once per frame; holds no state of its own.
	class ControlDeviceTarget : public IHeadlessInputTarget
	{
	private:
		BaseControlDevice* _device = nullptr;

	public:
		ControlDeviceTarget(BaseControlDevice* device) { _device = device; }

		uint8_t GetPort() override { return _device->GetPort(); }

		vector<HeadlessButtonName> GetButtonNames() override
		{
			vector<HeadlessButtonName> names;
			for(DeviceButtonName& button : _device->GetKeyNameAssociations()) {
				names.push_back({ button.Name, button.ButtonId, button.IsNumeric });
			}
			return names;
		}

		void PressButton(int buttonId) override { _device->SetBitValue((uint8_t)buttonId, true); }
	};
}

HeadlessInputProvider::HeadlessInputProvider(Emulator* emu) : _engine(this)
{
	_emu = emu;
}

void HeadlessInputProvider::Init()
{
	_emu->GetNotificationManager()->RegisterNotificationListener(shared_from_this());
	_emu->RegisterInputProvider(this);
}

bool HeadlessInputProvider::LoadScript(const string& text, double frameRate, string& error)
{
	return _engine.LoadScript(text, frameRate, error);
}

void HeadlessInputProvider::SetPauseFrame(uint32_t frame)
{
	_engine.SetPauseFrame(frame);
}

uint32_t HeadlessInputProvider::GetScriptFrameCount()
{
	return _engine.GetScriptFrameCount();
}

bool HeadlessInputProvider::SetInput(BaseControlDevice* device)
{
	ControlDeviceTarget target(device);
	return _engine.ApplyFrame(target);
}

void HeadlessInputProvider::ProcessNotification(ConsoleNotificationType type, void* parameter)
{
	if(type == ConsoleNotificationType::GameLoaded) {
		_engine.OnGameLoaded();
	}
}

uint32_t HeadlessInputProvider::GetFrameCount()
{
	return _emu->GetFrameCount();
}

bool HeadlessInputProvider::IsDebugging()
{
	return _emu->IsDebugging();
}

void HeadlessInputProvider::Pause()
{
	_emu->Pause();
}

void HeadlessInputProvider::RegisterInputProvider()
{
	_emu->RegisterInputProvider(this);
}

void HeadlessInputProvider::Log(const string& message)
{
	MessageManager::Log(message);
}
