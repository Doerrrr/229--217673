HTSLIB ?= /work/bcftools-1.20/htslib-1.20
CFLAGS ?= -O2 -std=c11 -Wall -Wextra
SOURCES := $(wildcard src/*.c)

all: cohort-native cohort-release

cohort-native: $(SOURCES) src/cohort.h
	$(CC) $(CFLAGS) -I$(HTSLIB) -Isrc $(SOURCES) $(HTSLIB)/libhts.a -lz -lbz2 -llzma -lm -lpthread -o $@

cohort-release: bin/cohort-release app/store.py
	cp bin/cohort-release cohort-release
	chmod 755 cohort-release

.PHONY: all clean
clean:
	rm -f cohort-native cohort-release
