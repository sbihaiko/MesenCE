using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Avalonia.Threading;
using Mesen.Controls;
using Xunit;

namespace Mesen.HeadlessTests;

//I.2, plan subsection 2B: "the live highlight in ControllerConfigWindow".
//The window polls InputApi.GetPressedKeys() (native) on a 60 Hz timer and sets
//KeyBindingButton.Highlighted; what happens after that is pure XAML, and is
//what this covers: Highlighted must reach the "highlighted" style class AND
//that class must actually restyle the button through KeyBindingButton.axaml.
//The polling half needs the native core plus a physically pressed key - see
//the report/AGENTS.md; it is not simulated here.
public class ControllerHighlightTests
{
	private static readonly Color HighlightBackground = Color.Parse("#3388CC");
	private static readonly Color HighlightBorder = Color.Parse("#55AAEE");

	private static (Window, KeyBindingButton) ShowButton()
	{
		//A bare KeyBindingButton, not the whole ControllerConfigWindow: realizing
		//a mapping tab constructs buttons whose KeyBinding setter calls
		//InputApi.GetKeyName() (native).
		KeyBindingButton button = new();
		Window window = new() { Content = button };
		window.Show();
		return (window, button);
	}

	[AvaloniaFact]
	public void Pressed_binding_lights_the_button_up()
	{
		(Window window, KeyBindingButton button) = ShowButton();

		Assert.DoesNotContain("highlighted", button.Classes);
		ISolidColorBrush? idle = button.Background as ISolidColorBrush;

		button.Highlighted = true;
		Dispatcher.UIThread.RunJobs();

		Assert.Contains("highlighted", button.Classes);
		ISolidColorBrush background = Assert.IsAssignableFrom<ISolidColorBrush>(button.Background);
		ISolidColorBrush border = Assert.IsAssignableFrom<ISolidColorBrush>(button.BorderBrush);
		Assert.Equal(HighlightBackground, background.Color);
		Assert.Equal(HighlightBorder, border.Color);
		Assert.NotEqual(idle?.Color, background.Color);
	}

	[AvaloniaFact]
	public void Releasing_the_key_restores_the_normal_look()
	{
		(Window window, KeyBindingButton button) = ShowButton();
		button.Highlighted = true;
		Dispatcher.UIThread.RunJobs();

		button.Highlighted = false;
		Dispatcher.UIThread.RunJobs();

		Assert.DoesNotContain("highlighted", button.Classes);
		if(button.Background is ISolidColorBrush background) {
			Assert.NotEqual(HighlightBackground, background.Color);
		}
	}
}
