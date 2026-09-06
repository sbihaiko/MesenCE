#include "ProcessUtilities.h"
#include "UTF8Util.h"

#include <vector>

#if defined(__APPLE__)
	#include <mach-o/dyld.h>
#endif

#if defined(_WIN32)
	#include <windows.h>
#else
	#include <unistd.h>
	#include <sys/wait.h>
	#include <cerrno>
	#include <cstdlib>
#endif

#if defined(_WIN32)
namespace
{
	//Quotes one argument the way the MSVC C runtime (and CommandLineToArgvW)
	//parse it back: the argument is wrapped in double quotes, a `"` inside it
	//becomes `\"`, and a run of backslashes is doubled only when it precedes
	//a `"` or the closing quote (a lone backslash elsewhere is literal).
	void AppendQuotedArgument(std::string& cmdline, const std::string& arg)
	{
		cmdline += '"';
		size_t backslashes = 0;
		for(char c : arg) {
			if(c == '\\') {
				backslashes++;
				continue;
			}
			if(c == '"') {
				//Backslashes before a quote must be doubled, then the quote escaped
				cmdline.append(backslashes * 2 + 1, '\\');
				cmdline += '"';
			} else {
				cmdline.append(backslashes, '\\');
				cmdline += c;
			}
			backslashes = 0;
		}
		//Trailing backslashes precede the closing quote: double them
		cmdline.append(backslashes * 2, '\\');
		cmdline += '"';
	}
}
#endif

bool ProcessUtilities::StartDetached(const string& program, const vector<string>& args)
{
#if defined(_WIN32)
	std::string cmdline;
	AppendQuotedArgument(cmdline, program);
	for(const string& arg : args) {
		cmdline += ' ';
		AppendQuotedArgument(cmdline, arg);
	}

	//Paths and arguments are UTF-8 throughout the code base: decode them
	//properly instead of widening byte-by-byte (which mangles anything
	//outside ASCII).
	std::wstring wideCmd = utf8::utf8::decode(cmdline);
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
	//Double fork: the intermediate child detaches (setsid) and exits at once,
	//so the parent can reap it synchronously and the grandchild - the actual
	//tool - is adopted by init. No process-wide signal disposition is touched
	//(a SIG_IGN on SIGCHLD would break every other waitpid() in the host).
	pid_t pid = fork();
	if(pid < 0) {
		return false;
	}
	if(pid == 0) {
		setsid();
		pid_t grandchild = fork();
		if(grandchild != 0) {
			_exit(grandchild < 0 ? 127 : 0);
		}
		//Grandchild: build argv and replace this image with the tool.
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
	int status = 0;
	while(waitpid(pid, &status, 0) < 0 && errno == EINTR) {
	}
	return WIFEXITED(status) && WEXITSTATUS(status) == 0;
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
	return utf8::utf8::encode(path);
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
