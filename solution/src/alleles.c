#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------ allele list */
void allele_list_init(allele_list *value) { memset(value, 0, sizeof(*value)); }

void allele_list_free(allele_list *value) {
    for (size_t i = 0; i < value->count; ++i) free(value->items[i]);
    free(value->items);
    memset(value, 0, sizeof(*value));
}

int allele_list_index(const allele_list *value, const char *text) {
    for (size_t i = 0; i < value->count; ++i)
        if (!strcmp(value->items[i], text)) return (int)i;
    return -1;
}

int allele_list_add(allele_list *value, const char *text) {
    if (allele_list_index(value, text) >= 0) return 0;
    char **grown = realloc(value->items, (value->count + 1) * sizeof(*grown));
    if (!grown) return -1;
    value->items = grown;
    value->items[value->count] = strdup(text);
    if (!value->items[value->count]) return -1;
    ++value->count;
    return 0;
}

/* ------------------------------------------------------- genotype algebra */
static uint64_t binomial(uint64_t n, uint64_t k) {
    if (k > n) return 0;
    if (k > n - k) k = n - k;
    uint64_t result = 1;
    for (uint64_t i = 1; i <= k; ++i) result = result * (n - k + i) / i;
    return result;
}

uint64_t genotype_slots(int ploidy, int alleles) {
    if (ploidy < 1 || alleles < 1) return 0;
    return binomial((uint64_t)alleles + (uint64_t)ploidy - 1, (uint64_t)ploidy);
}

/* Co-lexicographic combination index, as VCF orders Number=G values. */
uint64_t genotype_rank(const int *alleles, int ploidy) {
    uint64_t rank = 0;
    for (int i = 0; i < ploidy; ++i)
        rank += binomial((uint64_t)alleles[i] + (uint64_t)i, (uint64_t)i + 1);
    return rank;
}

void genotype_unrank(uint64_t rank, int ploidy, int alleles, int *out) {
    uint64_t remaining = rank;
    for (int i = ploidy - 1; i >= 0; --i) {
        int chosen = 0;
        for (int a = alleles - 1; a >= 0; --a) {
            uint64_t value = binomial((uint64_t)a + (uint64_t)i, (uint64_t)i + 1);
            if (value <= remaining) { chosen = a; remaining -= value; break; }
        }
        out[i] = chosen;
    }
}

int genotype_ploidy(const char *gt) {
    if (!gt || !*gt || !strcmp(gt, ".")) return 1;
    int ploidy = 1;
    for (const char *p = gt; *p; ++p)
        if (*p == '/' || *p == '|') ++ploidy;
    return ploidy;
}
