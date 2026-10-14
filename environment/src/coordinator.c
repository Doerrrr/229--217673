#include "cohort.h"
#include <stdlib.h>
#include <string.h>

int frame_compare(const void *a, const void *b) {
    const frame *x = *(frame *const *)a, *y = *(frame *const *)b;
    if (x->rid != y->rid) return x->rid < y->rid ? -1 : 1;
    if (x->position != y->position) return x->position < y->position ? -1 : 1;
    int cmp = strcmp(x->columns[3], y->columns[3]);
    if (cmp) return cmp;
    if (x->origin->rank != y->origin->rank) return x->origin->rank < y->origin->rank ? -1 : 1;
    return x->ordinal < y->ordinal ? -1 : x->ordinal != y->ordinal;
}

int same_locus(const frame *a, const frame *b) {
    return a->position == b->position && !strcmp(a->columns[0], b->columns[0]) && !strcmp(a->columns[3], b->columns[3]);
}

int frames_read_all(manifest *inputs, frame_list *out) {
    memset(out, 0, sizeof(*out));
    for (size_t i = 0; i < inputs->count; ++i) {
        frame *item = NULL;
        int status;
        while ((status = source_next(inputs->items[i], &item)) == 1) {
            if (out->count == out->capacity) {
                size_t capacity = out->capacity ? out->capacity*2 : 128;
                frame **next = realloc(out->items, capacity * sizeof(*next));
                if (!next) { frame_close(item); return -1; }
                out->items = next; out->capacity = capacity;
            }
            out->items[out->count++] = item;
        }
        if (status < 0) return -1;
    }
    qsort(out->items, out->count, sizeof(*out->items), frame_compare);
    return 0;
}

void frames_close(frame_list *value) {
    for (size_t i = 0; i < value->count; ++i) frame_close(value->items[i]);
    free(value->items); memset(value, 0, sizeof(*value));
}
