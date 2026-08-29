#pragma once

#include "pch.h"

//Cross-platform helpers for launching a detached helper process (ADR-0135
//point 7: the extract-audio tool runs as its own process, not in-process).
class ProcessUtilities
{
public:
	//Launches `program` with `args` detached: the caller does not wait for it
	//and is not blocked; the child keeps running after the parent exits.
	//SIGCHLD is set to SIG_IGN so the child is reaped automatically. Returns
	//true when the process was spawned.
	static bool StartDetached(const string& program, const vector<string>& args);

	//Full path of the folder containing the current process's executable,
	//with a trailing directory separator.
	static string GetExecutableFolder();
};
