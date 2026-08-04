import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from tools.recover_sdcard import main, _reject_if_device

_SECTOR = 512


def _fat32_boot_sector(reserved_sectors, num_fats, fat_size_32, root_cluster, total_sectors_32):
    boot = bytearray(_SECTOR)
    struct.pack_into("<HBHB", boot, 11, _SECTOR, 1, reserved_sectors, num_fats)
    struct.pack_into("<I", boot, 32, total_sectors_32)
    struct.pack_into("<I", boot, 36, fat_size_32)
    struct.pack_into("<I", boot, 44, root_cluster)
    boot[82:90] = b"FAT32   "
    return bytes(boot)


def _fat32_dir_entry(name11, attr, cluster, size):
    return struct.pack("<11sBBBHHHHHHHI", name11, attr, 0, 0, 0, 0, 0,
                        (cluster >> 16) & 0xFFFF, 0, 0, cluster & 0xFFFF, size)


def _simple_jpeg():
    soi = b"\xFF\xD8"
    app1_payload = b"Exif\x00\x00" + b"\x00" * 8
    app1 = b"\xFF\xE1" + struct.pack(">H", 2 + len(app1_payload)) + app1_payload
    sos = b"\xFF\xDA" + struct.pack(">H", 2)
    entropy = b"\x11\x22\x33"
    eoi = b"\xFF\xD9"
    return soi + app1 + sos + entropy + eoi


def _pad(data, size):
    return data + bytes(size - len(data))


def _build_fat32_image_with_deleted_jpeg():
    jpeg = _simple_jpeg()
    assert len(jpeg) <= _SECTOR
    reserved_sectors, num_fats, fat_size_32, root_cluster = 1, 1, 1, 2
    total_sectors_32 = 6  # reserved(1)+fat(1)+data(4 clusters: 2..5)
    boot = _fat32_boot_sector(reserved_sectors, num_fats, fat_size_32, root_cluster,
                               total_sectors_32)
    fat = bytearray(_SECTOR)
    root_entries = _fat32_dir_entry(b"\xE5HOTO   JPG", 0x20, 3, len(jpeg))
    cluster2 = _pad(root_entries, _SECTOR)
    cluster3 = _pad(jpeg, _SECTOR)
    cluster4 = bytes(_SECTOR)
    cluster5 = bytes(_SECTOR)
    return boot + bytes(fat) + cluster2 + cluster3 + cluster4 + cluster5


class TestRejectIfDevice(unittest.TestCase):
    def test_regular_file_is_accepted(self):
        with tempfile.NamedTemporaryFile() as f:
            _reject_if_device(f.name)  # 예외 없이 통과해야 함


class TestRecoverSdcardCli(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_both_mode_populates_undeleted_and_carved(self):
        image = _build_fat32_image_with_deleted_jpeg()
        image_path = os.path.join(self.tmpdir.name, "card.img")
        with open(image_path, "wb") as f:
            f.write(image)
        out_dir = os.path.join(self.tmpdir.name, "out")

        argv = ["recover_sdcard.py", image_path, out_dir]
        buf = StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            main()

        undeleted_dir = os.path.join(out_dir, "undeleted")
        carved_dir = os.path.join(out_dir, "carved")
        self.assertTrue(os.listdir(undeleted_dir))
        self.assertTrue(os.listdir(carved_dir))
        output = buf.getvalue()
        self.assertIn("fat32", output)
        self.assertIn("[undelete]", output)
        self.assertIn("[carve]", output)

    def test_carve_only_mode_skips_undelete(self):
        image = _build_fat32_image_with_deleted_jpeg()
        image_path = os.path.join(self.tmpdir.name, "card2.img")
        with open(image_path, "wb") as f:
            f.write(image)
        out_dir = os.path.join(self.tmpdir.name, "out2")

        argv = ["recover_sdcard.py", image_path, out_dir, "--mode", "carve"]
        buf = StringIO()
        with patch.object(sys, "argv", argv), redirect_stdout(buf):
            main()

        self.assertFalse(os.path.isdir(os.path.join(out_dir, "undeleted")))
        self.assertTrue(os.listdir(os.path.join(out_dir, "carved")))


if __name__ == "__main__":
    unittest.main()
