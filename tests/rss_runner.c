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

/* Author-owned measuring process. Never link this into a candidate binary. */
static double now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) _exit(125);
    return t.tv_sec + t.tv_nsec / 1e9;
}
int main(int argc, char **argv) {
    if (argc < 7) { fputs("usage: rss-runner seconds stdout stderr uid command args...\n", stderr); return 125; }
    char *end;
    long seconds = strtol(argv[1], &end, 10);
    if (*end || seconds < 1 || seconds > 600) return 125;
    /* This verifier always runs the candidate as UID/GID 10001. Reject every
       other identity before creating outputs or launching a process. There is
       no caller-controlled UID/GID passed into the privilege-changing calls. */
    if (strcmp(argv[4], "10001")) return 125;
    int output = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    int errors = open(argv[3], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (output < 0 || errors < 0) { perror("exclusive outputs"); return 125; }
    double start = now();
    pid_t child = fork();
    if (child < 0) { perror("fork"); return 125; }
    if (!child) {
        if (setpgid(0, 0) || dup2(output, 1) < 0 || dup2(errors, 2) < 0) _exit(125);
        close(output); close(errors);
        /* util-linux owns the privilege transition; both identifiers are
           explicitly 10001. The exec preserves the measured child's PID. */
        char **command = calloc((size_t)argc + 2, sizeof(*command));
        if (!command) _exit(125);
        command[0] = "/usr/bin/setpriv";
        command[1] = "--reuid=10001";
        command[2] = "--regid=10001";
        command[3] = "--clear-groups";
        command[4] = "--no-new-privs";
        command[5] = "--";
        for (int i = 5; i < argc; ++i) command[i + 1] = argv[i];
        execv(command[0], command);
        perror("exec setpriv"); _exit(125);
    }
    close(output); close(errors);
    setpgid(child, child);
    int status = 0, timeout = 0;
    struct rusage usage;
    for (;;) {
        pid_t result = wait4(child, &status, WNOHANG, &usage);
        if (result == child) break;
        if (result < 0 && errno != EINTR) { perror("wait4"); return 125; }
        if (now() - start > seconds) {
            timeout = 1;
            /* Only the process group created for this invocation is targeted. */
            kill(-child, SIGKILL);
            while (wait4(child, &status, 0, &usage) < 0) if (errno != EINTR) return 125;
            break;
        }
        struct timespec delay = {0, 10000000}; nanosleep(&delay, NULL);
    }
    int code = WIFEXITED(status) ? WEXITSTATUS(status) : -WTERMSIG(status);
    printf("{\"returncode\":%d,\"timed_out\":%s,\"peak_rss_kib\":%ld,\"elapsed_seconds\":%.3f}\n",
           code, timeout ? "true" : "false", usage.ru_maxrss, now() - start);
    return 0;
}
