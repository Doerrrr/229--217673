#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>

/*
   Published dictionary: the union of the ALT lists of every record contributing to
   one key, in the order in which the alleles first appear (contributors are ordered
   by batch priority and then by record ordinal).  No particular arrangement is
   mandated by the exchange record, but every observation has to be expressed in
   this dictionary so that a source's own allele numbering cannot change the allele
   or genotype an observation stands for.
*/
int locus_find(const locus *value, const char *alt) {
    for (size_t i = 0; i < value->nalt; ++i) if (!strcmp(value->alts[i], alt)) return (int)i;
    return -1;
}

int locus_open(frame_list *items, locus *out) {
    memset(out, 0, sizeof(*out));
    out->items = items->items; out->count = items->count;
    for (size_t i = 0; i < items->count; ++i) {
        if (!strcmp(items->items[i]->columns[4], ".")) continue;
        char *text = strdup(items->items[i]->columns[4]), *save = NULL;
        if (!text) { locus_close(out); return -1; }
        for (char *alt = strtok_r(text, ",", &save); alt; alt = strtok_r(NULL, ",", &save)) {
            if (locus_find(out, alt) >= 0) continue;
            char **next = realloc(out->alts, (out->nalt+1) * sizeof(*next));
            if (!next) { free(text); locus_close(out); return -1; }
            out->alts = next;
            out->alts[out->nalt] = strdup(alt);
            if (!out->alts[out->nalt]) { free(text); locus_close(out); return -1; }
            ++out->nalt;
        }
        free(text);
    }
    return 0;
}

void locus_close(locus *value) {
    for (size_t i = 0; i < value->nalt; ++i) free(value->alts[i]);
    free(value->alts); memset(value, 0, sizeof(*value));
}

/* ploidy declared by the GT string used by one observation */
int locus_ploidy(const char *gt) {
    if (!gt || !*gt) return -1;
    int ploidy = 0;
    for (const char *p = gt; *p; ) {
        if (*p == '/' || *p == '|') { ++p; continue; }
        if (*p == '.') ++p;
        else while (*p >= '0' && *p <= '9') ++p;
        ++ploidy;
    }
    return ploidy;
}

static int64_t choose_(int64_t n, int64_t k) {
    if (k < 0 || n < 0 || k > n) return 0;
    if (k > n - k) k = n - k;
    int64_t result = 1;
    for (int64_t i = 1; i <= k; ++i) {
        if (result > (INT64_MAX - 1) / (n - k + i)) return INT64_MAX/2;   /* far outside the supported domain */
        result = result * (n - k + i) / i;
    }
    return result;
}

/* number of genotypes for the given ploidy and allele count, i.e. C(alleles+ploidy-1, ploidy) */
int64_t locus_genotype_count(int ploidy, size_t alleles) {
    if (ploidy < 1) return 0;
    return choose_((int64_t)alleles + ploidy - 1, ploidy);
}

/* index of a genotype, alleles[] non-decreasing and 0-based */
int64_t locus_genotype_index(int ploidy, const int *alleles) {
    if (ploidy <= 1) return alleles[0];
    int top = alleles[ploidy-1];
    int64_t index = 0;
    for (int j = 0; j < top; ++j) index += choose_(j + ploidy - 1, ploidy - 1);
    return index + locus_genotype_index(ploidy-1, alleles);
}

/* inverse of locus_genotype_index: fill out[] with the non-decreasing allele multiset */
void locus_genotype_alleles(int ploidy, size_t alleles, int64_t index, int *out) {
    if (ploidy <= 1) { out[0] = (int)index; return; }
    size_t top = 0;
    for (; top < alleles; ++top) {
        int64_t block = choose_((int64_t)top + ploidy - 1, ploidy - 1);
        if (index < block) break;
        index -= block;
    }
    out[ploidy-1] = (int)top;
    locus_genotype_alleles(ploidy-1, top+1, index, out);
}
