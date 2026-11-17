/*
 * Prints the protocol reference vectors as produced by the firmware encoder.
 * `make vectors-check` diffs this output against protocol/vectors/v1.txt, which
 * the Python and TypeScript clients also test against, so all three
 * implementations are pinned to the same bytes.
 */
#include <stdio.h>
#include <string.h>

#include "fenrir/protocol.h"

static void hex(const char *name, const uint8_t *b, size_t n)
{
    printf("%s ", name);
    for (size_t i = 0; i < n; i++) printf("%02x", b[i]);
    printf("\n");
}

int main(void)
{
    uint8_t buf[300];
    fenrir_sample_t s[4] = { { 1000, 0 }, { 108374, 10000 }, { -5, -1 }, { 8388607, FENRIR_FORCE_INVALID } };
    fenrir_force_header_t h = { 7, 1234567890u, 11111, FENRIR_ST_STREAMING | FENRIR_ST_CAL_VALID | FENRIR_ST_TARED,
                                FENRIR_FMT_RAW_FORCE, 4 };
    hex("force_raw", buf, fenrir_force_encode(buf, sizeof buf, &h, s));
    h.format = FENRIR_FMT_FORCE;
    h.seq = 65535;
    h.dt_us = 2857;
    h.status = FENRIR_ST_STREAMING | FENRIR_ST_OVERLOAD | FENRIR_ST_FILTERED;
    hex("force_only", buf, fenrir_force_encode(buf, sizeof buf, &h, s));

    fenrir_status_t st = { FENRIR_STATE_STREAMING, 0, FENRIR_ST_STREAMING | FENRIR_ST_CAL_VALID, 87, 4012, 90,
                           FENRIR_FILTER_IIR, 2, 3600 };
    hex("status", buf, fenrir_status_encode(buf, sizeof buf, &st));

    fenrir_calinfo_t ci = { 1, 5, 490, 0.000931322574615479f /* 2^-30 * 1e6, exact in f32 */, -20000, 150, 1794000000u };
    hex("calinfo", buf, fenrir_calinfo_encode(buf, sizeof buf, &ci));

    hex("response", buf, fenrir_response_encode(buf, sizeof buf, FENRIR_OP_TARE, FENRIR_RES_BAD_STATE));
    return 0;
}
