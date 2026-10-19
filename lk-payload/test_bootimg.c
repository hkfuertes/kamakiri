#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "bootimg.h"

int main(void)
{
    uint8_t header[0x400] = {0};
    char *cmdline = (char *)header + 0x40;
    const char *arm64 = "bootopt=64S3,32N2,64N2";

    assert(!bootimg_is_arm64(NULL, 0));
    assert(!bootimg_is_arm64(header, sizeof(header)));
    memcpy(header, "ANDROID!", 8);

    strcpy(cmdline, "bootopt=64S3,32N2,32N2 buildvariant=user");
    assert(!bootimg_is_arm64(header, 0x260)); // Stock boot and TWRP stay ARM32.

    strcpy(cmdline, arm64);
    assert(bootimg_is_arm64(header, 0x260));
    strcat(cmdline, " console=ttyS0,115200");
    assert(bootimg_is_arm64(header, 0x260));
    strcpy(cmdline, "bootopt=64S3,32N2,64N2\tconsole=ttyS0");
    assert(bootimg_is_arm64(header, 0x260));

    strcpy(cmdline, "bootopt=64S3,32N2,64N2extra");
    assert(!bootimg_is_arm64(header, 0x260));
    strcpy(cmdline, "xbootopt=64S3,32N2,64N2");
    assert(!bootimg_is_arm64(header, 0x260));
    strcpy(cmdline, "console=ttyS0 bootopt=64S3,32N2,64N2");
    assert(!bootimg_is_arm64(header, 0x260)); // The marker must come first.
    strcpy(cmdline, "bootopt=64S3,32N2,64N");
    assert(!bootimg_is_arm64(header, 0x260));

    strcpy(cmdline, arm64);
    assert(!bootimg_is_arm64(header, 0x40 + strlen(arm64)));
    assert(bootimg_is_arm64(header, 0x40 + strlen(arm64) + 1));
    header[7] = '?';
    assert(!bootimg_is_arm64(header, sizeof(header)));

    // Exact-size buffers let AddressSanitizer check truncated-read boundaries.
    const uint8_t short_header[8] = {'A', 'N', 'D', 'R', 'O', 'I', 'D', '!'};
    assert(!bootimg_is_arm64(short_header, sizeof(short_header)));

    puts("PASS: ARM64 opt-in, ARM32 fallback, token and buffer boundaries");
    return 0;
}
