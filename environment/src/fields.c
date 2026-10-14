#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

void json_string(FILE *out, const char *text) {
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') fprintf(out, "\\%c", *p);
        else if (*p < 32) fprintf(out, "\\u%04x", *p);
        else fputc(*p, out);
    }
    fputc('"', out);
}

static void scalar(FILE *out, const char *value) {
    if (!value || !strcmp(value, ".")) fputs("null", out);
    else fprintf(out, "%lld", strtoll(value, NULL, 10));
}

static void vector(FILE *out, const char *value) {
    if (!value || !strcmp(value, ".")) { fputs("null", out); return; }
    char *text = strdup(value), *save = NULL;
    if (!text) { fputs("null", out); return; }
    fputc('[', out); int count = 0;
    for (char *v = strtok_r(text, ",", &save); v; v = strtok_r(NULL, ",", &save)) {
        if (count++) fputc(',', out);
        scalar(out, v);
    }
    fputc(']', out); free(text);
}

int fields_publish(FILE *out, const frame *value, int sample_slot) {
    if (sample_slot < 0 || (size_t)(9+sample_slot) >= value->ncolumns) return -1;
    char *tags = strdup(value->columns[8]), *values = strdup(value->columns[9+sample_slot]);
    if (!tags || !values) { free(tags); free(values); return -1; }
    size_t count = 1;
    for (char *p = tags; *p; ++p) if (*p == ':') ++count;
    char **keys = calloc(count, sizeof(*keys)), **parts = calloc(count, sizeof(*parts));
    if (!keys || !parts) { free(tags); free(values); free(keys); free(parts); return -1; }
    char *save = NULL; size_t used = 0, nvalue = 0;
    for (char *v = strtok_r(tags, ":", &save); v && used < count; v = strtok_r(NULL, ":", &save)) keys[used++] = v;
    save = NULL;
    for (char *v = strtok_r(values, ":", &save); v && nvalue < used; v = strtok_r(NULL, ":", &save)) parts[nvalue++] = v;
    fputs("{\"source\":", out); json_string(out, value->origin->id);
    fprintf(out, ",\"ordinal\":%llu,\"format\":[", (unsigned long long)value->ordinal);
    for (size_t i = 0; i < used; ++i) { if (i) fputc(',', out); json_string(out, keys[i]); }
    fputs("],\"values\":{", out);
    for (size_t i = 0; i < used; ++i) {
        if (i) fputc(',', out);
        json_string(out, keys[i]); fputc(':', out);
        if (!strcmp(keys[i], "GT")) json_string(out, parts[i] ? parts[i] : ".");
        else if (!strcmp(keys[i], "AD") || !strcmp(keys[i], "PL")) vector(out, parts[i]);
        else scalar(out, parts[i]);
    }
    fputs("}}", out); free(keys); free(parts); free(tags); free(values);
    return ferror(out) ? -1 : 0;
}
