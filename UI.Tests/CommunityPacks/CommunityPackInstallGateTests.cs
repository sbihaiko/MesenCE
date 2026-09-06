using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	//Guard B of the 2026-09-06 review (36ecf152): Restore refuses while an
	//auto-install runs. The exclusion lives in host-free
	//CommunityPackInstallGate (UI/Logic); CommunityPackInstallService owns one
	//instance and releases it in a finally. These pin the two properties the
	//service relies on: at most one holder at a time, and a refused caller does
	//not release a token it does not hold (so a Restore refused while an install
	//is in flight leaves the install free to finish).
	public class CommunityPackInstallGateTests
	{
		[Fact]
		public void TryEnter_WhenFree_AcquiresAndMarksHeld()
		{
			CommunityPackInstallGate gate = new();

			Assert.False(gate.IsHeld);
			Assert.True(gate.TryEnter());
			Assert.True(gate.IsHeld);
		}

		[Fact]
		public void TryEnter_WhileHeld_RefusesAndLeavesTheHolderUntouched()
		{
			CommunityPackInstallGate gate = new();
			Assert.True(gate.TryEnter());

			//A second install/Restore while the first is in flight is refused...
			Assert.False(gate.TryEnter());

			//...and the refused caller must not have released the holder's token
			//(RestoreInstalledPack returns on the false path before its finally).
			Assert.True(gate.IsHeld);

			//The original holder finishing (Exit in its finally) is what frees it.
			gate.Exit();
			Assert.False(gate.IsHeld);
		}

		[Fact]
		public void Exit_ThenTryEnter_AllowsTheNextOperation()
		{
			CommunityPackInstallGate gate = new();
			Assert.True(gate.TryEnter());
			gate.Exit();

			Assert.True(gate.TryEnter());
			Assert.True(gate.IsHeld);
			gate.Exit();
		}

		[Fact]
		public void RefusedCallerBackingOff_ThenHolderExit_ThenFreshTryEnter_IsTheFullCycle()
		{
			//The exact shape RestoreInstalledPack follows: refused restore backs
			//off (no Exit), the in-flight install finishes (Exit), the next
			//operation proceeds.
			CommunityPackInstallGate gate = new();
			Assert.True(gate.TryEnter());
			Assert.False(gate.TryEnter()); // Restore refused during install

			gate.Exit(); // install completes
			Assert.True(gate.TryEnter()); // a later Restore/load proceeds
			gate.Exit();
		}
	}
}
