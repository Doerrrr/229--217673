#include "cohort.h"
#include <stdlib.h>
#include <string.h>

/*
   Ordering is by the publication key: chromosome name in UTF-8 (byte) order, then
   numeric position, then REF.  The header's numeric dictionary index is not a
   cross-batch identifier, so it must not take part in the comparison; rank and
   record ordinal only break ties between records that share one key.
*/
static int key_compare(const frame *x, const frame *y) {
    int cmp = strcmp(x->columns[0], y->columns[0]);
    if (cmp) return cmp;
    if (x->position != y->position) return x->position < y->position ? -1 : 1;
    cmp = strcmp(x->columns[3], y->columns[3]);
    if (cmp) return cmp;
    if (x->origin->rank != y->origin->rank) return x->origin->rank < y->origin->rank ? -1 : 1;
    return x->ordinal < y->ordinal ? -1 : x->ordinal != y->ordinal;
}

int frame_order(const void *a, const void *b) {
    return key_compare(*(frame *const *)a, *(frame *const *)b);
}

static int key_equal(const frame *x, const frame *y) {
    return x->position == y->position && !strcmp(x->columns[0], y->columns[0]) && !strcmp(x->columns[3], y->columns[3]);
}

int frames_push(frame_list *value, frame *item) {
    if (value->count == value->capacity) {
        size_t capacity = value->capacity ? value->capacity*2 : 32;
        frame **next = realloc(value->items, capacity * sizeof(*next));
        if (!next) return -1;
        value->items = next; value->capacity = capacity;
    }
    value->items[value->count++] = item;
    return 0;
}

int cursor_advance(cursor *value) {
    if (value->exhausted) return 0;
    frame *item = NULL;
    int status = source_next(value->origin, &item);
    if (status < 0) return -1;
    if (status == 0) { value->exhausted = 1; value->pending = NULL; return 0; }
    value->pending = item;
    return 0;
}

/*
   Collect every record that belongs to the next publication key.  Only records of
   one key are ever resident, so the report is produced as a streaming merge of the
   sources (the exchange record guarantees that every source is already sorted by
   the publication key).  Returns 1 when a key was produced, 0 at end of input and
   -1 on failure.
*/
int locus_collect(cursor *cursors, size_t count, frame_list *out) {
    memset(out, 0, sizeof(*out));
    const frame *best = NULL;
    for (size_t i = 0; i < count; ++i) {
        frame *f = cursors[i].pending;
        if (!f) continue;
        if (!best || key_compare(f, best) < 0) best = f;
    }
    if (!best) return 0;
    for (;;) {
        size_t chosen = count;
        for (size_t i = 0; i < count; ++i) {
            frame *f = cursors[i].pending;
            if (!f || !key_equal(f, best)) continue;
            if (chosen == count || key_compare(f, cursors[chosen].pending) < 0) chosen = i;
        }
        if (chosen == count) return 1;
        frame *item = cursors[chosen].pending;
        cursors[chosen].pending = NULL;
        if (frames_push(out, item)) { frame_close(item); return -1; }
        if (cursor_advance(&cursors[chosen])) return -1;
    }
}

void frames_close(frame_list *value) {
    for (size_t i = 0; i < value->count; ++i) frame_close(value->items[i]);
    free(value->items); memset(value, 0, sizeof(*value));
}
