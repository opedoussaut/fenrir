#include "fenrir/ads1220.h"

/* RESET needs 50 us + 32 tCLK (4.096 MHz internal oscillator, ~8 us); 100 us leaves margin. */
#define RESET_WAIT_US 100u

bool ads1220_rate_supported(uint16_t sps)
{
    return sps == 90 || sps == 350;
}

static uint8_t reg1_for(uint16_t sps)
{
    return (uint8_t)(ADS1220_REG1_TURBO_CONT | (sps == 90 ? ADS1220_DR_TURBO_90 : ADS1220_DR_TURBO_350));
}

static ads1220_result_t command(const ads1220_bus_t *b, uint8_t cmd)
{
    return b->transfer(b->ctx, &cmd, NULL, 1) ? ADS1220_OK : ADS1220_ERR_BUS;
}

/* Write registers [first, first + n) and read them back. SPI has no acknowledge, so the
 * read-back is the only way to tell a working device from an open or shorted bus. */
static ads1220_result_t write_verify(const ads1220_bus_t *b, uint8_t first, const uint8_t *val, uint8_t n)
{
    uint8_t tx[5] = { ADS1220_CMD_WREG(first, n), 0, 0, 0, 0 };
    for (uint8_t i = 0; i < n; i++) tx[1 + i] = val[i];
    if (!b->transfer(b->ctx, tx, NULL, (size_t)(n + 1))) return ADS1220_ERR_BUS;

    uint8_t q[5] = { ADS1220_CMD_RREG(first, n), 0, 0, 0, 0 };
    uint8_t r[5] = { 0 };
    if (!b->transfer(b->ctx, q, r, (size_t)(n + 1))) return ADS1220_ERR_BUS;
    for (uint8_t i = 0; i < n; i++)
        if (r[1 + i] != val[i]) return ADS1220_ERR_VERIFY;
    return ADS1220_OK;
}

ads1220_result_t ads1220_init(const ads1220_bus_t *b, uint16_t sps)
{
    if (!ads1220_rate_supported(sps)) return ADS1220_ERR_PARAM;
    ads1220_result_t r = command(b, ADS1220_CMD_RESET);
    if (r != ADS1220_OK) return r;
    b->delay_us(b->ctx, RESET_WAIT_US);
    const uint8_t cfg[4] = { ADS1220_REG0_AIN0_AIN1_G128, reg1_for(sps), ADS1220_REG2_EXTREF0,
                             ADS1220_REG3_DEFAULT };
    r = write_verify(b, 0, cfg, 4);
    if (r != ADS1220_OK) return r;
    /* In continuous mode START/SYNC is sent once; conversions then run on their own. */
    return command(b, ADS1220_CMD_START);
}

ads1220_result_t ads1220_set_rate(const ads1220_bus_t *b, uint16_t sps)
{
    if (!ads1220_rate_supported(sps)) return ADS1220_ERR_PARAM;
    const uint8_t v = reg1_for(sps);
    ads1220_result_t r = write_verify(b, 1, &v, 1);
    if (r != ADS1220_OK) return r;
    /* Restart so that no conversion straddles the change. */
    return command(b, ADS1220_CMD_START);
}

ads1220_result_t ads1220_read(const ads1220_bus_t *b, int32_t *raw)
{
    if (!b->data_ready(b->ctx)) return ADS1220_NOT_READY;
    /* With DRDY low, 24 SCLKs shift out the result MSB first; DIN is held low. */
    const uint8_t tx[3] = { 0, 0, 0 };
    uint8_t d[3];
    if (!b->transfer(b->ctx, tx, d, 3)) return ADS1220_ERR_BUS;
    uint32_t u = ((uint32_t)d[0] << 16) | ((uint32_t)d[1] << 8) | d[2];
    if (u & 0x800000u) u |= 0xFF000000u; /* two's complement, sign-extend to 32 bits */
    *raw = (int32_t)u;
    return ADS1220_OK;
}

ads1220_result_t ads1220_power_down(const ads1220_bus_t *b)
{
    return command(b, ADS1220_CMD_POWERDOWN);
}
