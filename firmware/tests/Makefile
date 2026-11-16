CC ?= gcc
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror -O1 -g \
          -fsanitize=address,undefined -fno-sanitize-recover=all
INC = -I../include
CORE = ../src/core/protocol.c ../src/core/measure.c ../src/core/nau7802.c
VECTORS = ../../protocol/vectors/v1.txt
BUILD ?= /tmp/fenrir-build

.PHONY: test vectors-check vectors clean
test: $(BUILD)/test_core vectors-check
	$(BUILD)/test_core

$(BUILD)/test_core: test_core.c $(CORE)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ test_core.c $(CORE) -lm

$(BUILD)/gen_vectors: gen_vectors.c $(CORE)
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(INC) -o $@ gen_vectors.c $(CORE) -lm

vectors-check: $(BUILD)/gen_vectors
	$(BUILD)/gen_vectors | diff -u --strip-trailing-cr $(VECTORS) -

# Regenerate the reference vectors (only after an intentional protocol change).
vectors: $(BUILD)/gen_vectors
	$(BUILD)/gen_vectors > $(VECTORS)

clean:
	rm -rf $(BUILD)
