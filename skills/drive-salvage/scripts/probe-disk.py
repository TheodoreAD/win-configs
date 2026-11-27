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
if any(mbr[446:462]):
    print(f"  MBR entry 1: type 0x{mbr[450]:02x} (0xee = protective, for GPT), start {struct.unpack_from('<I', mbr, 454)[0]}")


def gpt(header: bytes, label: str) -> None:
    """Print a GPT header's fields and every non-empty entry it points to."""
    print(f"{label} GPT header: {header[:8] == b'EFI PART'}")
    if header[:8] != b"EFI PART":
        return
    first_usable, last_usable = struct.unpack_from("<QQ", header, 40)
    entries_lba, count, size = struct.unpack_from("<QII", header, 72)
    raw = read(entries_lba, (count * size + SECTOR - 1) // SECTOR)
    used = 0
    for i in range(count):
        e = raw[i * size:(i + 1) * size]
        if any(e[:16]):
            used += 1
            first, end = struct.unpack_from("<QQ", e, 32)
            name = e[56:128].decode("utf-16-le", errors="replace").rstrip("\x00")
            print(f"  partition {i + 1}: sectors {first}-{end} ({(end - first + 1) * SECTOR / 1e9:.1f} GB) "
                  f"'{name}', type {e[:16].hex()}")
    print(f"  disk GUID {header[56:72].hex()}, usable sectors {first_usable}-{last_usable}, "
          f"{used} of {count} entries used")


gpt(read(1), "primary (LBA 1)")
gpt(read(last), "backup (last LBA)")

SIGS = [("NTFS boot sector", 3, b"NTFS    "), ("BitLocker volume", 3, b"-FVE-FS-"), ("exFAT boot sector", 3, b"EXFAT   "),
        ("ReFS boot sector", 3, b"ReFS"), ("FAT32 boot sector", 82, b"FAT32   "), ("LUKS header", 0, b"LUKS\xba\xbe"),
        ("LVM label", 24, b"LVM2 001"), ("GPT header", 0, b"EFI PART"), ("XFS superblock", 0, b"XFSB"),
        ("F2FS superblock (fs starts 2 sectors earlier)", 0, b"\x10\x20\xf5\xf2"),
        ("btrfs superblock (fs starts 128 sectors earlier)", 64, b"_BHRfS_M"),
        ("Linux swap (page ends here)", 502, b"SWAPSPACE2")]
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
# Where partitions usually start: after the GPT, at 1 MB, after a 16 MB Microsoft Reserved partition.
for lba in (34, 2048, 34816, 264192):
    head = read(lba)[:32]
    print(f"  first bytes at sector {lba}: {head.hex(' ')}  |{''.join(chr(b) if 32 <= b < 127 else '.' for b in head)}|")

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
if "--ntfs" in sys.argv:
    # NTFS keeps a backup boot sector in the last sector of its partition: it gives the
    # partition's size, so its start follows. Then list file names from the MFT records.
    print("\nNTFS: looking for a backup boot sector in the last 1 GB...")
    tail = 2 * 1024 * 1024
    boot = None
    for start in range(max(0, last - tail), last + 1, CHUNK):
        buf = read(start, min(CHUNK, last + 1 - start))
        for s in range(0, len(buf), SECTOR):
            if buf[s + 3:s + 11] == b"NTFS    " and buf[s + 510:s + 512] == b"\x55\xaa":
                boot = (start + s // SECTOR, buf[s:s + SECTOR])
    if boot:
        lba, bs = boot
        bps, spc = struct.unpack_from("<HB", bs, 11)
        total, mft_lcn, mirr_lcn = struct.unpack_from("<QQQ", bs, 40)
        first = lba - total  # the backup sits right after the volume's last sector
        print(f"  backup boot sector at sector {lba}: volume of {total} sectors ({total * bps / 1e9:.1f} GB), "
              f"{spc * bps} bytes per cluster, so the partition ran from sector {first} to {lba}")
        print(f"  MFT at sector {first + mft_lcn * spc}, MFT mirror at sector {first + mirr_lcn * spc}")
        mft_at = first + mft_lcn * spc
    else:
        print("  none found")
        mft_at = 0
    # File names, from MFT records ("FILE" signature) near where the MFT should be.
    names, records = Counter(), 0
    sample = []
    region = range(mft_at, mft_at + 4 * 1024 * 1024, CHUNK) if mft_at else range(0, 16 * 1024 * 1024, CHUNK)
    for start in region:
        buf = read(start, CHUNK)
        for off in range(0, len(buf) - 1024, 1024):
            rec = buf[off:off + 1024]
            if rec[:4] != b"FILE" or not (struct.unpack_from("<H", rec, 22)[0] & 1):  # in use
                continue
            records += 1
            a = struct.unpack_from("<H", rec, 20)[0]
            while 0 < a < 1000:
                typ, ln = struct.unpack_from("<II", rec, a)
                if typ == 0xFFFFFFFF or ln == 0:
                    break
                if typ == 0x30 and rec[a + 8] == 0:  # resident $FILE_NAME
                    v = a + struct.unpack_from("<H", rec, a + 20)[0]
                    nlen, ns = rec[v + 64], rec[v + 65]
                    if ns != 2:  # skip DOS 8.3 names
                        name = rec[v + 66:v + 66 + 2 * nlen].decode("utf-16-le", errors="replace")
                        size = struct.unpack_from("<Q", rec, v + 48)[0]
                        if not name.startswith("$"):
                            names[name.rsplit(".", 1)[-1].lower() if "." in name else "(no extension)"] += 1
                            if len(sample) < 40:
                                sample.append((name, size))
                        break
                a += ln
    print(f"  {records} file records in use; by extension: "
          + ", ".join(f"{k} {v}" for k, v in names.most_common(15)))
    for name, size in sample:
        print(f"    {name}  ({size / 1e9:.1f} GB)" if size > 1e8 else f"    {name}")

if len(sys.argv) > 2 and sys.argv[2].isdigit():  # read the ext superblock of a filesystem starting at this sector
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
