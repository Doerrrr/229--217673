#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

#define MAX_SOURCES 64
#define MAX_SAMPLES 256

static char *relative_path(const char *manifest_path, const char *path) {
    if (*path == '/') return strdup(path);
    const char *slash = strrchr(manifest_path, '/');
    if (!slash) return strdup(path);
    size_t prefix = (size_t)(slash - manifest_path) + 1;
    char *result = malloc(prefix + strlen(path) + 1);
    if (!result) return NULL;
    memcpy(result, manifest_path, prefix);
    strcpy(result + prefix, path);
    return result;
}

/*
 * Returns 0 on success, EXIT_USAGE when the manifest is not a well formed
 * source/path table and EXIT_SOURCE when a listed source cannot be opened or
 * its header cannot be parsed.
 */
int manifest_load(const char *path, manifest *out) {
    memset(out, 0, sizeof(*out));
    FILE *file = fopen(path, "r");
    if (!file) return EXIT_SOURCE;
    char *line = NULL;
    size_t capacity = 0;
    ssize_t n = getline(&line, &capacity, file);
    if (n < 0 || (strcmp(line, "source\tpath\n") && strcmp(line, "source\tpath\r\n"))) {
        free(line); fclose(file); return EXIT_USAGE;
    }
    int status = 0;
    while ((n = getline(&line, &capacity, file)) >= 0) {
        while (n && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = 0;
        if (!n) continue;
        char *tab = strchr(line, '\t');
        if (!tab || tab == line || !tab[1] || strchr(tab+1, '\t') || out->count == MAX_SOURCES) {
            status = EXIT_USAGE; goto done;
        }
        *tab = 0;
        for (size_t i = 0; i < out->count; ++i) if (!strcmp(out->items[i]->id, line)) {
            status = EXIT_USAGE; goto done;
        }
        source *s = calloc(1, sizeof(*s));
        if (!s) { status = EXIT_USAGE; goto done; }
        source **items = realloc(out->items, (out->count + 1) * sizeof(*items));
        if (!items) { free(s); status = EXIT_USAGE; goto done; }
        out->items = items;
        out->items[out->count] = s;
        s->rank = (unsigned)out->count++;
        s->id = strdup(line);
        s->path = relative_path(path, tab+1);
        if (!s->id || !s->path) { status = EXIT_USAGE; goto done; }
        s->file = bcf_open(s->path, "r");
        if (!s->file) { status = EXIT_SOURCE; goto done; }
        s->header = bcf_hdr_read(s->file);
        s->record = bcf_init();
        if (!s->header || !s->record) { status = EXIT_SOURCE; goto done; }
    }
    if (!out->count) status = EXIT_USAGE;
done:
    free(line); fclose(file);
    if (status) { manifest_close(out); return status; }
    return 0;
}

void manifest_close(manifest *value) {
    for (size_t i = 0; i < value->count; ++i) {
        source *s = value->items[i];
        if (s->record) bcf_destroy(s->record);
        if (s->header) bcf_hdr_destroy(s->header);
        if (s->file) bcf_close(s->file);
        free(s->scratch.s); free(s->slots); free(s->id); free(s->path); free(s);
    }
    free(value->items); memset(value, 0, sizeof(*value));
}

void manifest_release_readers(manifest *value) {
    for (size_t i = 0; i < value->count; ++i) {
        source *s = value->items[i];
        if (s->record) { bcf_destroy(s->record); s->record = NULL; }
        if (s->header) { bcf_hdr_destroy(s->header); s->header = NULL; }
        if (s->file) { bcf_close(s->file); s->file = NULL; }
        free(s->scratch.s);
        s->scratch.s = NULL; s->scratch.l = 0; s->scratch.m = 0;
        free(s->slots); s->slots = NULL;
    }
}

/* Remember which of the requested samples this source actually declares. */
int source_bind(source *input, const selection *samples) {
    free(input->slots);
    input->slots = malloc(samples->count ? samples->count * sizeof(*input->slots) : sizeof(int));
    if (!input->slots) return -1;
    for (size_t s = 0; s < samples->count; ++s)
        input->slots[s] = bcf_hdr_id2int(input->header, BCF_DT_SAMPLE, samples->items[s]);
    return 0;
}

static int name_is_plain(const char *text) {
    if (!*text) return 0;
    for (const char *p = text; *p; ++p) {
        unsigned char c = (unsigned char)*p;
        if (c <= ' ' || c == 0x7f || c == ',' || c > 0x7e) return 0;
    }
    return 1;
}

int selection_parse(const char *text, selection *out) {
    memset(out, 0, sizeof(*out));
    if (!*text) return EXIT_USAGE;
    char *copy = strdup(text);
    if (!copy) return EXIT_USAGE;
    char *field = copy;
    for (;;) {
        char *comma = strchr(field, ',');
        if (comma) *comma = 0;
        if (!name_is_plain(field) || out->count == MAX_SAMPLES) goto fail;
        for (size_t i = 0; i < out->count; ++i) if (!strcmp(out->items[i], field)) goto fail;
        char **next = realloc(out->items, (out->count + 1) * sizeof(*next));
        if (!next) goto fail;
        out->items = next;
        out->items[out->count] = strdup(field);
        if (!out->items[out->count]) goto fail;
        ++out->count;
        if (!comma) break;
        field = comma+1;
    }
    free(copy);
    return 0;
fail:
    free(copy);
    selection_close(out);
    return EXIT_USAGE;
}

void selection_close(selection *value) {
    for (size_t i = 0; i < value->count; ++i) free(value->items[i]);
    free(value->items); memset(value, 0, sizeof(*value));
}
