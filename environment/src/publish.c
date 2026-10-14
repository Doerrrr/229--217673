#include "cohort.h"
#include <stdlib.h>

int locus_publish(FILE *out, const locus *value, const selection *samples) {
    const frame *first = value->items[0];
    fputs("{\"chrom\":", out); json_string(out, first->columns[0]);
    fprintf(out, ",\"position\":%lld,\"reference\":", (long long)first->position);
    json_string(out, first->columns[3]); fputs(",\"alternate\":[", out);
    for (size_t i = 0; i < value->nalt; ++i) { if (i) fputc(',', out); json_string(out, value->alts[i]); }
    fputs("],\"contributors\":[", out);
    for (size_t i = 0; i < value->count; ++i) {
        if (i) fputc(',', out);
        fputs("{\"source\":", out); json_string(out, value->items[i]->origin->id);
        fprintf(out, ",\"ordinal\":%llu}", (unsigned long long)value->items[i]->ordinal);
    }
    fputs("],\"samples\":[", out);
    for (size_t s = 0; s < samples->count; ++s) {
        if (s) fputc(',', out);
        fputs("{\"name\":", out); json_string(out, samples->items[s]); fputs(",\"winner\":", out);
        size_t winner = value->count;
        for (size_t i = 0; i < value->count; ++i) {
            int slot = bcf_hdr_id2int(value->items[i]->origin->header, BCF_DT_SAMPLE, samples->items[s]);
            if (slot >= 0) winner = i;
        }
        if (winner == value->count) fputs("null", out);
        else {
            frame *f = value->items[winner];
            if (fields_publish(out, f, bcf_hdr_id2int(f->origin->header, BCF_DT_SAMPLE, samples->items[s]))) return -1;
        }
        fputs(",\"others\":[", out); int emitted = 0;
        for (size_t i = 0; i < value->count; ++i) {
            if (i == winner) continue;
            frame *f = value->items[i];
            int slot = bcf_hdr_id2int(f->origin->header, BCF_DT_SAMPLE, samples->items[s]);
            if (slot < 0) continue;
            if (emitted++) fputc(',', out);
            if (fields_publish(out, f, slot)) return -1;
        }
        fputs("]}", out);
    }
    fputs("]}\n", out);
    return ferror(out) ? -1 : 0;
}
