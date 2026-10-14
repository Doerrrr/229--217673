#ifndef COHORT_H
#define COHORT_H
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <htslib/vcf.h>

typedef struct {
    char *id, *path;
    unsigned rank;
    uint64_t ordinal;
    htsFile *file;
    bcf_hdr_t *header;
    bcf1_t *record;
    kstring_t scratch;
} source;

typedef struct {
    source *origin;
    uint64_t ordinal;
    int rid;
    int64_t position;
    char *text, **columns;
    size_t ncolumns;
} frame;

typedef struct { source **items; size_t count; } manifest;
typedef struct { char **items; size_t count; } selection;
typedef struct { frame **items; size_t count, capacity; } frame_list;
typedef struct { frame **items; size_t count; char **alts; size_t nalt; } locus;

int manifest_load(const char *path, manifest *out);
void manifest_close(manifest *value);
int selection_parse(const char *text, selection *out);
void selection_close(selection *value);
int source_next(source *input, frame **out);
void frame_close(frame *value);
int frames_read_all(manifest *inputs, frame_list *out);
void frames_close(frame_list *value);
int frame_compare(const void *a, const void *b);
int same_locus(const frame *a, const frame *b);
int locus_open(frame **items, size_t count, locus *out);
void locus_close(locus *value);
void json_string(FILE *out, const char *text);
int fields_publish(FILE *out, const frame *value, int sample_slot);
int locus_publish(FILE *out, const locus *value, const selection *samples);
#endif
