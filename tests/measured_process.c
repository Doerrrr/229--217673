#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Author-owned launcher; never linked into candidate code. Fixed identity is
 * applied with setpriv, not a caller-provided UID/GID or credential syscall. */
static double now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) _exit(125);
    return t.tv_sec + t.tv_nsec / 1e9;
}
int main(int argc, char **argv) {
    if (argc < 6) return 125;
    char *end = NULL;
    long seconds = strtol(argv[1], &end, 10);
    if (*end || seconds < 1 || seconds > 600) return 125;
    long size = strtol(argv[4], &end, 10);
    if (*end || size < -1 || size > 2147483647L) return 125;
    int output = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    int errors = open(argv[3], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (output < 0 || errors < 0) { perror("exclusive outputs"); return 125; }
    double start = now();
    pid_t child = fork();
    if (child < 0) return 125;
    if (!child) {
        if (setpgid(0, 0) || dup2(output, 1) < 0 || dup2(errors, 2) < 0) _exit(125);
        close(output); close(errors);
        if (size >= 0) {
            struct rlimit limit = {(rlim_t)size, (rlim_t)size};
            if (setrlimit(RLIMIT_FSIZE, &limit)) _exit(125);
            signal(SIGXFSZ, SIG_IGN);
        }
        char **command = calloc((size_t)argc + 4, sizeof(char *));
        if (!command) _exit(125);
        command[0] = "/usr/bin/setpriv";
        command[1] = "--reuid=10001";
        command[2] = "--regid=10001";
        command[3] = "--clear-groups";
        command[4] = "--no-new-privs";
        command[5] = "--";
        for (int i = 5; i < argc; ++i) command[i+1] = argv[i];
        execv(command[0], command);
        perror("exec setpriv"); _exit(125);
    }
    close(output); close(errors);
    setpgid(child, child);
    printf("{\"child_pid\":%ld,\"process_group\":%ld}\n", (long)child, (long)child);
    fflush(stdout);
    int status = 0, timeout = 0;
    struct rusage usage;
    for (;;) {
        pid_t result = wait4(child, &status, WNOHANG, &usage);
        if (result == child) break;
        if (result < 0 && errno != EINTR) return 125;
        if (now() - start > seconds) {
            timeout = 1;
            kill(-child, SIGKILL);
            while (wait4(child, &status, 0, &usage) < 0) if (errno != EINTR) return 125;
            break;
        }
        struct timespec delay = {0, 10000000}; nanosleep(&delay, NULL);
    }
    /* Clean descendants belonging to this invocation, never other graders. */
    kill(-child, SIGKILL);
    int code = WIFEXITED(status) ? WEXITSTATUS(status) : -WTERMSIG(status);
    printf("{\"returncode\":%d,\"timed_out\":%s,\"peak_rss_kib\":%ld,\"elapsed_seconds\":%.3f}\n",
           code, timeout ? "true" : "false", usage.ru_maxrss, now() - start);
    return 0;
}
