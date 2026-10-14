#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

/*
 * The release view is ordered by (chromosome name, position, source priority,
 * physical ordinal), but the exchange stream is unordered: positions may step
 * backwards and chromosomes may reappear.  Records are therefore reduced to
 * sortable lines, kept in memory up to a fixed byte budget and spilled beyond
 * it as ordered runs, so the resident set follows the budget rather than the
 * number of input records.
 */

static int compare_lines(const void *a, const void *b) {
    return line_compare(*(char *const *)a, *(char *const *)b);
}

int spool_open(record_spool *out, size_t limit) {
    memset(out, 0, sizeof(*out));
    out->limit = limit ? limit : 16u * 1024u * 1024u;
    return 0;
}

/* Hand the in-memory lines to a fresh ordered run file. */
static int run_write(record_spool *spool) {
    if (!spool->count) return 0;
    qsort(spool->lines, spool->count, sizeof(*spool->lines), compare_lines);
    FILE *run = tmpfile();
    if (!run) return -1;
    size_t written = 0;
    while (written < spool->count) {
        if (fputs(spool->lines[written], run) == EOF || fputc('\n', run) == EOF) {
            /* A line belongs to the spool until the run has taken it.  The
               lines that were not written are released here, and the count is
               reset so that spool_close cannot release them a second time. */
            for (size_t i = written; i < spool->count; ++i) free(spool->lines[i]);
            spool->count = 0;
            spool->bytes = 0;
            fclose(run);
            return -1;
        }
        free(spool->lines[written]);
        spool->lines[written] = NULL;
        ++written;
    }
    spool->count = 0;
    spool->bytes = 0;
    if (fflush(run) || fseek(run, 0, SEEK_SET)) { fclose(run); return -1; }
    if (spool->nruns == spool->runs_capacity) {
        size_t capacity = spool->runs_capacity ? spool->runs_capacity * 2 : 8;
        FILE **grown = realloc(spool->runs, capacity * sizeof(*grown));
        if (!grown) { fclose(run); return -1; }
        spool->runs = grown;
        spool->runs_capacity = capacity;
    }
    spool->runs[spool->nruns++] = run;
    return 0;
}

int spool_add(record_spool *spool, const char *line) {
    if (spool->count == spool->capacity) {
        size_t capacity = spool->capacity ? spool->capacity * 2 : 1024;
        char **grown = realloc(spool->lines, capacity * sizeof(*grown));
        if (!grown) return -1;
        spool->lines = grown;
        spool->capacity = capacity;
    }
    char *copy = strdup(line);
    if (!copy) return -1;
    spool->lines[spool->count++] = copy;
    spool->bytes += strlen(copy) + 1;
    if (spool->bytes >= spool->limit && spool->count > 1) return run_write(spool);
    return 0;
}

int spool_finish(record_spool *spool) {
    if (spool->nruns) return run_write(spool);
    if (spool->count) qsort(spool->lines, spool->count, sizeof(*spool->lines), compare_lines);
    return 0;
}

void spool_close(record_spool *value) {
    for (size_t i = 0; i < value->count; ++i) free(value->lines[i]);
    for (size_t i = 0; i < value->nruns; ++i) fclose(value->runs[i]);
    free(value->lines);
    free(value->runs);
    memset(value, 0, sizeof(*value));
}

/* ------------------------------------------------------------------ */
/* The merge cursor borrows the run handles: the spool opens them and  */
/* spool_close is the only place that closes them.                     */
/* ------------------------------------------------------------------ */

int cursor_open(record_cursor *cursor, record_spool *spool) {
    memset(cursor, 0, sizeof(*cursor));
    cursor->spool = spool;
    cursor->nruns = spool->nruns;
    if (!cursor->nruns) return 0;
    cursor->files = calloc(cursor->nruns, sizeof(*cursor->files));
    cursor->heads = calloc(cursor->nruns, sizeof(*cursor->heads));
    cursor->caps = calloc(cursor->nruns, sizeof(*cursor->caps));
    cursor->state = calloc(cursor->nruns, sizeof(*cursor->state));
    if (!cursor->files || !cursor->heads || !cursor->caps || !cursor->state) {
        cursor_close(cursor);
        return -1;
    }
    for (size_t i = 0; i < cursor->nruns; ++i) cursor->files[i] = spool->runs[i];
    return 0;
}

/* state 2 marks an exhausted run. */
static void run_refill(record_cursor *cursor, size_t index) {
    char *head = cursor->heads[index];
    ssize_t length = getline(&head, &cursor->caps[index], cursor->files[index]);
    if (length < 0) {
        free(head);
        cursor->heads[index] = NULL;
        cursor->state[index] = 2;
        if (ferror(cursor->files[index])) cursor->failed = 1;
        return;
    }
    while (length > 0 && (head[length-1] == '\n' || head[length-1] == '\r')) head[--length] = 0;
    cursor->heads[index] = head;
    cursor->state[index] = 1;
}

const char *cursor_next(record_cursor *cursor) {
    if (cursor->failed) return NULL;
    if (!cursor->nruns) {
        if (cursor->index >= cursor->spool->count) return NULL;
        if (cursor->spool->lines[cursor->index] == NULL) return NULL;
        return cursor->spool->lines[cursor->index++];
    }
    size_t best = cursor->nruns;
    for (size_t i = 0; i < cursor->nruns; ++i) {
        if (cursor->state[i] == 0) run_refill(cursor, i);
        if (cursor->failed) return NULL;
        if (cursor->state[i] != 1) continue;
        if (best == cursor->nruns ||
            line_compare(cursor->heads[i], cursor->heads[best]) < 0) best = i;
    }
    if (best == cursor->nruns) return NULL;

    /* The head is replaced immediately, so hand back a private copy that
       stays valid until the next call. */
    size_t length = strlen(cursor->heads[best]);
    if (cursor->capacity < length + 1) {
        char *grown = realloc(cursor->buffer, length + 64);
        if (!grown) { cursor->failed = 1; return NULL; }
        cursor->buffer = grown;
        cursor->capacity = length + 64;
    }
    memcpy(cursor->buffer, cursor->heads[best], length + 1);
    run_refill(cursor, best);
    return cursor->buffer;
}

void cursor_close(record_cursor *value) {
    for (size_t i = 0; i < value->nruns; ++i)
        if (value->heads) free(value->heads[i]);
    free(value->files);
    free(value->heads);
    free(value->caps);
    free(value->state);
    free(value->buffer);
    memset(value, 0, sizeof(*value));
}
