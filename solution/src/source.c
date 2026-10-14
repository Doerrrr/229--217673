#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

int line_compare(const char *a, const char *b) { return strcmp(a, b); }

/* Split in place on TAB, keeping empty fields so that positions stay aligned. */
static int split_tab(char *text, char ***out, size_t *count) {
    size_t used = 0, capacity = 16;
    char **fields = malloc(capacity * sizeof(*fields));
    if (!fields) return -1;
    char *field = text;
    for (;;) {
        if (used == capacity) {
            capacity *= 2;
            char **grown = realloc(fields, capacity * sizeof(*grown));
            if (!grown) { free(fields); return -1; }
            fields = grown;
        }
        fields[used++] = field;
        char *tab = strchr(field, '\t');
        if (!tab) break;
        *tab = 0;
        field = tab + 1;
    }
    *out = fields;
    *count = used;
    return 0;
}

static void number_after_comma(kstring_t *out, long long position) {
    ksprintf(out, "%012lld", position);
}

/*
 * One source record, rendered twice.
 *
 * The reduced line is the key the release view is built on: chromosome name,
 * zero padded numeric position, source priority and physical ordinal, then the
 * record as the source wrote it.  Sorting the whole line bytewise therefore
 * orders by (chromosome name, position, priority, ordinal), which is exactly
 * the release order, while the payload still carries everything the publish
 * step needs.
 */
int source_next(source *input, const selection *samples, kstring_t *line, kstring_t *plain) {
    int status = bcf_read(input->file, input->header, input->record);
    if (status == -1) return 0;                       /* clean end of stream */
    if (status < 0 || input->record->errcode) return -1;
    input->scratch.l = 0;
    if (vcf_format1(input->header, input->record, &input->scratch) < 0) return -1;
    while (input->scratch.l &&
           (input->scratch.s[input->scratch.l-1] == '\n' || input->scratch.s[input->scratch.l-1] == '\r'))
        input->scratch.s[--input->scratch.l] = 0;

    char **field = NULL; size_t nfield = 0;
    if (split_tab(input->scratch.s, &field, &nfield)) return -1;
    /* the fixed columns plus one column per declared sample */
    if (nfield < 9) { free(field); return -1; }

    uint64_t ordinal = input->ordinal++;
    long long position = input->record->pos + 1;

    if (line) {
        line->l = 0;
        kputs(field[0], line); kputc('\t', line);
        number_after_comma(line, position); kputc('\t', line);
        ksprintf(line, "%03u", input->rank); kputc('\t', line);
        ksprintf(line, "%012llu", (unsigned long long)ordinal); kputc('\t', line);
        kputs(field[3], line); kputc('\t', line);      /* REF */
        kputs(field[4], line); kputc('\t', line);      /* ALT */
        kputs(field[8], line);                         /* FORMAT */
        for (size_t s = 0; s < samples->count; ++s) {
            int slot = input->slots[s];
            kputc('\t', line);
            if (slot >= 0 && (size_t)(9 + slot) < nfield) kputs(field[9 + slot], line);
        }
        if (line->s == NULL) return -1;
    }

    if (plain) {
        plain->l = 0;
        kputs("{\"source\":", plain); json_string_ks(plain, input->id);
        ksprintf(plain, ",\"ordinal\":%llu,\"chrom\":", (unsigned long long)ordinal);
        json_string_ks(plain, field[0]);
        ksprintf(plain, ",\"position\":%lld,\"reference\":", position);
        json_string_ks(plain, field[3]);
        kputs(",\"alternate\":[", plain);
        if (strcmp(field[4], ".")) {
            const char *alt = field[4];
            int first = 1;
            for (;;) {
                const char *comma = strchr(alt, ',');
                size_t length = comma ? (size_t)(comma - alt) : strlen(alt);
                if (!first) kputc(',', plain);
                first = 0;
                char *piece = malloc(length + 1);
                if (!piece) return -1;
                memcpy(piece, alt, length); piece[length] = 0;
                json_string_ks(plain, piece);
                free(piece);
                if (!comma) break;
                alt = comma + 1;
            }
        }
        kputs("],\"format\":[", plain);
        {
            const char *tag = field[8];
            int first = 1;
            if (strcmp(tag, ".")) {
                for (;;) {
                    const char *colon = strchr(tag, ':');
                    size_t length = colon ? (size_t)(colon - tag) : strlen(tag);
                    if (length) {
                        if (!first) kputc(',', plain);
                        first = 0;
                        char *piece = malloc(length + 1);
                        if (!piece) return -1;
                        memcpy(piece, tag, length); piece[length] = 0;
                        json_string_ks(plain, piece);
                        free(piece);
                    }
                    if (!colon) break;
                    tag = colon + 1;
                }
            }
        }
        kputs("],\"samples\":[", plain);
        int first_sample = 1;
        for (size_t s = 0; s < samples->count; ++s) {
            int slot = input->slots[s];
            if (slot < 0) continue;                    /* not carried here at all */
            if (!first_sample) kputc(',', plain);
            first_sample = 0;
            kputs("{\"name\":", plain); json_string_ks(plain, samples->items[s]);
            kputs(",\"values\":", plain);
            if (observation_plain_ks(plain, field[8],
                                     (size_t)(9 + slot) < nfield ? field[9 + slot] : ".")) return -1;
            kputc('}', plain);
        }
        kputs("]}", plain);
        if (plain->s == NULL) return -1;
    }

    free(field);
    return 1;
}
