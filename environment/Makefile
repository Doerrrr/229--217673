HTSLIB ?= /work/bcftools-1.20/htslib-1.20
CFLAGS ?= -O2 -std=c11 -Wall -Wextra
SOURCES := $(wildcard src/*.c)

cohort-release: $(SOURCES) src/cohort.h
	$(CC) $(CFLAGS) -I$(HTSLIB) -Isrc $(SOURCES) $(HTSLIB)/libhts.a -lz -lbz2 -llzma -lm -lpthread -o $@

.PHONY: clean
clean:
	rm -f cohort-release
