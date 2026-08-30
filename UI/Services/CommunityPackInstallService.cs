using Avalonia.Threading;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Utilities;
using Mesen.Windows;
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Mesen.Services
{
	//ROM-load entry point of F6.4b-2 (ADR-0138 §4/§37/§38): the thin orchestrator that ties
	//CommunityPackCatalogFetcher (network) and CommunityPackInstallCoordinator (gates + interop)
	//together once per loaded ROM, and surfaces the outcome through the emulator's own message
	//API. Runs off the UI thread; only the first-run consent dialog is marshalled onto it.
	//Fail-soft by contract: an auto-install must never break a game load, so every failure path
	//degrades to a one-line message (or silence for the routine "nothing to do" cases).
	public static class CommunityPackInstallService
	{
		private const string MessageTitle = "Enhancement Packs";
		private static int _running = 0;
		//§51 per-session idempotency key: one attempt per ROM sha1 per process, decided before any
		//network call; the .mep-install.json stamp (§43) remains the cross-session gate.
		private static readonly HashSet<string> _attemptedRomSha1 = new(StringComparer.OrdinalIgnoreCase);
		//P.6: community 👍 counts from the last catalog fetch (MEI `votes`), keyed
		//by pack_id - the Player picker sorts by them (§5). Read-only for the
		//UI; local-only packs have no entry and sort by name (votes 0).
		private static readonly Dictionary<string, int> _catalogVotesByPackId = new(StringComparer.OrdinalIgnoreCase);

		public static int GetVotes(string packId)
		{
			return _catalogVotesByPackId.TryGetValue(packId, out int votes) ? votes : 0;
		}

		//Called from MainWindow.OnNotification(GameLoaded); power cycles are not new loads
		//(a pack we just installed is applied through exactly such a power cycle).
		public static void OnGameLoaded(bool isPowerCycle)
		{
			//DIAGNOSTIC (temporary, issue #142/community-pack investigation):
			//trace every early-return so the mesen.log always shows why the
			//auto-install did or didn't proceed, instead of pure silence.
			EmuApi.WriteLogEntry("[CommunityPack] OnGameLoaded: isPowerCycle=" + isPowerCycle +
				" AutoInstallCommunityPacks=" + ConfigManager.Config.EnhancementPacks.AutoInstallCommunityPacks);
			if(isPowerCycle || !ConfigManager.Config.EnhancementPacks.AutoInstallCommunityPacks) {
				EmuApi.WriteLogEntry("[CommunityPack] skipped: isPowerCycle or AutoInstallCommunityPacks off");
				return;
			}
			if(Interlocked.CompareExchange(ref _running, 1, 0) != 0) {
				EmuApi.WriteLogEntry("[CommunityPack] skipped: a previous load's install is still in flight");
				return; //a previous load's install is still in flight
			}
			_ = Task.Run(RunAsync);
		}

		private static async Task RunAsync()
		{
			try {
				//§38: the very first automatic download is gated behind an explicit Yes/No prompt,
				//before the catalog itself is contacted (that GET is already a network access).
				bool allowed = await Dispatcher.UIThread.InvokeAsync(EnhancementPacksWindow.EnsureCommunityPackAutoInstallConsent);
				EmuApi.WriteLogEntry("[CommunityPack] consent check: allowed=" + allowed +
					" ConsentGiven=" + ConfigManager.Config.EnhancementPacks.CommunityPackAutoInstallConsentGiven);
				if(!allowed) {
					EmuApi.WriteLogEntry("[CommunityPack] skipped: consent not given / dialog pending");
					return;
				}
				string romSha1 = EmuApi.GetMepRomSha1();
				EmuApi.WriteLogEntry("[CommunityPack] romSha1=" + romSha1);
				lock(_attemptedRomSha1) {
					if(string.IsNullOrWhiteSpace(romSha1) || !_attemptedRomSha1.Add(romSha1)) {
						EmuApi.WriteLogEntry("[CommunityPack] skipped: no hash, or already attempted this session");
						return; //no hash, or already attempted this session
					}
				}

				CommunityPackFetchResult? fetched = await CommunityPackCatalogFetcher.FetchMatchingPackAsync();
				if(fetched == null) {
					EmuApi.WriteLogEntry("[CommunityPack] no match/fetch result (see [CommunityPackFetch] lines above for the stage that returned null)");
					return; //no catalog, no match, host not allowed or hash mismatch - all silent (§41/§42)
				}
				EmuApi.WriteLogEntry("[CommunityPack] fetched entry: pack_id=" + fetched.Entry.PackId + " primaryPath=" + fetched.PrimaryPackPath);

				//P.6 §5: remember the matched entry's community 👍 count so the
				//Player picker sorts its competing packs by it (votes 0 when the
				//entry carries none).
				if(!string.IsNullOrWhiteSpace(fetched.Entry.PackId) && fetched.Entry.Votes is int votes) {
					lock(_catalogVotesByPackId) {
						_catalogVotesByPackId[fetched.Entry.PackId] = votes;
					}
				}

				CommunityPackInstallOutcome outcome = CommunityPackInstallCoordinator.Install(
					fetched.Entry, fetched.PrimaryPackPath, fetched.ResolvedDepPaths);
				EmuApi.WriteLogEntry("[CommunityPack] Install() outcome: Status=" + outcome.Status +
					" ContainerName=" + outcome.ContainerName + " Message=" + outcome.Message);
				Surface(outcome);
			} catch(Exception ex) {
				EmuApi.WriteLogEntry("[CommunityPack] RunAsync threw: " + ex);
				Notify("Community pack auto-install failed: " + ex.Message);
			} finally {
				Interlocked.Exchange(ref _running, 0);
			}
		}

		private static void Surface(CommunityPackInstallOutcome outcome)
		{
			switch(outcome.Status) {
				case CommunityPackInstallStatus.Installed:
					Notify("Community pack '" + outcome.ContainerName + "' installed - power cycle to apply");
					foreach(string withheld in outcome.Withheld) {
						//§6: a patch whose dependency is missing is withheld, never applied blindly.
						Notify("Patch withheld (missing dependency): " + withheld);
					}
					NotifyPendingDeps(outcome.PendingDeps);
					break;

				case CommunityPackInstallStatus.Failed:
					Notify("Community pack install failed: " + outcome.Message);
					break;

				case CommunityPackInstallStatus.Skipped:
				case CommunityPackInstallStatus.NeedsConsent:
					//Routine: up to date, disabled by user, consent declined - nothing to say.
					break;
			}
		}

		//MEI-v1.md §2.3 user_supplied deps: tell the user what to drop where, with the
		//declared licence (or "not declared") so they can judge the source themselves.
		private static void NotifyPendingDeps(IReadOnlyList<CommunityPackDepPrompt> pending)
		{
			foreach(CommunityPackDepPrompt dep in pending) {
				string license = string.IsNullOrWhiteSpace(dep.License) ? "not declared" : dep.License;
				string hints = string.IsNullOrWhiteSpace(dep.Hints) ? dep.DepId : dep.Hints;
				Notify("Missing file '" + hints + "' (licence: " + license + ") - drop it into " + dep.DropFolder + " and power cycle");
			}
		}

		private static void Notify(string message)
		{
			Dispatcher.UIThread.Post(() => DisplayMessageHelper.DisplayMessage(MessageTitle, message));
		}
	}
}
