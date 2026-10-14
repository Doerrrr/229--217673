#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>

void json_string(FILE *out, const char *text) {
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') fprintf(out, "\\%c", *p);
        else if (*p < 32) fprintf(out, "\\u%04x", *p);
        else fputc(*p, out);
    }
    fputc('"', out);
}

/* a slot/measurement the source has no value for */
#define ABSENT INT64_MIN
#define MAX_PLOIDY 8

static int64_t *scratch = NULL;
static size_t scratch_size = 0;
static char **tokens = NULL;
static size_t token_size = 0;

static int scratch_reserve(size_t count) {
    if (scratch_size >= count) return 0;
    int64_t *next = realloc(scratch, count * sizeof(*next));
    if (!next) return -1;
    scratch = next; scratch_size = count;
    return 0;
}

static int tokens_reserve(size_t count) {
    if (token_size >= count) return 0;
    char **next = realloc(tokens, count * sizeof(*next));
    if (!next) return -1;
    tokens = next; token_size = count;
    return 0;
}

static size_t count_fields(const char *text, char separator) {
    if (!text || !*text) return 0;
    size_t count = 1;
    for (const char *p = text; *p; ++p) if (*p == separator) ++count;
    return count;
}

/* split in place, keeping empty fields so that vectors stay aligned */
static size_t split_fields(char *text, char separator, char **out, size_t capacity) {
    if (!text) return 0;
    size_t count = 0;
    char *field = text;
    for (;;) {
        if (count < capacity) out[count] = field;
        ++count;
        char *at = strchr(field, separator);
        if (!at) break;
        *at = 0;
        field = at + 1;
    }
    return count;
}

static int64_t measurement(const char *text) {
    if (!text || !*text || !strcmp(text, ".")) return ABSENT;
    return strtoll(text, NULL, 10);
}

static void print_vector(FILE *out, size_t count) {
    fputc('[', out);
    for (size_t i = 0; i < count; ++i) {
        if (i) fputc(',', out);
        if (scratch[i] == ABSENT) fputs("null", out);
        else fprintf(out, "%lld", (long long)scratch[i]);
    }
    fputc(']', out);
}

/*
   A source states its measurements against its own allele dictionary.  The report
   states them against the published dictionary of the key, because that is what the
   receiver reads them with: an allele or genotype has to keep its identity no matter
   how its source happened to spell it, and a slot the source has no measurement for
   stays unobserved instead of being filled with a value.
   map[i] is the published index of source allele i (index 0 is REF).
*/
static void emit_number_r(FILE *out, const locus *site, const char *text, const int *map, size_t nsrc) {
    size_t given = count_fields(text, ',');
    size_t count = site->nalt + 1;
    if (!given || (given == 1 && !*text) || (given == 1 && !strcmp(text, "."))) { fputs("null", out); return; }
    if (scratch_reserve(count) || tokens_reserve(given)) { fputs("null", out); return; }
    char *copy = strdup(text);
    if (!copy) { fputs("null", out); return; }
    size_t used = split_fields(copy, ',', tokens, given);
    for (size_t i = 0; i < count; ++i) scratch[i] = ABSENT;
    for (size_t i = 0; i < used; ++i) {
        if (i >= nsrc) break;
        int slot = map[i];
        if (slot < 0 || (size_t)slot >= count) continue;
        scratch[slot] = measurement(tokens[i]);
    }
    free(copy);
    print_vector(out, count);
}

static void emit_number_a(FILE *out, const locus *site, const char *text, const int *map, size_t nsrc) {
    size_t given = count_fields(text, ',');
    size_t count = site->nalt;
    if (!given || (given == 1 && !*text) || (given == 1 && !strcmp(text, "."))) { fputs("null", out); return; }
    if (!count) { fputs("null", out); return; }
    if (scratch_reserve(count) || tokens_reserve(given)) { fputs("null", out); return; }
    char *copy = strdup(text);
    if (!copy) { fputs("null", out); return; }
    size_t used = split_fields(copy, ',', tokens, given);
    for (size_t i = 0; i < count; ++i) scratch[i] = ABSENT;
    for (size_t i = 0; i < used; ++i) {
        int slot = (i + 1 < nsrc) ? map[i+1] : -1;      /* Number=A starts at the first ALT */
        if (slot < 1 || (size_t)slot > count) continue;
        scratch[slot-1] = measurement(tokens[i]);
    }
    free(copy);
    print_vector(out, count);
}

static void emit_number_g(FILE *out, const locus *site, const char *text, const int *map, size_t nsrc, int ploidy) {
    size_t given = count_fields(text, ',');
    if (!given || (given == 1 && !*text) || (given == 1 && !strcmp(text, ".")) || ploidy < 1 || ploidy > MAX_PLOIDY) {
        fputs("null", out); return;
    }
    int64_t count = locus_genotype_count(ploidy, site->nalt + 1);
    int64_t source_count = locus_genotype_count(ploidy, nsrc);
    if (count <= 0 || source_count <= 0 || count > (int64_t)(1<<26)) { fputs("null", out); return; }
    if (scratch_reserve((size_t)count) || tokens_reserve(given)) { fputs("null", out); return; }
    char *copy = strdup(text);
    if (!copy) { fputs("null", out); return; }
    size_t used = split_fields(copy, ',', tokens, given);
    for (int64_t i = 0; i < count; ++i) scratch[i] = ABSENT;
    for (size_t i = 0; i < used && (int64_t)i < source_count; ++i) {
        int source_alleles[MAX_PLOIDY], translated[MAX_PLOIDY];
        locus_genotype_alleles(ploidy, nsrc, (int64_t)i, source_alleles);
        int usable = 1;
        for (int j = 0; j < ploidy; ++j) {
            int slot = map[source_alleles[j]];
            if (slot < 0) { usable = 0; break; }
            translated[j] = slot;
        }
        if (!usable) continue;
        for (int a = 0; a < ploidy; ++a)                 /* a genotype is unordered */
            for (int b = a+1; b < ploidy; ++b)
                if (translated[b] < translated[a]) { int t = translated[a]; translated[a] = translated[b]; translated[b] = t; }
        int64_t index = locus_genotype_index(ploidy, translated);
        if (index >= 0 && index < count) scratch[index] = measurement(tokens[i]);
    }
    free(copy);
    print_vector(out, (size_t)count);
}

static void emit_scalar(FILE *out, const char *text) {
    int64_t value = measurement(text);
    if (value == ABSENT) fputs("null", out);
    else fprintf(out, "%lld", (long long)value);
}

/* GT keeps its separators and its allele visit order; only the allele ids change */
static int emit_gt(FILE *out, const char *text, const int *map, size_t nsrc) {
    fputc('"', out);
    if (!text || !*text) { fputs(".", out); fputc('"', out); return 0; }
    for (const char *p = text; *p; ) {
        if (*p == '/' || *p == '|' || *p == '.') { fputc(*p++, out); continue; }
        if (*p < '0' || *p > '9') { ++p; continue; }
        char *end = NULL;
        long index = strtol(p, &end, 10);
        p = end;
        if (index == 0) fputc('0', out);
        else if ((size_t)index < nsrc && map[index] >= 0) fprintf(out, "%d", map[index]);
        else { fprintf(stderr, "genotype allele %ld is outside the published dictionary\n", index); return -1; }
    }
    fputc('"', out);
    return 0;
}

int fields_publish(FILE *out, const locus *site, const frame *value, int sample_slot) {
    if (sample_slot < 0 || (size_t)(9+sample_slot) >= value->ncolumns) return -1;
    bcf_hdr_t *header = value->origin->header;
    const char *cell = value->columns[9+sample_slot];
    int result = -1;
    char *tag_text = NULL, *cell_text = NULL, *alt_text = NULL;
    char **keys = NULL, **cells = NULL, **source_alts = NULL;
    int *map = NULL;
    size_t nkeys = count_fields(value->columns[8], ':');
    size_t ncell = count_fields(cell, ':');
    size_t used = 0, measured = 0, nsrc_alt = 0, nsrc = 1;

    tag_text = strdup(value->columns[8]);
    cell_text = strdup(cell);
    alt_text = strdup(value->columns[4]);
    keys = calloc(nkeys ? nkeys : 1, sizeof(*keys));
    cells = calloc(ncell ? ncell : 1, sizeof(*cells));
    if (!tag_text || !cell_text || !alt_text || !keys || !cells) goto cleanup;
    used = split_fields(tag_text, ':', keys, nkeys);
    measured = split_fields(cell_text, ':', cells, ncell);

    /* the source's own allele dictionary, translated into the published one */
    nsrc_alt = count_fields(alt_text, ',');
    if (nsrc_alt == 1 && !strcmp(alt_text, ".")) nsrc_alt = 0;
    source_alts = calloc(nsrc_alt ? nsrc_alt : 1, sizeof(*source_alts));
    map = calloc(nsrc_alt + 1, sizeof(*map));
    if (!source_alts || !map) goto cleanup;
    map[0] = 0;
    if (nsrc_alt) {
        nsrc_alt = split_fields(alt_text, ',', source_alts, nsrc_alt);
        for (size_t i = 0; i < nsrc_alt; ++i) {
            int slot = locus_find(site, source_alts[i]);
            map[i+1] = slot >= 0 ? slot + 1 : -1;      /* published allele 0 is the reference */
        }
    }
    nsrc = nsrc_alt + 1;

    int ploidy = -1;
    for (size_t i = 0; i < used; ++i)
        if (!strcmp(keys[i], "GT")) ploidy = locus_ploidy(i < measured ? cells[i] : ".");

    fputs("{\"source\":", out); json_string(out, value->origin->id);
    fprintf(out, ",\"ordinal\":%llu,\"format\":[", (unsigned long long)value->ordinal);
    for (size_t i = 0; i < used; ++i) { if (i) fputc(',', out); json_string(out, keys[i]); }
    fputs("],\"values\":{", out);
    result = 0;
    for (size_t i = 0; i < used; ++i) {
        if (i) fputc(',', out);
        json_string(out, keys[i]); fputc(':', out);
        const char *measurement_text = i < measured ? cells[i] : NULL;
        if (!strcmp(keys[i], "GT")) {
            if (emit_gt(out, measurement_text, map, nsrc)) { result = -1; break; }
            continue;
        }
        int id = bcf_hdr_id2int(header, BCF_DT_ID, keys[i]);
        int number = id >= 0 ? bcf_hdr_id2length(header, BCF_HL_FMT, id) : BCF_VL_VAR;
        if (number == BCF_VL_R) emit_number_r(out, site, measurement_text, map, nsrc);
        else if (number == BCF_VL_A) emit_number_a(out, site, measurement_text, map, nsrc);
        else if (number == BCF_VL_G) emit_number_g(out, site, measurement_text, map, nsrc, ploidy);
        else emit_scalar(out, measurement_text);
    }
    fputs("}}", out);
    if (ferror(out)) result = -1;

cleanup:
    free(keys); free(cells); free(source_alts); free(map);
    free(tag_text); free(cell_text); free(alt_text);
    return result;
}
