#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

#define POSITION_WIDTH 12

void locus_init(locus *value) { memset(value, 0, sizeof(*value)); }

void locus_free(locus *value) {
    for (size_t i = 0; i < value->count; ++i) {
        locus_record *record = &value->records[i];
        for (size_t k = 0; k < record->ncoord; ++k) free(record->coord[k]);
        free(record->coord);
        free(record->columns);
        free(record->line);
    }
    free(value->records);
    free(value->target_ref);
    free(value->chrom);
    memset(value, 0, sizeof(*value));
}

/* chromosome name and numeric position of a reduced line, without mutating it */
static int parse_prefix(const char *line, const char **chrom, size_t *chrom_len,
                        long long *position) {
    const char *tab = strchr(line, '\t');
    if (!tab || tab == line) return -1;
    *chrom = line;
    *chrom_len = (size_t)(tab - line);
    const char *pos = tab + 1;
    const char *end = strchr(pos, '\t');
    if (!end || (size_t)(end - pos) != POSITION_WIDTH) return -1;
    long long value = 0;
    for (const char *p = pos; p < end; ++p) {
        if (*p < '0' || *p > '9') return -1;
        value = value * 10 + (*p - '0');
    }
    *position = value;
    return 0;
}

int locus_same_key(const locus *value, const char *line) {
    const char *chrom; size_t chrom_len; long long position;
    if (parse_prefix(line, &chrom, &chrom_len, &position)) return 0;
    return chrom_len == strlen(value->chrom) &&
           !memcmp(chrom, value->chrom, chrom_len) &&
           position == value->position;
}

/*
 * Take over one reduced line as a member of this position.  The line is copied
 * and split in place so the record keeps its own storage: the merge cursor
 * reuses its buffer on the very next call.
 */
int locus_add(locus *value, char *line, const selection *samples, manifest *inputs) {
    const char *chrom; size_t chrom_len; long long position;
    if (parse_prefix(line, &chrom, &chrom_len, &position)) return -1;

    char *copy = strdup(line);
    if (!copy) return -1;
    size_t nfield = 1;
    for (char *p = copy; *p; ++p) if (*p == '\t') ++nfield;
    if (nfield < 7 + samples->count) { free(copy); return -1; }

    if (value->count == value->capacity) {
        size_t capacity = value->capacity ? value->capacity * 2 : 8;
        locus_record *grown = realloc(value->records, capacity * sizeof(*grown));
        if (!grown) { free(copy); return -1; }
        value->records = grown;
        value->capacity = capacity;
    }
    char **field = malloc(nfield * sizeof(*field));
    char **columns = calloc(samples->count ? samples->count : 1, sizeof(*columns));
    if (!field || !columns) { free(field); free(columns); free(copy); return -1; }

    size_t used = 0;
    char *walk = copy;
    for (;;) {
        field[used++] = walk;
        char *tab = strchr(walk, '\t');
        if (!tab) break;
        *tab = 0;
        walk = tab + 1;
    }

    unsigned rank = (unsigned)strtoul(field[2], NULL, 10);
    locus_record *record = &value->records[value->count];
    memset(record, 0, sizeof(*record));
    record->line = copy;
    record->chrom = field[0];
    record->position = position;
    record->rank = rank;
    record->source_id = rank < inputs->count ? inputs->items[rank]->id : NULL;
    record->ordinal = strtoull(field[3], NULL, 10);
    record->ref = field[4];
    record->alt = field[5];
    record->format = field[6];
    record->columns = columns;
    for (size_t s = 0; s < samples->count; ++s)
        record->columns[s] = field[7 + s][0] ? field[7 + s] : NULL;
    free(field);

    if (!value->count) {
        value->chrom = malloc(chrom_len + 1);
        if (!value->chrom) return -1;
        memcpy(value->chrom, chrom, chrom_len);
        value->chrom[chrom_len] = 0;
        value->position = position;
    }
    ++value->count;
    return 0;
}

/*
 * Coordinate the reference spans of one position: the longest REF wins, every
 * shorter REF must be its exact prefix, and the suffix that a shorter REF does
 * not cover is appended to that record's REF *and* to each of its ALTs.
 */
int locus_coordinate(locus *value) {
    size_t best = 0;
    for (size_t i = 1; i < value->count; ++i)
        if (strlen(value->records[i].ref) > strlen(value->records[best].ref)) best = i;
    const char *target = value->records[best].ref;
    size_t target_len = strlen(target);
    if (!target_len) return -1;

    for (size_t i = 0; i < value->count; ++i) {
        const char *ref = value->records[i].ref;
        if (strncmp(target, ref, strlen(ref))) return -1;              /* not a prefix */
        if (strlen(ref) == target_len && strcmp(target, ref)) return -1; /* same length, different */
    }

    free(value->target_ref);
    value->target_ref = strdup(target);
    if (!value->target_ref) return -1;

    for (size_t i = 0; i < value->count; ++i) {
        locus_record *record = &value->records[i];
        const char *suffix = target + strlen(record->ref);
        for (size_t k = 0; k < record->ncoord; ++k) free(record->coord[k]);
        free(record->coord);
        record->coord = NULL;
        record->ncoord = 0;
        if (!strcmp(record->alt, ".")) continue;                       /* REF-only record */
        char *text = strdup(record->alt);
        if (!text) return -1;
        size_t capacity = 0;
        int failed = 0;
        for (char *token = text;;) {
            char *comma = strchr(token, ',');
            if (comma) *comma = 0;
            if (record->ncoord == capacity) {
                capacity = capacity ? capacity * 2 : 4;
                char **grown = realloc(record->coord, capacity * sizeof(*grown));
                if (!grown) { failed = 1; break; }
                record->coord = grown;
            }
            size_t length = strlen(token) + strlen(suffix);
            char *joined = malloc(length + 1);
            if (!joined) { failed = 1; break; }
            strcpy(joined, token);
            strcat(joined, suffix);
            record->coord[record->ncoord++] = joined;
            if (!comma) break;
            token = comma + 1;
        }
        free(text);
        if (failed) return -1;
    }
    return 0;
}

/* The published dictionary: the coordinated REF plus every coordinated ALT. */
int locus_dictionary(locus *value, allele_list *dict) {
    allele_list_init(dict);
    if (allele_list_add(dict, value->target_ref)) return -1;
    for (size_t i = 0; i < value->count; ++i)
        for (size_t k = 0; k < value->records[i].ncoord; ++k)
            if (allele_list_add(dict, value->records[i].coord[k])) return -1;
    return 0;
}

/* How one record's own dictionary maps onto the published one. */
static int build_map(const locus_record *record, const allele_list *dict, allele_map *map) {
    map->dict = dict;
    map->source_alleles = (int)record->ncoord + 1;
    map->source_to_pub = malloc((size_t)map->source_alleles * sizeof(*map->source_to_pub));
    map->pub_to_src = malloc((dict->count ? dict->count : 1) * sizeof(*map->pub_to_src));
    if (!map->source_to_pub || !map->pub_to_src) return -1;
    map->source_to_pub[0] = 0;                       /* the record's REF is the target REF */
    for (size_t k = 0; k < record->ncoord; ++k) {
        int index = allele_list_index(dict, record->coord[k]);
        if (index < 0) return -1;
        map->source_to_pub[k + 1] = (size_t)index;
    }
    for (size_t j = 0; j < dict->count; ++j) {
        int source = (j == 0) ? 0 : -1;
        for (size_t k = 0; k < record->ncoord && source < 0; ++k)
            if (!strcmp(record->coord[k], dict->items[j])) source = (int)k + 1;
        map->pub_to_src[j] = source;
    }
    return 0;
}

int locus_publish(FILE *out, const locus *value, const allele_list *dict,
                  const selection *samples) {
    allele_map *maps = calloc(value->count ? value->count : 1, sizeof(*maps));
    observation_scratch scratch;
    memset(&scratch, 0, sizeof(scratch));
    if (!maps) return -1;
    int failed = 0;
    for (size_t i = 0; i < value->count && !failed; ++i)
        if (build_map(&value->records[i], dict, &maps[i])) failed = 1;

    if (!failed) {
        fputs("{\"chrom\":", out); json_string(out, value->chrom);
        fprintf(out, ",\"position\":%lld,\"reference\":", value->position);
        json_string(out, value->target_ref);
        fputs(",\"alternate\":[", out);
        for (size_t i = 1; i < dict->count; ++i) {
            if (i > 1) fputc(',', out);
            json_string(out, dict->items[i]);
        }
        fputs("],\"contributors\":[", out);
        for (size_t i = 0; i < value->count; ++i) {
            if (i) fputc(',', out);
            fputs("{\"source\":", out);
            json_string(out, value->records[i].source_id ? value->records[i].source_id : "?");
            fprintf(out, ",\"ordinal\":%llu}", (unsigned long long)value->records[i].ordinal);
        }
        fputs("],\"samples\":[", out);
        for (size_t s = 0; s < samples->count && !failed; ++s) {
            if (s) fputc(',', out);
            fputs("{\"name\":", out); json_string(out, samples->items[s]);
            fputs(",\"winner\":", out);
            size_t winner = value->count;
            for (size_t i = 0; i < value->count; ++i)
                if (value->records[i].columns[s]) { winner = i; break; }
            if (winner == value->count) fputs("null", out);
            else {
                const locus_record *record = &value->records[winner];
                if (observation_publish(out, record->source_id ? record->source_id : "?",
                                        record->ordinal, record->format,
                                        record->columns[s], &maps[winner], &scratch)) failed = 1;
            }
            if (!failed) {
                fputs(",\"others\":[", out);
                int emitted = 0;
                for (size_t i = 0; i < value->count; ++i) {
                    if (i == winner || !value->records[i].columns[s]) continue;
                    const locus_record *record = &value->records[i];
                    if (emitted++) fputc(',', out);
                    if (observation_publish(out, record->source_id ? record->source_id : "?",
                                            record->ordinal, record->format,
                                            record->columns[s], &maps[i], &scratch)) { failed = 1; break; }
                }
                fputs("]}", out);
            }
        }
        if (!failed) { fputs("]}\n", out); if (ferror(out)) failed = 1; }
    }

    observation_scratch_free(&scratch);
    for (size_t i = 0; i < value->count; ++i) {
        free(maps[i].source_to_pub);
        free(maps[i].pub_to_src);
    }
    free(maps);
    return failed ? -1 : 0;
}
