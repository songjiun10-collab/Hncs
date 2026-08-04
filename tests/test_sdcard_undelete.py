import os
import struct
import tempfile
import unittest

from core.sdcard_undelete import detect_filesystem, recover_fat32, recover_exfat

_SECTOR = 512


def _pad(data, size):
    if len(data) > size:
        raise ValueError("data larger than sector/cluster size")
    return data + bytes(size - len(data))


# ---------------------------------------------------------------------------
# FAT32 fixture
# ---------------------------------------------------------------------------

def _fat32_boot_sector(reserved_sectors, num_fats, fat_size_32, root_cluster,
                        total_sectors_32, sectors_per_cluster=1, bytes_per_sector=_SECTOR):
    boot = bytearray(_SECTOR)
    struct.pack_into("<HBHB", boot, 11, bytes_per_sector, sectors_per_cluster,
                      reserved_sectors, num_fats)
    struct.pack_into("<I", boot, 32, total_sectors_32)
    struct.pack_into("<I", boot, 36, fat_size_32)
    struct.pack_into("<I", boot, 44, root_cluster)
    boot[82:90] = b"FAT32   "
    return bytes(boot)


def _fat32_dir_entry(name11, attr, cluster, size):
    return struct.pack("<11sBBBHHHHHHHI", name11, attr, 0, 0, 0, 0, 0,
                        (cluster >> 16) & 0xFFFF, 0, 0, cluster & 0xFFFF, size)


class TestFat32Recovery(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def _build_image(self):
        reserved_sectors, num_fats, fat_size_32 = 1, 1, 1
        root_cluster = 2
        total_sectors_32 = 10  # reserved(1) + fat(1) + 8 data clusters(2..9)
        boot = _fat32_boot_sector(reserved_sectors, num_fats, fat_size_32,
                                   root_cluster, total_sectors_32)

        fat = bytearray(_SECTOR)
        struct.pack_into("<I", fat, 3 * 4, 4)   # cluster3 -> 4 (intact chain)
        struct.pack_into("<I", fat, 6 * 4, 0)   # cluster6 -> free (broken chain)

        root_entries = b"".join([
            _fat32_dir_entry(b"\xE5FILE   JPG", 0x20, 3, 700),   # deleted, intact chain
            _fat32_dir_entry(b"LIVE    JPG", 0x20, 10, 100),      # not deleted -> skip
            _fat32_dir_entry(b"SUB        ", 0x10, 5, 0),         # subdirectory
        ])
        cluster2 = _pad(root_entries, _SECTOR)

        cluster3 = bytes([ord("A")]) * _SECTOR
        cluster4 = bytes([ord("B")]) * _SECTOR

        sub_entries = _fat32_dir_entry(b"\xE5GILE   JPG", 0x20, 6, 600)  # deleted, broken chain
        cluster5 = _pad(sub_entries, _SECTOR)

        cluster6 = bytes([ord("C")]) * _SECTOR
        cluster7 = bytes([ord("D")]) * _SECTOR
        cluster8 = bytes(_SECTOR)
        cluster9 = bytes(_SECTOR)

        data = boot + bytes(fat) + cluster2 + cluster3 + cluster4 + cluster5 + \
            cluster6 + cluster7 + cluster8 + cluster9
        path = os.path.join(self.tmpdir.name, "fat32.img")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_detect_filesystem(self):
        path = self._build_image()
        self.assertEqual(detect_filesystem(path), "fat32")

    def test_recovers_intact_chain_file(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_fat32(path, out_dir)
        by_name = {r["name"]: r for r in results}
        self.assertIn("_FILE.JPG", by_name)
        r = by_name["_FILE.JPG"]
        self.assertTrue(r["recovered"])
        self.assertEqual(r["method"], "fat_chain")
        self.assertEqual(r["size"], 700)
        with open(r["out_path"], "rb") as f:
            recovered = f.read()
        self.assertEqual(len(recovered), 700)
        self.assertEqual(recovered, b"A" * 512 + b"B" * 188)

    def test_recovers_broken_chain_via_contiguous_guess(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_fat32(path, out_dir)
        by_name = {r["name"]: r for r in results}
        self.assertIn("_GILE.JPG", by_name)
        r = by_name["_GILE.JPG"]
        self.assertTrue(r["recovered"])
        self.assertEqual(r["method"], "contiguous_guess")
        self.assertEqual(r["path"], os.path.join("SUB", "_GILE.JPG"))
        with open(r["out_path"], "rb") as f:
            recovered = f.read()
        self.assertEqual(recovered, b"C" * 512 + b"D" * 88)

    def test_live_file_not_recovered(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_fat32(path, out_dir)
        names = [r["name"] for r in results]
        self.assertNotIn("LIVE.JPG", names)


# ---------------------------------------------------------------------------
# exFAT fixture
# ---------------------------------------------------------------------------

def _exfat_boot_sector(fat_offset_sectors, fat_length_sectors, cluster_heap_offset_sectors,
                        cluster_count, root_cluster, bytes_per_sector_shift=9,
                        sectors_per_cluster_shift=0):
    boot = bytearray(_SECTOR)
    boot[3:11] = b"EXFAT   "
    struct.pack_into("<IIIII", boot, 80, fat_offset_sectors, fat_length_sectors,
                      cluster_heap_offset_sectors, cluster_count, root_cluster)
    boot[112] = bytes_per_sector_shift
    boot[113] = sectors_per_cluster_shift
    return bytes(boot)


def _exfat_file_dir_entry(deleted, is_dir, secondary_count):
    entry_type = 0x05 if deleted else 0x85
    b = bytearray(32)
    b[0] = entry_type
    b[1] = secondary_count
    struct.pack_into("<H", b, 4, 0x10 if is_dir else 0x20)
    return bytes(b)


def _exfat_stream_entry(deleted, no_fat_chain, name_length, valid_data_length, first_cluster):
    entry_type = 0x40 if deleted else 0xC0
    b = bytearray(32)
    b[0] = entry_type
    b[1] = 0x01 | (0x02 if no_fat_chain else 0x00)
    b[3] = name_length
    struct.pack_into("<Q", b, 8, valid_data_length)
    struct.pack_into("<I", b, 20, first_cluster)
    struct.pack_into("<Q", b, 24, valid_data_length)
    return bytes(b)


def _exfat_name_entries(deleted, name):
    entry_type = 0x41 if deleted else 0xC1
    raw = name.encode("utf-16-le")
    out = []
    for i in range(0, len(raw), 30):
        b = bytearray(32)
        b[0] = entry_type
        chunk = raw[i:i + 30]
        b[2:2 + len(chunk)] = chunk
        out.append(bytes(b))
    return out


def _exfat_file_group(name, deleted, is_dir, no_fat_chain, valid_data_length, first_cluster):
    names = _exfat_name_entries(deleted, name)
    secondary_count = 1 + len(names)
    entries = [_exfat_file_dir_entry(deleted, is_dir, secondary_count),
               _exfat_stream_entry(deleted, no_fat_chain,
                                    len(name), valid_data_length, first_cluster)]
    entries.extend(names)
    return b"".join(entries)


class TestExfatRecovery(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def _build_image(self):
        root_cluster = 2
        cluster_count = 8  # clusters 2..9
        boot = _exfat_boot_sector(fat_offset_sectors=1, fat_length_sectors=1,
                                   cluster_heap_offset_sectors=2,
                                   cluster_count=cluster_count, root_cluster=root_cluster)

        fat = bytearray(_SECTOR)
        struct.pack_into("<I", fat, 5 * 4, 6)  # cluster5 -> 6 (real chain for CHAIN.JPG)

        root_entries = b"".join([
            _exfat_file_group("SHORT.JPG", deleted=True, is_dir=False,
                               no_fat_chain=True, valid_data_length=700, first_cluster=3),
            _exfat_file_group("CHAIN.JPG", deleted=True, is_dir=False,
                               no_fat_chain=False, valid_data_length=700, first_cluster=5),
            _exfat_file_group("LIVE.JPG", deleted=False, is_dir=False,
                               no_fat_chain=True, valid_data_length=100, first_cluster=7),
            _exfat_file_group("SUBD", deleted=False, is_dir=True,
                               no_fat_chain=True, valid_data_length=0, first_cluster=8),
        ])
        cluster2 = _pad(root_entries, _SECTOR)

        cluster3 = bytes([ord("A")]) * _SECTOR
        cluster4 = bytes([ord("B")]) * _SECTOR
        cluster5 = bytes([ord("C")]) * _SECTOR
        cluster6 = bytes([ord("D")]) * _SECTOR
        cluster7 = bytes(_SECTOR)

        sub_entries = _exfat_file_group("DEEP.JPG", deleted=True, is_dir=False,
                                         no_fat_chain=True, valid_data_length=300,
                                         first_cluster=9)
        cluster8 = _pad(sub_entries, _SECTOR)
        cluster9 = bytes([ord("E")]) * _SECTOR

        data = boot + bytes(fat) + cluster2 + cluster3 + cluster4 + cluster5 + \
            cluster6 + cluster7 + cluster8 + cluster9
        path = os.path.join(self.tmpdir.name, "exfat.img")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_detect_filesystem(self):
        path = self._build_image()
        self.assertEqual(detect_filesystem(path), "exfat")

    def test_recovers_contiguous_no_fat_chain_file_full_name(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_exfat(path, out_dir)
        by_name = {r["name"]: r for r in results}
        self.assertIn("SHORT.JPG", by_name)  # exFAT keeps the full original name
        r = by_name["SHORT.JPG"]
        self.assertTrue(r["recovered"])
        self.assertEqual(r["method"], "contiguous_no_fat_chain")
        with open(r["out_path"], "rb") as f:
            recovered = f.read()
        self.assertEqual(recovered, b"A" * 512 + b"B" * 188)

    def test_recovers_via_real_fat_chain(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_exfat(path, out_dir)
        by_name = {r["name"]: r for r in results}
        self.assertIn("CHAIN.JPG", by_name)
        r = by_name["CHAIN.JPG"]
        self.assertTrue(r["recovered"])
        self.assertEqual(r["method"], "fat_chain")
        with open(r["out_path"], "rb") as f:
            recovered = f.read()
        self.assertEqual(recovered, b"C" * 512 + b"D" * 188)

    def test_live_file_not_recovered(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_exfat(path, out_dir)
        names = [r["name"] for r in results]
        self.assertNotIn("LIVE.JPG", names)

    def test_recurses_into_subdirectory(self):
        path = self._build_image()
        out_dir = os.path.join(self.tmpdir.name, "out")
        results = recover_exfat(path, out_dir)
        by_path = {r["path"]: r for r in results}
        self.assertIn(os.path.join("SUBD", "DEEP.JPG"), by_path)
        r = by_path[os.path.join("SUBD", "DEEP.JPG")]
        self.assertTrue(r["recovered"])
        with open(r["out_path"], "rb") as f:
            recovered = f.read()
        self.assertEqual(recovered, b"E" * 300)


if __name__ == "__main__":
    unittest.main()
