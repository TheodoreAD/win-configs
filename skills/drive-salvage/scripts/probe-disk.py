"""Read-only probe of a raw disk: what's on it when Windows sees no partitions.

Run in an admin shell (raw disk reads need it):
  python -I <skill>/scripts/probe-disk.py 4          # disk number from Get-Disk
  python -I <skill>/scripts/probe-disk.py 4 2048     # also read the ext superblock starting there

It reports:
- the MBR, the primary GPT, and the backup GPT at the last sector, with its partitions if
  there is one: a wiped table often leaves the backup
- signatures in the first 1 GB, sector by sector: NTFS, BitLocker, exFAT, FAT32, LUKS, LVM,
  GPT and ext. The ext magic is two bytes, so random data matches it about every 65,000
  sectors. A hit at a partition-like offset (sector 2048, the 1 MB mark) is the real one.
- the median entropy of 200 samples: about 7.95 bits per byte is encrypted, 7–7.9 compressed
  data, under ~6 ordinary files
- with a start sector, the ext superblock: size, free space, file count, label, last mount
  point, and when it was created and last written

Opens \\\\.\\PhysicalDrive<n> for reading only and writes nothing anywhere. See
references/retiring-a-drive.md, step 0.
"""
import math
import struct
import sys
from collections import Counter

n = sys.argv[1]
SECTOR = 512
dev = open(rf"\\.\PhysicalDrive{n}", "rb", buffering=0)


def read(lba: int, count: int = 1) -> bytes:
    dev.seek(lba * SECTOR)
    return dev.read(count * SECTOR)


# Size: seek to the end isn't supported on raw devices; find it by binary search on readable sectors.
lo, hi = 0, 1 << 40
while lo < hi:
    mid = (lo + hi + 1) // 2
    try:
        dev.seek(mid * SECTOR)
        ok = len(dev.read(SECTOR)) == SECTOR
    except OSError:
        ok = False
    lo, hi = (mid, hi) if ok else (lo, mid - 1)
last = lo
print(f"disk: {last + 1} sectors ({(last + 1) * SECTOR / 1e9:.1f} GB)")

mbr = read(0)
print(f"MBR signature 55AA: {mbr[510:512] == b'\\x55\\xaa'}; partition entries non-empty: "
      f"{sum(1 for i in range(4) if any(mbr[446 + 16 * i:462 + 16 * i]))}")
print(f"primary GPT header at LBA 1: {read(1)[:8] == b'EFI PART'}")
backup = read(last)
print(f"backup GPT header at last LBA: {backup[:8] == b'EFI PART'}")
if backup[:8] == b"EFI PART":
    entries_lba, count, size = struct.unpack_from("<QII", backup, 72)
    raw = read(entries_lba, (count * size + SECTOR - 1) // SECTOR)
    for i in range(count):
        e = raw[i * size:(i + 1) * size]
        if any(e[:16]):
            first, end = struct.unpack_from("<QQ", e, 32)
            name = e[56:128].decode("utf-16-le", errors="replace").rstrip("\x00")
            print(f"  backup GPT partition {i + 1}: sectors {first}-{end} ({(end - first + 1) * SECTOR / 1e9:.1f} GB) '{name}'")

SIGS = [("NTFS boot sector", 3, b"NTFS    "), ("BitLocker volume", 3, b"-FVE-FS-"), ("exFAT boot sector", 3, b"EXFAT   "),
        ("FAT32 boot sector", 82, b"FAT32   "), ("LUKS header", 0, b"LUKS\xba\xbe"), ("LVM label", 24, b"LVM2 001"),
        ("GPT header", 0, b"EFI PART")]
found = []
CHUNK = 2048  # sectors per read (1 MB)
scan = min(last, 2 * 1024 * 1024)  # first 1 GB
for start in range(0, scan, CHUNK):
    buf = read(start, CHUNK)
    for s in range(0, len(buf), SECTOR):
        sec = buf[s:s + SECTOR]
        for name, off, sig in SIGS:
            if sec[off:off + len(sig)] == sig:
                found.append((start + s // SECTOR, name))
        if sec[56:58] == b"\x53\xef" and s >= 2 * SECTOR:  # ext superblock magic, 1024 bytes into a filesystem
            found.append((start + s // SECTOR - 2, "ext2/3/4 superblock"))
print(f"signatures in the first {scan * SECTOR / 1e9:.1f} GB: {len(found)}")
for lba, name in found[:25]:
    print(f"  sector {lba} ({lba * SECTOR / 1e6:.1f} MB): {name}")

# How random is the data? Encrypted or compressed data is close to 8 bits per byte.
samples = []
for i in range(200):
    blk = read(last // 200 * i, 8)
    if any(blk):
        c = Counter(blk)
        samples.append(-sum(v / len(blk) * math.log2(v / len(blk)) for v in c.values()))
if samples:
    samples.sort()
    print(f"entropy of {len(samples)} non-empty 4 KB samples: median {samples[len(samples) // 2]:.2f} bits/byte "
          f"(8.0 = random: encrypted or compressed; under ~6 = ordinary files)")
if len(sys.argv) > 2:  # read the ext superblock of a filesystem starting at this sector
    import time
    start = int(sys.argv[2])
    sb = read(start + 2, 2)  # superblock: 1024 bytes into the filesystem
    inodes, blocks_lo, _, free_lo, free_inodes, first_data, log_bs = struct.unpack_from("<IIIIIII", sb, 0)
    mtime, wtime, mnt_count = struct.unpack_from("<IIH", sb, 44)
    magic, state = struct.unpack_from("<HH", sb, 56)
    lastcheck, = struct.unpack_from("<I", sb, 64)
    creator, = struct.unpack_from("<I", sb, 72)
    compat, incompat = struct.unpack_from("<II", sb, 92)
    label = sb[120:136].split(b"\0")[0].decode(errors="replace")
    last_mounted = sb[136:200].split(b"\0")[0].decode(errors="replace")
    mkfs_time, = struct.unpack_from("<I", sb, 264)
    blocks_hi, = struct.unpack_from("<I", sb, 336)
    bs = 1024 << log_bs
    blocks = blocks_lo | ((blocks_hi << 32) if incompat & 0x80 else 0)
    t = lambda x: time.strftime("%Y-%m-%d %H:%M", time.localtime(x)) if x else "-"
    kind = "ext4" if incompat & 0x40 else ("ext3" if compat & 0x4 else "ext2")
    print(f"\nsuperblock at sector {start}: magic {'OK' if magic == 0xEF53 else hex(magic)}, {kind}")
    print(f"  size {blocks * bs / 1e9:.1f} GB, free {free_lo * bs / 1e9:.1f} GB, inodes {inodes} ({free_inodes} free)")
    print(f"  label '{label}', last mounted on '{last_mounted}', state {'clean' if state & 1 else 'not clean'}")
    print(f"  created {t(mkfs_time)}, last mounted {t(mtime)}, last written {t(wtime)}, mounted {mnt_count} times, "
          f"creator OS {['Linux', 'Hurd', 'Masix', 'FreeBSD', 'Lites'][creator] if creator < 5 else creator}")
dev.close()
