#include <stdio.h>
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    fputs("{\"status\":\"MIGRATION_UNAVAILABLE\"}\n", stdout);
    fputs("cohort release migration is not configured\n", stderr);
    return 78;
}
