using System.Threading;

namespace Mesen.Logic
{
	//Exclusion gate shared by the two UI/Services flows that rewrite the same
	//installed pack folder (CommunityPackInstallService): the ROM-load
	//auto-install and the user's explicit Restore. At most one may run at a
	//time; an install/Restore that finds the gate already held refuses instead
	//of queuing, and the refused caller must NOT release the holder's token (a
	//Restore refused while an auto-install is in flight leaves the install free
	//to finish). Host-free (BCL only) so UI.Tests can pin the mutual exclusion
	//that keeps the two from ever rewriting mep/ concurrently; the host-aware
	//service owns a single static instance and releases it in a finally.
	public sealed class CommunityPackInstallGate
	{
		private int _held; // 0 = free, 1 = held; Interlocked so check-and-set is atomic across threads

		//Acquires the gate when free. False means another install/Restore is in
		//flight - the caller must back off and, on the false path, must not call
		//Exit (that would release a token it does not hold).
		public bool TryEnter()
		{
			return Interlocked.CompareExchange(ref _held, 1, 0) == 0;
		}

		//Releases the gate. Only the caller that received true from TryEnter may
		//call this, typically from a finally so a throwing install still frees
		//the gate for the next ROM load or Restore.
		public void Exit()
		{
			Interlocked.Exchange(ref _held, 0);
		}

		public bool IsHeld
		{
			get { return Volatile.Read(ref _held) != 0; }
		}
	}
}
