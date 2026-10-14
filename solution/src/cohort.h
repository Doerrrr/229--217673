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
    int64_t position;
    char *text, **columns;
    size_t ncolumns;
} frame;

typedef struct { source **items; size_t count; } manifest;
typedef struct { char **items; size_t count; } selection;
typedef struct { frame **items; size_t count, capacity; } frame_list;
typedef struct { frame **items; size_t count; char **alts; size_t nalt; } locus;

/* One open source stream. pending is the frame read from that stream but not yet
   published, so that the smallest key over all streams can be selected; this keeps
   only one line per source resident instead of the whole corpus. */
typedef struct { source *origin; frame *pending; int exhausted; } cursor;

int manifest_load(const char *path, manifest *out);
void manifest_close(manifest *value);
int selection_parse(const char *text, selection *out);
void selection_close(selection *value);

int source_next(source *input, frame **out);
void frame_close(frame *value);

int cursor_advance(cursor *value);
int locus_collect(cursor *cursors, size_t count, frame_list *out);
int frames_push(frame_list *value, frame *item);
void frames_close(frame_list *value);

int frame_order(const void *a, const void *b);
int locus_open(frame_list *items, locus *out);
void locus_close(locus *value);
int locus_find(const locus *value, const char *alt);
int locus_ploidy(const char *gt);
int64_t locus_genotype_count(int ploidy, size_t alleles);
int64_t locus_genotype_index(int ploidy, const int *alleles);
void locus_genotype_alleles(int ploidy, size_t alleles, int64_t index, int *out);

void json_string(FILE *out, const char *text);
int fields_publish(FILE *out, const locus *site, const frame *value, int sample_slot);
int locus_publish(FILE *out, const locus *value, const selection *samples);
#endif
