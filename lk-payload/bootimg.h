#pragma once

#include <stdint.h>

static int bootimg_is_arm64(const void *image, uint32_t size)
{
    const uint8_t *header = image;
    const char magic[] = "ANDROID!";
    const char option[] = "bootopt=64S3,32N2,64N2";

    if (!header || size < 0x40 + sizeof(option))
        return 0;

    for (unsigned i = 0; i < sizeof(magic) - 1; ++i)
        if (header[i] != magic[i])
            return 0;

    for (unsigned i = 0; i < sizeof(option) - 1; ++i)
        if (header[0x40 + i] != option[i])
            return 0;

    uint8_t end = header[0x40 + sizeof(option) - 1];
    return end == '\0' || end == ' ' || end == '\t';
}
