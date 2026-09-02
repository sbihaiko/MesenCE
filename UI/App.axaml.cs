using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Controls.Platform;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using Avalonia.Styling;
using Avalonia.Threading;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Utilities;
using Mesen.ViewModels;
using Mesen.Windows;
using System;
using System.IO;
using System.Reflection;

namespace Mesen
{
	public class App : Application
	{
		public static bool ShowConfigWindow { get; set; }

		public override void Initialize()
		{
			if(Design.IsDesignMode || ShowConfigWindow) {
				RequestedThemeVariant = ThemeVariant.Light;
			} else {
				RequestedThemeVariant = ConfigManager.Config.Preferences.Theme == MesenTheme.Dark ? ThemeVariant.Dark : ThemeVariant.Light;
			}

			Dispatcher.UIThread.UnhandledException += (s, e) => {
				MesenMsgBox.ShowException(e.Exception);
				e.Handled = true;
			};

#if DEBUG
			this.AttachDeveloperTools();
#endif
			AvaloniaXamlLoader.Load(this);
			ResourceHelper.LoadResources();
		}

		public override void OnFrameworkInitializationCompleted()
		{
			if(ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop) {
				if(ShowConfigWindow) {
					new PreferencesConfig().InitializeFontDefaults();
					desktop.MainWindow = new SetupWizardWindow();
				} else {
					//Test if the core can be loaded, and display an error message popup if not
					try {
						EmuApi.TestDll();
					} catch(Exception ex) {
						bool sdlMissing = ex.Message.Contains("SDL2", StringComparison.InvariantCultureIgnoreCase);

						string errorMessage;
						if(sdlMissing) {
							errorMessage = ResourceHelper.GetMessage("UnableToStartMissingSdl", ex.Message);
						} else {
							errorMessage = ResourceHelper.GetMessage("UnableToStartMissingDependencies", ex.Message + Environment.NewLine + ex.StackTrace);
						}
						MessageBox.Show(null, errorMessage, "MesenCE", MessageBoxButtons.OK, MessageBoxIcon.Error, out MessageBox msgbox);
						desktop.MainWindow = msgbox;
						base.OnFrameworkInitializationCompleted();
						return;
					}

					try {
						desktop.MainWindow = new MainWindow();
					} catch {
						//Something broke when trying to load the main window, the settings file might be invalid/broken, try to reset them
						Configuration.BackupSettings(ConfigManager.ConfigFile);
						ConfigManager.ResetSettings(false);
						desktop.MainWindow = new MainWindow();
					}

					//Issue #149: on macOS the OS delivers files to an already-running
					//app via an Apple 'open documents' event (ActivationKind.File). In
					//Avalonia 12 the event is surfaced by the IActivatableLifetime FEATURE
					//(Application.Current.TryGetFeature), NOT by the application-lifetime
					//object - `ApplicationLifetime is IActivatableLifetime` is always false
					//(ClassicDesktopStyleApplicationLifetime does not implement it), so the
					//original fix was a silent no-op. Route each file through the same
					//LoadRomHelper path used by drag-and-drop and the pipe handler.
					if(OperatingSystem.IsMacOS() && this.TryGetFeature<IActivatableLifetime>() is { } activatable) {
						activatable.Activated += OnActivated;
					}
				}
			}
			base.OnFrameworkInitializationCompleted();
		}

		//Issue #149: handles Apple 'open documents' events (Finder / `open -a`)
		//delivered to an already-running instance on macOS. Avalonia surfaces
		//these as FileActivatedEventArgs via IActivatableLifetime.Activated.
		//Each file is routed through LoadRomHelper.LoadFile - the same
		//path used by drag-and-drop and the SingleInstance named-pipe handler.
		private void OnActivated(object? sender, ActivatedEventArgs e)
		{
			if(e is not FileActivatedEventArgs fileArgs) {
				return;
			}
			foreach(IStorageItem file in fileArgs.Files) {
				if(file.TryGetLocalPath() is string localPath) {
					Dispatcher.UIThread.Post(() => LoadRomHelper.LoadFile(localPath));
				}
			}
		}
	}
}
