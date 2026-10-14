#define _POSIX_C_SOURCE 200809L
#include "cohort.h"
#include <stdlib.h>
#include <string.h>
#if defined(__GLIBC__)
#include <malloc.h>
#endif

#define SPOOL_LIMIT (8u * 1024u * 1024u)

/*
 * A position can carry tens of megabytes of record text.  Freed blocks of that
 * size are kept in the arena by default, so the resident set would otherwise
 * reflect the largest amount of text ever held rather than what is held now.
 */
static void release_memory(void) {
#if defined(__GLIBC__)
    malloc_trim(0);
#endif
}

static int copy_stream(FILE *source, FILE *out) {
    if (fflush(source) || fseek(source, 0, SEEK_SET)) return -1;
    unsigned char buffer[65536];
    size_t got;
    while ((got = fread(buffer, 1, sizeof(buffer), source)) > 0)
        if (fwrite(buffer, 1, got, out) != got) return -1;
    if (ferror(source)) return -1;
    return fflush(out) || ferror(out) ? -1 : 0;
}

static void usage(void) {
    fputs("usage: cohort-release --manifest BATCHES.tsv --samples NAME,...\n"
          "       cohort-release --manifest BATCHES.tsv --samples NAME,..."
          " --release-out FILE --original-out FILE\n", stderr);
}

int main(int argc, char **argv) {
    const char *manifest_path = NULL, *sample_text = NULL;
    const char *release_path = NULL, *original_path = NULL;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--manifest") && i + 1 < argc) manifest_path = argv[++i];
        else if (!strcmp(argv[i], "--samples") && i + 1 < argc) sample_text = argv[++i];
        else if (!strcmp(argv[i], "--release-out") && i + 1 < argc) release_path = argv[++i];
        else if (!strcmp(argv[i], "--original-out") && i + 1 < argc) original_path = argv[++i];
        else { usage(); return EXIT_USAGE; }
    }
    if (!manifest_path || !sample_text) { usage(); return EXIT_USAGE; }
    if ((release_path == NULL) != (original_path == NULL)) { usage(); return EXIT_USAGE; }

    manifest inputs = {0};
    selection samples = {0};
    record_spool spool = {0};
    record_cursor cursor = {0};
    kstring_t line = {0}, plain = {0};
    locus group;
    locus_init(&group);
    FILE *release = NULL, *original = NULL, *staged = NULL;
    int status = EXIT_IO;
    int cursor_open_done = 0;
    unsigned long long published = 0;

    if (selection_parse(sample_text, &samples)) { fputs("invalid sample selection\n", stderr); status = EXIT_USAGE; goto done; }
    status = manifest_load(manifest_path, &inputs);
    if (status) { fputs("cannot open manifest or source header\n", stderr); goto done; }

    for (size_t s = 0; s < samples.count; ++s) {
        int present = 0;
        for (size_t i = 0; i < inputs.count; ++i)
            if (bcf_hdr_id2int(inputs.items[i]->header, BCF_DT_SAMPLE, samples.items[s]) >= 0) present = 1;
        if (!present) {
            fputs("requested sample absent from every source header\n", stderr);
            status = EXIT_SAMPLE; goto done;
        }
    }
    for (size_t i = 0; i < inputs.count; ++i)
        if (source_bind(inputs.items[i], &samples)) { fputs("out of memory\n", stderr); status = EXIT_IO; goto done; }

    if (release_path) {
        release = fopen(release_path, "wb");
        if (!release) { fputs("cannot create the release view\n", stderr); status = EXIT_IO; goto done; }
        original = fopen(original_path, "wb");
        if (!original) { fputs("cannot create the original view\n", stderr); status = EXIT_IO; goto done; }
    } else {
        staged = tmpfile();
        if (!staged) { fputs("cannot stage the release\n", stderr); status = EXIT_IO; goto done; }
        release = staged;
    }

    if (spool_open(&spool, SPOOL_LIMIT)) { fputs("cannot prepare the spool\n", stderr); status = EXIT_IO; goto done; }

    /*
     * One pass over the sources.  The original view is emitted here, in
     * manifest order and physical order, exactly as each source wrote it; the
     * reduced lines are collected for the ordered release pass below.
     */
    for (size_t i = 0; i < inputs.count; ++i) {
        int outcome;
        while ((outcome = source_next(inputs.items[i], &samples, &line, original ? &plain : NULL)) == 1) {
            if (original) {
                if (fwrite(plain.s, 1, plain.l, original) != plain.l) {
                    fputs("cannot write the original view\n", stderr); status = EXIT_IO; goto done;
                }
                if (fputc('\n', original) == EOF) {
                    fputs("cannot write the original view\n", stderr); status = EXIT_IO; goto done;
                }
            }
            if (spool_add(&spool, line.s)) { fputs("cannot buffer a source record\n", stderr); status = EXIT_IO; goto done; }
        }
        if (outcome < 0) { fputs("source record cannot be read or parsed\n", stderr); status = EXIT_RECORD; goto done; }
    }
    if (original && (fflush(original) || ferror(original))) {
        fputs("cannot write the original view\n", stderr); status = EXIT_IO; goto done;
    }
    manifest_release_readers(&inputs);
    if (spool_finish(&spool)) { fputs("cannot order the source records\n", stderr); status = EXIT_IO; goto done; }
    if (cursor_open(&cursor, &spool)) { fputs("cannot open the ordered stream\n", stderr); status = EXIT_IO; goto done; }
    cursor_open_done = 1;

    /* Second pass: one release row per (chromosome, position). */
    for (;;) {
        const char *next = cursor_next(&cursor);
        if (cursor.failed) { fputs("cannot read the ordered stream\n", stderr); status = EXIT_IO; goto done; }
        if (!next) break;
        if (group.count && !locus_same_key(&group, next)) {
            if (locus_coordinate(&group)) {
                fputs("reference spans at one position are incompatible\n", stderr);
                status = EXIT_RECORD; goto done;
            }
            allele_list dict;
            if (locus_dictionary(&group, &dict)) { fputs("out of memory\n", stderr); status = EXIT_IO; goto done; }
            size_t held = group.count;
            int failed = locus_publish(release, &group, &dict, &samples);
            allele_list_free(&dict);
            locus_free(&group);
            if (failed) { fputs("cannot write the release view\n", stderr); status = EXIT_IO; goto done; }
            if (held >= 8 || ++published % 4096 == 0) release_memory();
        }
        if (locus_add(&group, (char *)next, &samples, &inputs)) {
            fputs("malformed buffered record\n", stderr); status = EXIT_RECORD; goto done;
        }
    }
    if (group.count) {
        if (locus_coordinate(&group)) {
            fputs("reference spans at one position are incompatible\n", stderr);
            status = EXIT_RECORD; goto done;
        }
        allele_list dict;
        if (locus_dictionary(&group, &dict)) { fputs("out of memory\n", stderr); status = EXIT_IO; goto done; }
        int failed = locus_publish(release, &group, &dict, &samples);
        allele_list_free(&dict);
        if (failed) { fputs("cannot write the release view\n", stderr); status = EXIT_IO; goto done; }
    }

    if (release_path) {
        if (fflush(release) || ferror(release)) { fputs("cannot write the release view\n", stderr); status = EXIT_IO; goto done; }
        status = 0;
    } else {
        /* Nothing reaches stdout until the whole release is known to be good. */
        if (copy_stream(staged, stdout)) { fputs("cannot deliver the release\n", stderr); status = EXIT_IO; goto done; }
        status = 0;
    }

done:
    locus_free(&group);
    if (cursor_open_done) cursor_close(&cursor);
    spool_close(&spool);
    if (release_path) {
        if (release) fclose(release);
        if (original) fclose(original);
    } else if (staged) {
        fclose(staged);
    }
    free(line.s);
    free(plain.s);
    selection_close(&samples);
    manifest_close(&inputs);
    return status;
}
