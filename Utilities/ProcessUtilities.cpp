#include "ProcessUtilities.h"

#include <vector>

#if defined(__APPLE__)
	#include <mach-o/dyld.h>
#endif

#if defined(_WIN32)
	#include <windows.h>
#else
	#include <unistd.h>
	#include <csignal>
	#include <cstdlib>
#endif

bool ProcessUtilities::StartDetached(const string& program, const vector<string>& args)
{
#if defined(_WIN32)
	//Build a command line: quote every argument, doubling any embedded quotes.
	std::string cmdline = "\"" + program + "\"";
	for(const string& arg : args) {
		cmdline += " \"";
		for(char c : arg) {
			if(c == '"') {
				cmdline += "\\\"";
			} else {
				cmdline += c;
			}
		}
		cmdline += "\"";
	}

	std::wstring wideCmd = std::wstring(cmdline.begin(), cmdline.end());
	STARTUPINFOW si = {};
	si.cb = sizeof(si);
	PROCESS_INFORMATION pi = {};
	bool created = CreateProcessW(nullptr, wideCmd.data(), nullptr, nullptr, FALSE,
		CREATE_NO_WINDOW | DETACHED_PROCESS, nullptr, nullptr, &si, &pi);
	if(created) {
		CloseHandle(pi.hThread);
		CloseHandle(pi.hProcess);
	}
	return created;
#else
	//Ignore SIGCHLD so the detached child is reaped automatically instead of
	//becoming a zombie.
	signal(SIGCHLD, SIG_IGN);

	pid_t pid = fork();
	if(pid == 0) {
		//Child: build argv and replace this image with the tool.
		std::vector<char*> argv;
		argv.reserve(args.size() + 2);
		argv.push_back(const_cast<char*>(program.c_str()));
		for(const string& arg : args) {
			argv.push_back(const_cast<char*>(arg.c_str()));
		}
		argv.push_back(nullptr);

		execvp(program.c_str(), argv.data());
		_exit(127); //only reached when exec fails
	}
	return pid >= 0;
#endif
}

string ProcessUtilities::GetExecutableFolder()
{
#if defined(_WIN32)
	wchar_t buffer[MAX_PATH];
	DWORD size = GetModuleFileNameW(nullptr, buffer, MAX_PATH);
	if(size == 0) {
		return "";
	}
	std::wstring path(buffer, size);
	size_t slash = path.find_last_of(L"\\/");
	if(slash != std::wstring::npos) {
		path.resize(slash + 1);
	}
	//Narrow explicitly: the std::string range constructor from wchar_t
	//iterators triggers C4244 at /W4 /WX (wchar_t->char, possible loss).
	std::string result;
	result.reserve(path.size());
	for(wchar_t ch : path) {
		result.push_back(static_cast<char>(ch));
	}
	return result;
#elif defined(__APPLE__)
	uint32_t size = 0;
	_NSGetExecutablePath(nullptr, &size);
	std::vector<char> buffer(size);
	if(_NSGetExecutablePath(buffer.data(), &size) != 0) {
		return "";
	}
	string path(buffer.data());
	size_t slash = path.find_last_of("/");
	if(slash != string::npos) {
		path.resize(slash + 1);
	}
	return path;
#else
	char buffer[4096];
	ssize_t size = readlink("/proc/self/exe", buffer, sizeof(buffer) - 1);
	if(size <= 0) {
		return "";
	}
	buffer[size] = '\0';
	string path(buffer);
	size_t slash = path.find_last_of("/");
	if(slash != string::npos) {
		path.resize(slash + 1);
	}
	return path;
#endif
}
