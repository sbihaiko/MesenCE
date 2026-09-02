using Avalonia.Controls;
using Avalonia.Rendering;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Windows;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Mesen.Utilities
{
	public class MesenMsgBox
	{
		public static Task ShowException(Exception ex)
		{
			try {
				//Record the full exception (type + message + inner exceptions + stack) in
				//mesen.log so handled UI exceptions are never only visible in the popup.
				//The popup itself keeps showing message + stack for the user.
				EmuApi.WriteLogEntry("[UI] " + ex.ToString());
			} catch {
				//Logging must never prevent the popup from being shown
			}
			return MesenMsgBox.Show(null, "UnexpectedError", MessageBoxButtons.OK, MessageBoxIcon.Error, ex.Message + Environment.NewLine + ex.StackTrace);
		}

		public static Task<DialogResult> Show(Window? parent, string text, MessageBoxButtons buttons, MessageBoxIcon icon, params string[] args)
		{
			Window? wnd = parent as Window;
			if(parent != null && wnd == null) {
				throw new Exception("Invalid parent window");
			}

			string resourceText = ResourceHelper.GetMessage(text, args);

			if(resourceText.StartsWith("[[")) {
				if(args != null && args.Length > 0) {
					return MessageBox.Show(wnd, string.Format("Critical error (" + text + ") {0}", args), "MesenCE", buttons, icon);
				} else {
					return MessageBox.Show(wnd, string.Format("Critical error (" + text + ")"), "MesenCE", buttons, icon);
				}
			} else {
				return MessageBox.Show(wnd, ResourceHelper.GetMessage(text, args), "MesenCE", buttons, icon);
			}
		}
	}
}
