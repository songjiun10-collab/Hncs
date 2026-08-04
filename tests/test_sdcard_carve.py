import os
import struct
import tempfile
import unittest

from core.sdcard_carve import carve, _jpeg_extent, _tiff_extent_and_make, _raf_extent, _cr3_extent


def _write(tmpdir, name, data):
    path = os.path.join(tmpdir, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _tiff_entry(tag, typ, count, value4):
    return struct.pack("<HHI", tag, typ, count) + value4


def _build_tiff(make=b"Canon\x00", strip_offset=60, strip_size=1000, fill=b"R"):
    header = b"II*\x00" + struct.pack("<I", 8)
    e_make = _tiff_entry(271, 2, len(make), struct.pack("<I", 50))
    e_strip_off = _tiff_entry(273, 4, 1, struct.pack("<I", strip_offset))
    e_strip_cnt = _tiff_entry(279, 4, 1, struct.pack("<I", strip_size))
    ifd0 = struct.pack("<H", 3) + e_make + e_strip_off + e_strip_cnt + struct.pack("<I", 0)
    total = strip_offset + strip_size
    buf = bytearray(total)
    buf[0:len(header)] = header
    buf[8:8 + len(ifd0)] = ifd0
    buf[50:50 + len(make)] = make
    buf[strip_offset:strip_offset + strip_size] = fill * strip_size
    return bytes(buf)


def _simple_jpeg():
    soi = b"\xFF\xD8"
    app1_payload = b"Exif\x00\x00" + b"\x00" * 8
    app1 = b"\xFF\xE1" + struct.pack(">H", 2 + len(app1_payload)) + app1_payload
    sos = b"\xFF\xDA" + struct.pack(">H", 2)
    entropy = b"\x11\x22\x33"
    eoi = b"\xFF\xD9"
    return soi + app1 + sos + entropy + eoi


def _jpeg_with_embedded_thumbnail():
    soi = b"\xFF\xD8"
    thumb = b"\xFF\xD8" + b"\x00" * 20 + b"\xFF\xD9"  # 자기 SOI/EOI를 가진 가짜 썸네일
    app1_payload = b"Exif\x00\x00" + thumb
    app1 = b"\xFF\xE1" + struct.pack(">H", 2 + len(app1_payload)) + app1_payload
    sof0 = b"\xFF\xC0" + struct.pack(">H", 2 + 6) + b"\x00" * 6
    dht = b"\xFF\xC4" + struct.pack(">H", 2 + 4) + b"\x00" * 4
    sos = b"\xFF\xDA" + struct.pack(">H", 2)
    entropy = b"\x12\x34\xFF\x00\x56\x78"  # FF00 = 스터핑, 진짜 마커 아님
    real_eoi = b"\xFF\xD9"
    return soi + app1 + sof0 + dht + sos + entropy + real_eoi


def _build_raf(jpeg_offset=200, jpeg_length=50, cfa_header_offset=300, cfa_header_length=10,
               cfa_offset=400, cfa_length=2000):
    header = b"FUJIFILMCCD-RAW " + b"0201" + b"FF389501" + b"X-T1".ljust(32, b"\x00")
    header += b"0100" + b"\x00" * 20
    header += struct.pack(">IIIIII", jpeg_offset, jpeg_length, cfa_header_offset,
                           cfa_header_length, cfa_offset, cfa_length)
    assert len(header) == 108
    total = cfa_offset + cfa_length
    buf = bytearray(total)
    buf[0:108] = header
    return bytes(buf)


def _bmff_box(type4, payload):
    size = 8 + len(payload)
    return struct.pack(">I", size) + type4 + payload


def _build_cr3():
    ftyp = _bmff_box(b"ftyp", b"crx " + b"\x00" * 16)
    moov = _bmff_box(b"moov", b"\x00" * 40)
    mdat = _bmff_box(b"mdat", b"\x00" * 500)
    return ftyp + moov + mdat


class TestJpegExtent(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_simple_jpeg_finds_real_eoi(self):
        data = _simple_jpeg()
        path = _write(self.tmpdir.name, "a.jpg", data)
        with open(path, "rb") as f:
            end = _jpeg_extent(f, 0, len(data))
        self.assertEqual(end, len(data))

    def test_does_not_truncate_at_embedded_thumbnail_eoi(self):
        data = _jpeg_with_embedded_thumbnail()
        path = _write(self.tmpdir.name, "b.jpg", data)
        with open(path, "rb") as f:
            end = _jpeg_extent(f, 0, len(data))
        self.assertEqual(end, len(data))


class TestTiffExtent(unittest.TestCase):
    def test_extent_and_make_detection(self):
        data = _build_tiff(make=b"Canon\x00", strip_offset=60, strip_size=1000)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "x.cr2", data)
            with open(path, "rb") as f:
                result = _tiff_extent_and_make(f, 0, len(data))
        self.assertIsNotNone(result)
        end, make = result
        self.assertEqual(end, 1060)
        self.assertEqual(make, "canon")

    def test_nonzero_start_offset(self):
        tiff = _build_tiff(make=b"NIKON CORPORATION\x00", strip_offset=80, strip_size=500)
        padding = b"\x00" * 200
        data = padding + tiff
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "y.bin", data)
            with open(path, "rb") as f:
                result = _tiff_extent_and_make(f, 200, len(data))
        self.assertIsNotNone(result)
        end, make = result
        self.assertEqual(end, 200 + 80 + 500)
        self.assertEqual(make, "nikon corporation")


class TestRafExtent(unittest.TestCase):
    def test_extent_from_header_offsets(self):
        data = _build_raf(cfa_offset=400, cfa_length=2000)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "z.raf", data)
            with open(path, "rb") as f:
                end = _raf_extent(f, 0, len(data))
        self.assertEqual(end, 2400)


class TestCr3Extent(unittest.TestCase):
    def test_extent_from_box_walk(self):
        data = _build_cr3()
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "w.cr3", data)
            with open(path, "rb") as f:
                end = _cr3_extent(f, 0, len(data))
        self.assertEqual(end, len(data))


class TestCarveIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_carves_tiff_raf_cr3_and_jpeg_from_one_image(self):
        tiff = _build_tiff(make=b"SONY\x00", strip_offset=60, strip_size=300)
        raf = _build_raf(cfa_offset=200, cfa_length=300)
        cr3 = _build_cr3()
        jpeg = _simple_jpeg()
        image = tiff + raf + cr3 + jpeg
        path = _write(self.tmpdir.name, "card.img", image)
        out_dir = os.path.join(self.tmpdir.name, "out")

        results = carve(path, out_dir)
        kinds = [r["kind"] for r in results]
        self.assertEqual(kinds, ["tiff", "raf", "cr3", "jpeg"])

        tiff_r = results[0]
        self.assertEqual(tiff_r["start"], 0)
        self.assertEqual(tiff_r["size"], len(tiff))
        self.assertTrue(tiff_r["out_path"].endswith(".arw"))

        raf_r = results[1]
        self.assertEqual(raf_r["start"], len(tiff))
        self.assertEqual(raf_r["size"], len(raf))

        cr3_r = results[2]
        self.assertEqual(cr3_r["start"], len(tiff) + len(raf))
        self.assertEqual(cr3_r["size"], len(cr3))

        jpeg_r = results[3]
        self.assertEqual(jpeg_r["start"], len(tiff) + len(raf) + len(cr3))
        self.assertEqual(jpeg_r["size"], len(jpeg))

        for r in results:
            self.assertEqual(os.path.getsize(r["out_path"]), r["size"])

    def test_x3f_heuristic_truncated_by_next_signature(self):
        x3f_data = b"FOVb" + b"\x00" * 20  # 24 bytes
        jpeg = _simple_jpeg()
        image = x3f_data + jpeg
        path = _write(self.tmpdir.name, "card2.img", image)
        out_dir = os.path.join(self.tmpdir.name, "out2")

        results = carve(path, out_dir)
        self.assertEqual(len(results), 2)
        x3f_r, jpeg_r = results
        self.assertEqual(x3f_r["kind"], "x3f")
        self.assertEqual(x3f_r["start"], 0)
        self.assertEqual(x3f_r["end"], len(x3f_data))
        self.assertTrue(x3f_r["approx"])

        self.assertEqual(jpeg_r["kind"], "jpeg")
        self.assertEqual(jpeg_r["start"], len(x3f_data))
        self.assertEqual(jpeg_r["size"], len(jpeg))
        self.assertFalse(jpeg_r["approx"])


if __name__ == "__main__":
    unittest.main()
