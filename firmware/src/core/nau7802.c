#include "fenrir/nau7802.h"

static nau7802_result_t update(const nau7802_bus_t *b, uint8_t reg, uint8_t mask, uint8_t value)
{
    uint8_t v;
    if (!b->read(b->ctx, reg, &v, 1)) return NAU7802_ERR_BUS;
    v = (uint8_t)((v & ~mask) | (value & mask));
    return b->write(b->ctx, reg, v) ? NAU7802_OK : NAU7802_ERR_BUS;
}

static nau7802_result_t calibrate_offset(const nau7802_bus_t *b)
{
    /* CALMOD = 00 (internal offset), CALS = 1; CALS self-clears when done. */
    nau7802_result_t r = update(b, NAU7802_REG_CTRL2, 0x07, NAU7802_CTRL2_CALS);
    if (r != NAU7802_OK) return r;
    for (int i = 0; i < 200; i++) { /* up to ~1 s; takes a few conversions */
        uint8_t v;
        b->delay_ms(b->ctx, 5);
        if (!b->read(b->ctx, NAU7802_REG_CTRL2, &v, 1)) return NAU7802_ERR_BUS;
        if (!(v & NAU7802_CTRL2_CALS)) return (v & NAU7802_CTRL2_CAL_ERR) ? NAU7802_ERR_CAL : NAU7802_OK;
    }
    return NAU7802_ERR_CAL;
}

nau7802_result_t nau7802_set_rate(const nau7802_bus_t *b, uint16_t sps)
{
    uint8_t crs;
    if (sps == 80) crs = NAU7802_CTRL2_CRS_80;
    else if (sps == 320) crs = NAU7802_CTRL2_CRS_320;
    else return NAU7802_ERR_PARAM;
    nau7802_result_t r = update(b, NAU7802_REG_CTRL2, 0x70, crs);
    if (r != NAU7802_OK) return r;
    /* The datasheet asks for recalibration after a rate change. */
    return calibrate_offset(b);
}

nau7802_result_t nau7802_init(const nau7802_bus_t *b, uint16_t sps)
{
    if (sps != 80 && sps != 320) return NAU7802_ERR_PARAM;
    /* Register reset is level-triggered: assert, then release. */
    if (!b->write(b->ctx, NAU7802_REG_PU_CTRL, NAU7802_PU_RR)) return NAU7802_ERR_BUS;
    b->delay_ms(b->ctx, 1);
    if (!b->write(b->ctx, NAU7802_REG_PU_CTRL, NAU7802_PU_PUD)) return NAU7802_ERR_BUS;
    bool up = false;
    for (int i = 0; i < 50 && !up; i++) {
        uint8_t v;
        b->delay_ms(b->ctx, 1);
        if (!b->read(b->ctx, NAU7802_REG_PU_CTRL, &v, 1)) return NAU7802_ERR_BUS;
        up = (v & NAU7802_PU_PUR) != 0;
    }
    if (!up) return NAU7802_ERR_POWERUP;
    /* Analog on, AVDD from the internal LDO (drives the bridge excitation). */
    if (!b->write(b->ctx, NAU7802_REG_PU_CTRL, NAU7802_PU_PUD | NAU7802_PU_PUA | NAU7802_PU_AVDDS))
        return NAU7802_ERR_BUS;
    if (!b->write(b->ctx, NAU7802_REG_CTRL1, NAU7802_CTRL1_LDO_3V0 | NAU7802_CTRL1_GAIN_128))
        return NAU7802_ERR_BUS;
    /* REG_CHPS = 11: chopper clock off, recommended for gain 128 bridge use. */
    if (!b->write(b->ctx, NAU7802_REG_ADC, 0x30)) return NAU7802_ERR_BUS;
    /* PGA_CAP_EN: enables the external Cfilter across the PGA output (single channel). */
    if (!b->write(b->ctx, NAU7802_REG_POWER, 0x80)) return NAU7802_ERR_BUS;
    b->delay_ms(b->ctx, 200); /* LDO and bridge settle before calibrating */
    nau7802_result_t r = update(b, NAU7802_REG_CTRL2, 0x70,
                                sps == 80 ? NAU7802_CTRL2_CRS_80 : NAU7802_CTRL2_CRS_320);
    if (r != NAU7802_OK) return r;
    r = update(b, NAU7802_REG_PU_CTRL, NAU7802_PU_CS, NAU7802_PU_CS);
    if (r != NAU7802_OK) return r;
    return calibrate_offset(b);
}

nau7802_result_t nau7802_read(const nau7802_bus_t *b, int32_t *raw)
{
    uint8_t v;
    if (!b->read(b->ctx, NAU7802_REG_PU_CTRL, &v, 1)) return NAU7802_ERR_BUS;
    if (!(v & NAU7802_PU_CR)) return NAU7802_NOT_READY;
    uint8_t d[3];
    if (!b->read(b->ctx, NAU7802_REG_ADCO_B2, d, 3)) return NAU7802_ERR_BUS;
    uint32_t u = ((uint32_t)d[0] << 16) | ((uint32_t)d[1] << 8) | d[2];
    if (u & 0x800000u) u |= 0xFF000000u;
    *raw = (int32_t)u;
    return NAU7802_OK;
}

nau7802_result_t nau7802_power_down(const nau7802_bus_t *b)
{
    return b->write(b->ctx, NAU7802_REG_PU_CTRL, 0x00) ? NAU7802_OK : NAU7802_ERR_BUS;
}
