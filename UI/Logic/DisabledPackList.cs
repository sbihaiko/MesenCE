using System;
using System.Collections.Generic;

namespace Mesen.Logic
{
	//Host-free counterpart to EnhancementPackConfig.SetPackEnabled's list
	//mutation (Fase 2, docs/roadmap/plano-testes-unitarios.md). Keeps
	//DisabledPacks free of duplicates (case-insensitive) regardless of how
	//many times a container is toggled: any existing entry (any casing) is
	//removed first, then re-added only when the pack is being disabled. Kept
	//free of Avalonia/EmuApi so it can be dual-compiled into UI.Tests (see
	//UI.Tests/UI.Tests.csproj) and unit tested without the native MesenCore
	//library. The caller (EnhancementPackConfig.SetPackEnabled) still owns
	//the EmuApi.SetMepPackEnabled native call - this only mutates the list.
	public static class DisabledPackList
	{
		public static void Set(List<string> disabledPacks, string container, bool enabled)
		{
			disabledPacks.RemoveAll(x => string.Equals(x, container, StringComparison.OrdinalIgnoreCase));
			if(!enabled) {
				disabledPacks.Add(container);
			}
		}
	}
}
