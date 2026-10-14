#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

int source_next(source *input, frame **out) {
    *out = NULL;
    int status = bcf_read(input->file, input->header, input->record);
    if (status == -1) {
        /* Frames retain their source header, never the decoder or open file. */
        bcf_close(input->file); input->file = NULL;
        bcf_destroy(input->record); input->record = NULL;
        free(input->scratch.s); memset(&input->scratch, 0, sizeof(input->scratch));
        return 0;
    }
    if (status < 0 || input->record->errcode) return -1;
    input->scratch.l = 0;
    if (vcf_format1(input->header, input->record, &input->scratch) < 0) return -1;
    while (input->scratch.l && (input->scratch.s[input->scratch.l-1] == '\n' || input->scratch.s[input->scratch.l-1] == '\r'))
        input->scratch.s[--input->scratch.l] = 0;
    frame *f = calloc(1, sizeof(*f));
    if (!f) return -1;
    f->origin = input; f->ordinal = input->ordinal++;
    f->position = input->record->pos + 1;
    f->text = strdup(input->scratch.s);
    if (!f->text) { frame_close(f); return -1; }
    size_t count = 1;
    for (char *p = f->text; *p; ++p) if (*p == '\t') ++count;
    f->columns = calloc(count, sizeof(*f->columns));
    if (!f->columns) { frame_close(f); return -1; }
    char *field = f->text;
    for (;;) {
        f->columns[f->ncolumns++] = field;
        char *tab = strchr(field, '\t');
        if (!tab) break;
        *tab = 0; field = tab+1;
    }
    if (f->ncolumns < 9) { frame_close(f); return -1; }
    /* Bound per-source decoding capacity in addition to the owned group. */
    if (input->scratch.m > 65536) {
        free(input->scratch.s); memset(&input->scratch, 0, sizeof(input->scratch));
        bcf_destroy(input->record); input->record = bcf_init();
        if (!input->record) { frame_close(f); return -1; }
    }
    *out = f; return 1;
}

void frame_close(frame *value) {
    if (!value) return;
    free(value->columns); free(value->text); free(value);
}
