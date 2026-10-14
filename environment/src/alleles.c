#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

int locus_open(frame **items, size_t count, locus *out) {
    memset(out, 0, sizeof(*out)); out->items = items; out->count = count;
    for (size_t i = 0; i < count; ++i) {
        char *text = strdup(items[i]->columns[4]), *save = NULL;
        if (!text) { locus_close(out); return -1; }
        for (char *alt = strtok_r(text, ",", &save); alt; alt = strtok_r(NULL, ",", &save)) {
            if (!strcmp(alt, ".")) continue;
            size_t j = 0;
            while (j < out->nalt && strcmp(out->alts[j], alt)) ++j;
            if (j < out->nalt) continue;
            char **next = realloc(out->alts, (out->nalt+1) * sizeof(*next));
            if (!next) { free(text); locus_close(out); return -1; }
            out->alts = next;
            out->alts[out->nalt] = strdup(alt);
            if (!out->alts[out->nalt]) { free(text); locus_close(out); return -1; }
            ++out->nalt;
        }
        free(text);
    }
    return 0;
}

void locus_close(locus *value) {
    for (size_t i = 0; i < value->nalt; ++i) free(value->alts[i]);
    free(value->alts); memset(value, 0, sizeof(*value));
}
