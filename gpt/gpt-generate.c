/* File-only GPT generator. C99; POSIX libc open(O_EXCL) prevents clobbering. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define TABLE (128 * 128)
static unsigned char primary[34 * 512], backup[33 * 512];
static const unsigned char linux_type[16] = {
    0xaf,0x3d,0xc6,0x0f,0x83,0x84,0x72,0x47,
    0x8e,0x79,0x3d,0x69,0xd8,0x47,0x7d,0xe4
};
static const char *names[] = {
    "lk", "tee1", "tee2", "boot", "recovery", "logo", "kb", "dkb",
    "MISC", "vendor", "system", "cache", "userdata"
};
static const uint64_t starts[] = {
    1024,3072,13312,23552,56320,89088,96256,98304,100352,102400,
    409600,3481600,4530176
};
static void die(const char *s)
{
    fprintf(stderr, "gpt-generate: %s\n", s);
    exit(1);
}
static uint32_t get32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 |
           (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static uint64_t get64(const unsigned char *p)
{
    return get32(p) | (uint64_t)get32(p+4)<<32;
}
static void put32(unsigned char *p, uint32_t v)
{
    unsigned i;
    for (i=0; i<4; i++, v>>=8) p[i]=(unsigned char)v;
}
static void put64(unsigned char *p, uint64_t v)
{
    put32(p, (uint32_t)v);
    put32(p+4, (uint32_t)(v>>32));
}
static uint32_t crc32(const unsigned char *p, size_t n)
{
    uint32_t c=0xffffffffU;
    unsigned j;
    while (n--) {
        c ^= *p++;
        for (j=0; j<8; j++) c=(c>>1) ^ (0xedb88320U & (0U-(c&1)));
    }
    return ~c;
}
static int zero(const unsigned char *p, size_t n)
{
    while (n--) if (*p++) return 0;
    return 1;
}
static int named(const unsigned char *e, const char *s)
{
    unsigned i;
    for (i=0; i<36; i++) {
        unsigned c=(unsigned char)*s;
        if (e[56+2*i]!=c || e[57+2*i]) return 0;
        if (c) s++;
    }
    return !*s;
}
static void load(const char *path, unsigned char *p, size_t n)
{
    struct stat st;
    FILE *f=fopen(path, "rb");
    if (!f) die("cannot open input");
    if (fstat(fileno(f), &st) || !S_ISREG(st.st_mode) ||
        st.st_size!=(off_t)n) die("input must be an exactly sized regular file");
    if (fread(p, 1, n, f)!=n || fgetc(f)!=EOF || ferror(f))
        die("cannot read input");
    if (fclose(f)) die("cannot close input");
}
static void header(unsigned char *h, const unsigned char *table,
                   uint64_t sectors, int back)
{
    uint32_t saved=get32(h+16);
    if (memcmp(h, "EFI PART", 8) || get32(h+8)!=0x10000 ||
        get32(h+12)!=92 || get32(h+20) ||
        get64(h+24)!=(back ? sectors-1 : 1) ||
        get64(h+32)!=(back ? 1 : sectors-1) ||
        get64(h+40)!=34 || get64(h+48)!=sectors-34 ||
        zero(h+56,16) || get64(h+72)!=(back ? sectors-33 : 2) ||
        get32(h+80)!=128 || get32(h+84)!=128)
        die("unsupported GPT header");
    put32(h+16,0);
    if (crc32(h,92)!=saved) die("header CRC mismatch");
    put32(h+16,saved);
    if (crc32(table,TABLE)!=get32(h+88)) die("table CRC mismatch");
}
static void entries(const unsigned char *t, uint64_t sectors)
{
    unsigned i,j,count=0;
    for (i=0; i<128; i++) {
        const unsigned char *e=t+128*i;
        uint64_t start=get64(e+32), end=get64(e+40);
        if (zero(e,128)) continue;
        /* ponytail: only verified original-13 and generated-11 profiles. */
        if (i!=count || i>=13 || memcmp(e,linux_type,16) ||
            zero(e+16,16) || !named(e,names[i]) ||
            start<34 || start>end || end>sectors-34)
            die("unsupported partition entry");
        for (j=0; j<i; j++) {
            const unsigned char *other=t+128*j;
            if (!memcmp(e+16,other+16,16) ||
                (start<=get64(other+40) && end>=get64(other+32)))
                die("duplicate GUID or overlapping partitions");
        }
        count++;
    }
    if (count!=11 && count!=13) die("unsupported source profile");
    for (i=0; i<count; i++) {
        const unsigned char *e=t+128*i;
        uint64_t end=(i+1==count) ? sectors-34 : starts[i+1]-1;
        if (get64(e+32)!=starts[i] || get64(e+40)!=end)
            die("unsupported source partition range");
    }
}
static void reseal(unsigned char *h, const unsigned char *t)
{
    put32(h+88,crc32(t,TABLE));
    put32(h+16,0);
    put32(h+16,crc32(h,92));
}
static int save(int fd, const unsigned char *p, size_t n)
{
    while (n) {
        ssize_t written=write(fd,p,n);
        if (written<0 && errno==EINTR) continue;
        if (written<=0) return -1;
        p+=written;
        n-=(size_t)written;
    }
    return fsync(fd);
}
int main(int argc, char **argv)
{
    uint64_t sectors;
    unsigned char *table=primary+1024;
    int bfd,pfd,failed;
    if (argc!=6) die("usage: gpt-generate SECTORS INPUT_PRIMARY INPUT_BACKUP OUTPUT_PRIMARY OUTPUT_BACKUP");
    if (!strcmp(argv[1],"15269888")) sectors=15269888;
    else if (!strcmp(argv[1],"15273600")) sectors=15273600;
    else die("unsupported sector count");
    load(argv[2],primary,sizeof primary);
    load(argv[3],backup,sizeof backup);
    if (primary[510]!=0x55 || primary[511]!=0xaa) die("invalid MBR signature");
    header(primary+512,table,sectors,0);
    header(backup+TABLE,backup,sectors,1);
    if (memcmp(primary+568,backup+TABLE+56,16) || memcmp(table,backup,TABLE))
        die("GPT copies disagree");
    entries(table,sectors);
    /* Preserve first ten entries and system metadata, changing only its end. */
    put64(table+10*128+40,sectors-34);
    memset(table+11*128,0,TABLE-11*128);
    memcpy(backup,table,TABLE);
    reseal(primary+512,table);
    reseal(backup+TABLE,backup);

    /* O_EXCL also rejects symlinks and existing device nodes. Backup first. */
    bfd=open(argv[5],O_WRONLY|O_CREAT|O_EXCL,0600);
    if (bfd<0) die("cannot exclusively create backup output");
    failed=save(bfd,backup,sizeof backup);
    if (close(bfd)) failed=1;
    if (failed) {
        unlink(argv[5]);
        die("cannot write backup output");
    }
    pfd=open(argv[4],O_WRONLY|O_CREAT|O_EXCL,0600);
    if (pfd<0) {
        unlink(argv[5]);
        die("cannot exclusively create primary output");
    }
    failed=save(pfd,primary,sizeof primary);
    if (close(pfd)) failed=1;
    if (failed) {
        unlink(argv[4]);
        unlink(argv[5]);
        die("cannot write primary output");
    }
    return 0;
}
