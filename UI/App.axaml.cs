using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Controls.Platform;
using Avalonia.Markup.Xaml;
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
					//app via an Apple 'open documents' event that Avalonia surfaces as
					//IActivatableLifetime.Activated(UrlsOpenedEventArgs). The named-pipe
					//SingleInstance path is never used in this scenario, so we subscribe
					//here and route each file:// URI through the same LoadRomHelper path
					//used by drag-and-drop and the pipe handler.
					if(OperatingSystem.IsMacOS() && ApplicationLifetime is IActivatableLifetime activatable) {
						activatable.Activated += OnActivated;
					}
				}
			}
			base.OnFrameworkInitializationCompleted();
		}

		//Issue #149: handles Apple 'open documents' events (Finder / `open -a`)
		//delivered to an already-running instance on macOS. Avalonia surfaces
		//these as UrlsOpenedEventArgs via IActivatableLifetime.Activated.
		//Each file:// URI is routed through LoadRomHelper.LoadFile - the same
		//path used by drag-and-drop and the SingleInstance named-pipe handler.
		private void OnActivated(object? sender, ActivatedEventArgs e)
		{
			if(e is not UrlsOpenedEventArgs urlsEvent) {
				return;
			}
			foreach(string url in urlsEvent.Urls) {
				if(Uri.TryCreate(url, UriKind.Absolute, out Uri? uri) && uri.IsFile) {
					string localPath = uri.LocalPath;
					Dispatcher.UIThread.Post(() => LoadRomHelper.LoadFile(localPath));
				}
			}
		}
	}
}
