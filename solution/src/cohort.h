#ifndef COHORT_H
#define COHORT_H
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <htslib/vcf.h>

/* Failure classes the public policies pin to specific exit codes. */
#define EXIT_USAGE      2   /* CLI or manifest structure */
#define EXIT_SOURCE     3   /* source unreadable or header unparseable */
#define EXIT_RECORD     4   /* record unparseable or reference spans incompatible */
#define EXIT_SAMPLE     5   /* requested sample absent from every header */
#define EXIT_IO         6   /* artifact or temporary file write failure */

/* ---------------------------------------------------------------- source */
typedef struct {
    char *id, *path;
    unsigned rank;
    uint64_t ordinal;
    htsFile *file;
    bcf_hdr_t *header;
    bcf1_t *record;
    kstring_t scratch;
    int *slots;              /* header sample index per requested sample, -1 absent */
} source;

typedef struct { source **items; size_t count; } manifest;
typedef struct { char **items; size_t count; } selection;

int manifest_load(const char *path, manifest *out);
void manifest_close(manifest *value);
int selection_parse(const char *text, selection *out);
void selection_close(selection *value);
int source_bind(source *input, const selection *samples);
/*
 * After the single read pass the source readers are never consulted again: the
 * release pass works from the reduced lines alone.  Their rendered buffers and
 * parsed records are the largest thing a wide source holds, so they are given
 * back here rather than at exit.
 */
void manifest_release_readers(manifest *value);

/*
 * Read one source record and render it twice:
 *   `line`  the reduced sortable line backing the aggregate release view
 *   `plain` the source record as it stands, backing the original view
 * Either may be NULL when that view is not wanted.  Returns 1 on a record,
 * 0 at the end of the source, -1 when the record cannot be read, parsed or
 * represented.
 */
int source_next(source *input, const selection *samples, kstring_t *line, kstring_t *plain);

int line_compare(const char *a, const char *b);

/* --------------------------------------------------------------- alleles */
typedef struct { char **items; size_t count; } allele_list;

void allele_list_init(allele_list *value);
void allele_list_free(allele_list *value);
int allele_list_add(allele_list *value, const char *text);
int allele_list_index(const allele_list *value, const char *text);

uint64_t genotype_slots(int ploidy, int alleles);
uint64_t genotype_rank(const int *alleles, int ploidy);
void genotype_unrank(uint64_t rank, int ploidy, int alleles, int *out);
int genotype_ploidy(const char *gt);

/* ---------------------------------------------------------------- fields */
void json_string(FILE *out, const char *text);
void json_string_ks(kstring_t *out, const char *text);

/* How one source record's dictionary maps into the published dictionary. */
typedef struct {
    int source_alleles;              /* 1 + the record's coordinated ALT count */
    size_t *source_to_pub;           /* [source_alleles] */
    int *pub_to_src;                 /* [dict->count] source index or -1 */
    const allele_list *dict;
} allele_map;

/*
 * Working memory for observation rendering, reserved once per release and
 * reused for every observation.  A position can carry 64 samples x 32 records
 * of 4845 PL values, so allocating per observation would dominate the resident
 * set for no reason.
 */
typedef struct {
    int *combo, *mapped;
    size_t ploidy_cap;
    int *slot_of_rank;
    size_t rank_cap;
    struct { const char *start; size_t length; } *values;
    size_t values_cap;
} observation_scratch;

void observation_scratch_free(observation_scratch *value);
int observation_scratch_reserve(observation_scratch *value, size_t ploidy,
                                size_t ranks, size_t slots);

/* Render one observation expressed in its own source dictionary. */
int observation_plain_ks(kstring_t *out, const char *format, const char *column);
/* Render one observation expressed in the published dictionary. */
int observation_publish(FILE *out, const char *source_id, uint64_t ordinal,
                        const char *format, const char *column,
                        const allele_map *map, observation_scratch *scratch);

/* -------------------------------------------------------------- spooling */
typedef struct {
    char **lines; size_t count, capacity, bytes, limit;
    FILE **runs; size_t nruns, runs_capacity;
} record_spool;

int spool_open(record_spool *out, size_t limit);
int spool_add(record_spool *spool, const char *line);
int spool_finish(record_spool *spool);
void spool_close(record_spool *spool);

/*
 * Walks the reduced lines in release order.  The run handles in `files` are
 * borrowed from the spool: the spool opens them and spool_close closes them,
 * so nothing here may close them a second time.
 */
typedef struct {
    record_spool *spool;
    size_t index;
    FILE **files;
    char **heads;
    size_t *caps;
    unsigned char *state;
    size_t nruns;
    char *buffer;
    size_t capacity;
    int failed;
} record_cursor;

int cursor_open(record_cursor *cursor, record_spool *spool);
const char *cursor_next(record_cursor *cursor);
void cursor_close(record_cursor *cursor);

/* ----------------------------------------------------------------- locus */
typedef struct {
    char *line;                      /* owned copy of the reduced line */
    char *chrom;                     /* borrowed into line */
    long long position;
    unsigned rank;
    const char *source_id;           /* borrowed from the manifest */
    uint64_t ordinal;
    char *ref;                       /* source REF, uncoordinated */
    char *alt;                       /* source ALT field, uncoordinated */
    char *format;
    char **columns;                  /* requested sample columns, NULL when absent */
    char **coord;                    /* coordinated ALT strings */
    size_t ncoord;
} locus_record;

typedef struct {
    char *chrom;
    long long position;
    char *target_ref;                /* longest REF at this position */
    locus_record *records;
    size_t count, capacity;
} locus;

void locus_init(locus *value);
void locus_free(locus *value);
int locus_add(locus *value, char *line, const selection *samples, manifest *inputs);
int locus_same_key(const locus *value, const char *line);

int locus_coordinate(locus *value);            /* -1 when the spans disagree */
int locus_dictionary(locus *value, allele_list *dict);
int locus_publish(FILE *out, const locus *value, const allele_list *dict,
                  const selection *samples);

#endif
