#include "cohort.h"
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 5 || strcmp(argv[1], "--manifest") || strcmp(argv[3], "--samples")) {
        fputs("usage: cohort-release --manifest BATCHES.tsv --samples NAME,...\n", stderr); return 2;
    }
    manifest inputs = {0}; selection samples = {0};
    cursor *cursors = NULL;
    int status = 1;
    if (selection_parse(argv[4], &samples)) { fputs("invalid sample selection\n", stderr); goto done; }
    if (manifest_load(argv[2], &inputs)) { fputs("cannot open batch manifest or source\n", stderr); goto done; }
    for (size_t s = 0; s < samples.count; ++s) {
        int exists = 0;
        for (size_t i = 0; i < inputs.count; ++i)
            if (bcf_hdr_id2int(inputs.items[i]->header, BCF_DT_SAMPLE, samples.items[s]) >= 0) exists = 1;
        if (!exists) { fputs("requested sample absent from all source headers\n", stderr); goto done; }
    }
    cursors = calloc(inputs.count, sizeof(*cursors));
    if (!cursors) { fputs("allocation failed\n", stderr); goto done; }
    for (size_t i = 0; i < inputs.count; ++i) {
        cursors[i].origin = inputs.items[i];
        if (cursor_advance(&cursors[i])) { fputs("source reading failed\n", stderr); goto done; }
    }
    for (;;) {
        frame_list group = {0};
        int produced = locus_collect(cursors, inputs.count, &group);
        if (produced < 0) { frames_close(&group); fputs("source reading failed\n", stderr); goto done; }
        if (!produced) { frames_close(&group); break; }
        locus site = {0};
        if (locus_open(&group, &site)) { locus_close(&site); frames_close(&group); fputs("locus allocation failed\n", stderr); goto done; }
        int error = locus_publish(stdout, &site, &samples);
        locus_close(&site); frames_close(&group);
        if (error) { fputs("publication failed\n", stderr); goto done; }
    }
    status = 0;
done:
    if (cursors) {
        for (size_t i = 0; i < inputs.count; ++i) frame_close(cursors[i].pending);
        free(cursors);
    }
    selection_close(&samples); manifest_close(&inputs);
    return status;
}
