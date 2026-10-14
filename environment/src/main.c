#include "cohort.h"
#include <string.h>

/* Preview entry left by the migration. Native components are available, but
   the page is still a placeholder rather than the required source report. */
int main(int argc, char **argv) {
    if (argc != 5 || strcmp(argv[1], "--manifest") || strcmp(argv[3], "--samples")) {
        fputs("usage: cohort-release --manifest BATCHES.tsv --samples NAME,...\n", stderr);
        return 2;
    }
    puts("{\"chrom\":\"pending\",\"position\":1,\"reference\":\"N\",\"alternate\":[],\"contributors\":[],\"samples\":[]}");
    return ferror(stdout) ? 1 : 0;
}
