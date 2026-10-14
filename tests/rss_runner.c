#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <grp.h>
#include <signal.h>
#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

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
    long uid = strtol(argv[4], &end, 10);
    if (*end || uid < 1) return 125;
    int output = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    int errors = open(argv[3], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (output < 0 || errors < 0) { perror("exclusive outputs"); return 125; }
    double start = now();
    pid_t child = fork();
    if (child < 0) { perror("fork"); return 125; }
    if (!child) {
        if (setpgid(0, 0) || dup2(output, 1) < 0 || dup2(errors, 2) < 0) _exit(125);
        close(output); close(errors);
        if (geteuid() == 0 && (setgroups(0, NULL) || setgid(uid) || setuid(uid))) _exit(125);
        if (getuid() != (uid_t)uid) _exit(125);
        execvp(argv[5], argv + 5);
        perror("exec"); _exit(125);
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
