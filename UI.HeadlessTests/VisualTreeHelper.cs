using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.VisualTree;
using Xunit.Sdk;

namespace Mesen.HeadlessTests;

internal static class VisualTreeHelper
{
	//Named elements inside a DataTemplate live in the template's own name scope,
	//so Window.GetControl<T>(name) cannot see them - walk the realized visual
	//tree instead, which is also what "is it actually on screen" means here.
	public static T FindNamed<T>(this Visual root, string name) where T : Control
	{
		T? found = root.GetVisualDescendants().OfType<T>().FirstOrDefault(c => c.Name == name);
		if(found == null) {
			throw new XunitException($"No {typeof(T).Name} named '{name}' in the visual tree of {root.GetType().Name}.");
		}
		return found;
	}

	public static IReadOnlyList<T> FindAll<T>(this Visual root) where T : Visual
	{
		return root.GetVisualDescendants().OfType<T>().ToList();
	}

	//IsVisible is a local flag; a control inside a collapsed parent is not on
	//screen even with IsVisible=true. IsEffectivelyVisible is the real answer.
	public static bool IsOnScreen(this Visual visual) => visual.IsEffectivelyVisible;
}
