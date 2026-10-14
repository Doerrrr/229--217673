#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

void json_string(FILE *out, const char *text) {
    fputc('"', out);
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') fprintf(out, "\\%c", *p);
        else if (*p < 32) fprintf(out, "\\u%04x", *p);
        else fputc(*p, out);
    }
    fputc('"', out);
}

void json_string_ks(kstring_t *out, const char *text) {
    kputc('"', out);
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') { kputc('\\', out); kputc(*p, out); }
        else if (*p < 32) ksprintf(out, "\\u%04x", *p);
        else kputc(*p, out);
    }
    kputc('"', out);
}

/* ------------------------------------------------------------ scanning -- */

/*
 * Field `index` of a separated list, borrowed from the caller's text.  A FORMAT
 * tag and its measurement are paired by position, so the index is what selects
 * a measurement and an empty field still occupies its slot.
 */
static int list_token(const char *text, char separator, size_t index,
                      const char **start, size_t *length) {
    if (!text) return 0;
    const char *field = text;
    for (size_t i = 0;; ++i) {
        const char *next = strchr(field, separator);
        size_t size = next ? (size_t)(next - field) : strlen(field);
        if (i == index) { *start = field; *length = size; return 1; }
        if (!next) return 0;
        field = next + 1;
    }
}

/* The same, inside a substring that is not terminated. */
static int bounded_token(const char *text, size_t total, char separator, size_t index,
                         const char **start, size_t *length) {
    if (!text) return 0;
    size_t begin = 0;
    for (size_t i = 0;; ++i) {
        size_t end = begin;
        while (end < total && text[end] != separator) ++end;
        if (i == index) { *start = text + begin; *length = end - begin; return 1; }
        if (end >= total) return 0;
        begin = end + 1;
    }
}

static int is_missing(const char *start, size_t length) {
    return start == NULL || length == 0 || (length == 1 && *start == '.');
}

static size_t field_count(const char *text, char separator) {
    size_t count = 0;
    if (!text) return 0;
    for (const char *p = text; *p; ++p) if (*p == separator) ++count;
    return count + 1;
}

static const char *tag_at(const char *format, size_t index, size_t *length) {
    const char *start = NULL;
    if (!list_token(format, ':', index, &start, length)) return NULL;
    return start;
}

/* A measurement that is not a decimal integer is not a measurement. */
static void number_at(FILE *out, const char *start, size_t length) {
    if (is_missing(start, length)) { fputs("null", out); return; }
    char buffer[32];
    if (length >= sizeof(buffer)) { fputs("null", out); return; }
    memcpy(buffer, start, length);
    buffer[length] = 0;
    char *end = NULL;
    errno = 0;
    long long parsed = strtoll(buffer, &end, 10);
    if (!errno && end && end != buffer && !*end) fprintf(out, "%lld", parsed);
    else fputs("null", out);
}

static void number_at_ks(kstring_t *out, const char *start, size_t length) {
    if (is_missing(start, length)) { kputs("null", out); return; }
    char buffer[32];
    if (length >= sizeof(buffer)) { kputs("null", out); return; }
    memcpy(buffer, start, length);
    buffer[length] = 0;
    char *end = NULL;
    errno = 0;
    long long parsed = strtoll(buffer, &end, 10);
    if (!errno && end && end != buffer && !*end) ksprintf(out, "%lld", parsed);
    else kputs("null", out);
}

/* ---------------------------------------------------- the original view -- */

/* Values exactly as the source wrote them, walked once, in their own order. */
static void plain_vector_ks(kstring_t *out, const char *text, size_t total) {
    if (is_missing(text, total)) { kputs("null", out); return; }
    kputc('[', out);
    size_t begin = 0;
    for (size_t k = 0;; ++k) {
        size_t end = begin;
        while (end < total && text[end] != ',') ++end;
        if (k) kputc(',', out);
        number_at_ks(out, text + begin, end - begin);
        if (end >= total) break;
        begin = end + 1;
    }
    kputc(']', out);
}

int observation_plain_ks(kstring_t *out, const char *format, const char *column) {
    if (!format || !*format) format = ".";
    size_t ntags = field_count(format, ':');
    kputc('{', out);
    int first = 1;
    for (size_t i = 0; i < ntags; ++i) {
        size_t tag_length = 0;
        const char *tag = tag_at(format, i, &tag_length);
        if (!tag || !tag_length || (tag_length == 1 && *tag == '.')) continue;
        char name[64];
        if (tag_length >= sizeof(name)) continue;
        memcpy(name, tag, tag_length); name[tag_length] = 0;

        const char *raw = NULL; size_t raw_length = 0;
        list_token(column ? column : ".", ':', i, &raw, &raw_length);
        if (!first) kputc(',', out);
        first = 0;
        json_string_ks(out, name);
        kputc(':', out);
        if (!strcmp(name, "GT")) {
            if (is_missing(raw, raw_length)) kputs("\".\"", out);
            else { kputc('"', out); kputsn(raw, raw_length, out); kputc('"', out); }
        } else if (!strcmp(name, "AD") || !strcmp(name, "PL")) {
            plain_vector_ks(out, raw, raw_length);
        } else {
            number_at_ks(out, raw, raw_length);
        }
    }
    kputc('}', out);
    return 0;
}

/* ------------------------------------------------ the published view ---- */

void observation_scratch_free(observation_scratch *value) {
    free(value->combo); free(value->mapped);
    free(value->slot_of_rank); free(value->values);
    memset(value, 0, sizeof(*value));
}

int observation_scratch_reserve(observation_scratch *value, size_t ploidy,
                                size_t ranks, size_t slots) {
    if (value->ploidy_cap < ploidy) {
        int *combo = realloc(value->combo, ploidy * sizeof(*combo));
        if (!combo) return -1;
        value->combo = combo;
        int *mapped = realloc(value->mapped, ploidy * sizeof(*mapped));
        if (!mapped) return -1;
        value->mapped = mapped;
        value->ploidy_cap = ploidy;
    }
    if (value->rank_cap < ranks) {
        int *grown = realloc(value->slot_of_rank, (ranks ? ranks : 1) * sizeof(*grown));
        if (!grown) return -1;
        value->slot_of_rank = grown;
        value->rank_cap = ranks;
    }
    if (value->values_cap < slots) {
        void *grown = realloc(value->values, (slots ? slots : 1) * sizeof(*value->values));
        if (!grown) return -1;
        value->values = grown;
        value->values_cap = slots;
    }
    return 0;
}

/* GT alleles are source indices; the published allele is the coordinated one. */
static void gt_publish(FILE *out, const char *raw, size_t raw_length, const allele_map *map) {
    if (is_missing(raw, raw_length)) { fputs("\".\"", out); return; }
    fputc('"', out);
    const char *p = raw;
    const char *stop = raw + raw_length;
    while (p < stop) {
        const char *end = p;
        while (end < stop && *end != '/' && *end != '|') ++end;
        size_t length = (size_t)(end - p);
        int mapped = 0;
        if (length == 1 && *p == '.') fputc('.', out);
        else {
            char buffer[32];
            if (length && length < sizeof(buffer)) {
                memcpy(buffer, p, length);
                buffer[length] = 0;
                char *tail = NULL;
                long index = strtol(buffer, &tail, 10);
                if (tail && *tail == 0 && index >= 0 && index < map->source_alleles) {
                    fprintf(out, "%zu", map->source_to_pub[index]);
                    mapped = 1;
                }
            }
            if (!mapped) fputc('.', out);
        }
        if (end >= stop) break;
        fputc(*end, out);
        p = end + 1;
    }
    fputc('"', out);
}

/* AD is indexed by allele, so each source slot moves to its published slot. */
static void ad_publish(FILE *out, const char *raw, size_t raw_length, const allele_map *map) {
    if (is_missing(raw, raw_length)) { fputs("null", out); return; }
    fputc('[', out);
    for (size_t j = 0; j < map->dict->count; ++j) {
        if (j) fputc(',', out);
        int source = map->pub_to_src[j];
        const char *start = NULL; size_t length = 0;
        if (source < 0 || !bounded_token(raw, raw_length, ',', (size_t)source, &start, &length)) {
            fputs("null", out);
            continue;
        }
        number_at(out, start, length);
    }
    fputc(']', out);
}

/*
 * PL is indexed by genotype combination.  Published slot j takes the source
 * slot naming the same genotype; a genotype the source never measured stays
 * null instead of being filled with zero.
 *
 * The plan walks the *source* genotypes (a handful, because a record carries at
 * most a few ALT) and maps each one forward into the published ordering, rather
 * than unranking every published slot of a possibly 17 allele dictionary for
 * every one of the 64 samples.
 */
static void pl_publish(FILE *out, const char *raw, size_t raw_length,
                       const allele_map *map, int ploidy, observation_scratch *scratch) {
    if (is_missing(raw, raw_length)) { fputs("null", out); return; }
    size_t slots = (size_t)genotype_slots(ploidy, (int)map->dict->count);
    size_t ranks = (size_t)genotype_slots(ploidy, map->source_alleles);
    if (!slots || !ranks) { fputs("null", out); return; }
    if (observation_scratch_reserve(scratch, (size_t)ploidy, ranks, slots)) {
        fputs("null", out);
        return;
    }
    for (size_t j = 0; j < slots; ++j) scratch->values[j].start = NULL;

    for (size_t r = 0; r < ranks; ++r) {
        genotype_unrank(r, ploidy, map->source_alleles, scratch->combo);
        for (int k = 0; k < ploidy; ++k)
            scratch->mapped[k] = (int)map->source_to_pub[scratch->combo[k]];
        /* the published index of an allele is not ordered like the source one,
           so the genotype has to be put back in non-decreasing order first */
        for (int a = 1; a < ploidy; ++a) {
            int value = scratch->mapped[a], b = a - 1;
            while (b >= 0 && scratch->mapped[b] > value) {
                scratch->mapped[b + 1] = scratch->mapped[b];
                --b;
            }
            scratch->mapped[b + 1] = value;
        }
        uint64_t slot = genotype_rank(scratch->mapped, ploidy);
        if (slot < slots) scratch->slot_of_rank[r] = (int)slot;
        else scratch->slot_of_rank[r] = -1;
    }

    size_t begin = 0;
    for (size_t r = 0; r < ranks; ++r) {
        size_t end = begin;
        while (end < raw_length && raw[end] != ',') ++end;
        int slot = scratch->slot_of_rank[r];
        if (slot >= 0) {
            scratch->values[slot].start = raw + begin;
            scratch->values[slot].length = end - begin;
        }
        if (end >= raw_length) break;
        begin = end + 1;
    }
    fputc('[', out);
    for (size_t j = 0; j < slots; ++j) {
        if (j) fputc(',', out);
        if (!scratch->values[j].start) fputs("null", out);
        else number_at(out, scratch->values[j].start, scratch->values[j].length);
    }
    fputc(']', out);
}

int observation_publish(FILE *out, const char *source_id, uint64_t ordinal,
                        const char *format, const char *column,
                        const allele_map *map, observation_scratch *scratch) {
    if (!format || !*format) format = ".";
    size_t ntags = field_count(format, ':');

    const char *gt = NULL; size_t gt_length = 0;
    for (size_t i = 0; i < ntags; ++i) {
        size_t length = 0;
        const char *tag = tag_at(format, i, &length);
        if (tag && length == 2 && !strncmp(tag, "GT", 2)) {
            list_token(column ? column : ".", ':', i, &gt, &gt_length);
            break;
        }
    }
    int ploidy = 2;
    if (gt && gt_length && gt_length < 32) {
        char buffer[32];
        memcpy(buffer, gt, gt_length);
        buffer[gt_length] = 0;
        ploidy = genotype_ploidy(buffer);
    }
    if (ploidy < 1) ploidy = 1;
    if (ploidy > 4) ploidy = 4;                /* the policy stops at tetraploid */

    fputs("{\"source\":", out); json_string(out, source_id);
    fprintf(out, ",\"ordinal\":%llu,\"format\":[", (unsigned long long)ordinal);
    int first = 1;
    for (size_t i = 0; i < ntags; ++i) {
        size_t length = 0;
        const char *tag = tag_at(format, i, &length);
        if (!tag || !length || (length == 1 && *tag == '.')) continue;
        char name[64];
        if (length >= sizeof(name)) continue;
        memcpy(name, tag, length); name[length] = 0;
        if (!first) fputc(',', out);
        first = 0;
        json_string(out, name);
    }
    fputs("],\"values\":{", out);
    first = 1;
    for (size_t i = 0; i < ntags; ++i) {
        size_t length = 0;
        const char *tag = tag_at(format, i, &length);
        if (!tag || !length || (length == 1 && *tag == '.')) continue;
        char name[64];
        if (length >= sizeof(name)) continue;
        memcpy(name, tag, length); name[length] = 0;
        const char *raw = NULL; size_t raw_length = 0;
        list_token(column ? column : ".", ':', i, &raw, &raw_length);
        if (!first) fputc(',', out);
        first = 0;
        json_string(out, name);
        fputc(':', out);
        if (!strcmp(name, "GT")) gt_publish(out, raw, raw_length, map);
        else if (!strcmp(name, "AD")) ad_publish(out, raw, raw_length, map);
        else if (!strcmp(name, "PL")) pl_publish(out, raw, raw_length, map, ploidy, scratch);
        else number_at(out, raw, raw_length);
    }
    fputs("}}", out);
    return ferror(out) ? -1 : 0;
}
