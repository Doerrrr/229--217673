#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

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

int manifest_load(const char *path, manifest *out) {
    memset(out, 0, sizeof(*out));
    FILE *file = fopen(path, "r");
    if (!file) return -1;
    char *line = NULL;
    size_t capacity = 0;
    ssize_t n = getline(&line, &capacity, file);
    if (n < 0 || (strcmp(line, "source\tpath\n") && strcmp(line, "source\tpath\r\n"))) goto fail;
    while ((n = getline(&line, &capacity, file)) >= 0) {
        while (n && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = 0;
        char *tab = strchr(line, '\t');
        if (!tab || tab == line || !tab[1] || strchr(tab+1, '\t') || out->count == 16) goto fail;
        *tab = 0;
        for (size_t i = 0; i < out->count; ++i) if (!strcmp(out->items[i]->id, line)) goto fail;
        source *s = calloc(1, sizeof(*s));
        if (!s) goto fail;
        source **items = realloc(out->items, (out->count + 1) * sizeof(*items));
        if (!items) { free(s); goto fail; }
        out->items = items;
        out->items[out->count] = s;
        s->rank = (unsigned)out->count++;
        s->id = strdup(line); s->path = relative_path(path, tab+1);
        if (!s->id || !s->path) goto fail;
        s->file = bcf_open(s->path, "r");
        if (!s->file) goto fail;
        s->header = bcf_hdr_read(s->file); s->record = bcf_init();
        if (!s->header || !s->record) goto fail;
    }
    free(line); fclose(file);
    if (!out->count) { manifest_close(out); return -1; }
    return 0;
fail:
    free(line); fclose(file); manifest_close(out); return -1;
}

void manifest_close(manifest *value) {
    for (size_t i = 0; i < value->count; ++i) {
        source *s = value->items[i];
        if (s->record) bcf_destroy(s->record);
        if (s->header) bcf_hdr_destroy(s->header);
        if (s->file) bcf_close(s->file);
        free(s->scratch.s); free(s->id); free(s->path); free(s);
    }
    free(value->items); memset(value, 0, sizeof(*value));
}

int selection_parse(const char *text, selection *out) {
    memset(out, 0, sizeof(*out));
    char *copy = strdup(text);
    if (!copy) return -1;
    char *field = copy;
    for (;;) {
        char *comma = strchr(field, ',');
        if (comma) *comma = 0;
        if (!*field || out->count == 256) goto fail;
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
    free(copy); return 0;
fail:
    free(copy); selection_close(out); return -1;
}

void selection_close(selection *value) {
    for (size_t i = 0; i < value->count; ++i) free(value->items[i]);
    free(value->items); memset(value, 0, sizeof(*value));
}
