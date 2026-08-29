using Avalonia.Controls;
using Mesen.Config;
using Mesen.Utilities;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Mesen.ViewModels
{
	public partial class InputConfigViewModel : DisposableViewModel
	{
		[ObservableProperty] public partial InputConfig Config { get; set; }
		[ObservableProperty] public partial InputConfig OriginalConfig { get; set; }

		//Host input tester (PRD slice I.1): the Test tab polls connected pads
		//only while the tab is visible (see GamepadTesterViewModel).
		public GamepadTesterViewModel GamepadTester { get; } = new();

		public InputConfigViewModel()
		{
			Config = ConfigManager.Config.Input;
			OriginalConfig = Config.Clone();

			if(Design.IsDesignMode) {
				return;
			}

			AddDisposable(ReactiveHelper.RegisterRecursiveObserver(Config, (s, e) => { Config.ApplyConfig(); }));
			AddDisposable(GamepadTester);
		}
	}
}
