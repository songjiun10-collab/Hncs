"""시그니처 기반 파일 카빙(PhotoRec류) - `core/sdcard_undelete.py`의
파일시스템 복구가 실패한 파일(포맷된 카드, FAT/디렉토리 손상)을 위한
폴백. 이미지 전체를 알려진 매직 바이트로 훑어 파일 "시작"을 찾고,
포맷별로 "끝"을 계산한 뒤 그 구간을 그대로 잘라낸다.

**끝 계산 정확도는 포맷마다 다르다**(솔직하게):
- **JPEG**: 정확. SOI 다음 세그먼트를 하나씩 걸으며 길이 필드로
  건너뛰다 SOS를 만나면 그 뒤(엔트로피 데이터)에서 진짜 EOI(0xFFD9)를
  찾는다 - "SOI 다음 첫 EOI"로 자르면 EXIF 썸네일(그 자체가 완결된
  JPEG라 자기 EOI를 갖고 있다)에서 끊겨버리는 흔한 카빙 버그를 피한다.
- **TIFF 기반 RAW**(CR2/NEF/ARW/ORF/RW2/PEF/DNG/3FR/FFF/IIQ 등 - 대부분의
  RAW가 여기 속한다): IFD 체인 + SubIFD(태그 330)를 걸으며 발견되는
  모든 StripOffsets/StripByteCounts, TileOffsets/TileByteCounts의
  최댓값(offset+bytecount)으로 끝을 추정한다 - Make(271) 태그로
  브랜드를 읽어 확장자를 붙인다. 일부 벤더가 메이커노트 안에 감춰둔
  비표준 오프셋은 못 잡는다 - 그래서 다음 감지된 파일 시작 시그니처가
  이 추정 끝보다 앞이면 거기서 자르는 안전망을 전 포맷에 공통 적용한다.
- **RAF(Fuji)**: 정확. 헤더(84~107바이트, 빅엔디안)에 CFA 오프셋+길이가
  그대로 박혀있다(libopenraw 문서 확인) - `cfa_offset + cfa_length`가
  곧 파일 끝.
- **CR3(Canon)**: 정확. ISO 기반 미디어 파일(BMFF)이라 각 박스가 자기
  크기를 갖고 있어 ftyp부터 순서대로 박스를 걸으며 더하면 끝.
- **X3F(Sigma)**: 근사치만. 디렉토리가 파일 "끝"에 있어(꼬리에 크기를
  적는 구조) 카빙 시점엔 아직 모른다 - "FOVb" 매직만 확인하고 넉넉한
  최대 크기로 자른 뒤 다음 파일 시작 안전망에 맡긴다. 결과의
  `approx=True`로 표시.

이미지를 통째로 메모리에 올리지 않는다(100MP 프레임 하나도 OOM났던
전례가 있다 - `tools/CLAUDE.md`) - 시그니처 스캔은 청크(64MB) + 겹침
버퍼로, 실제 헤더 파싱/복사는 파일 핸들에 직접 seek/read한다.
"""
import os
import struct

_CHUNK = 64 * 1024 * 1024
_OVERLAP = 4096
_WRITE_BLOCK = 1 << 20

_JPEG_SOI = b"\xff\xd8\xff"
_TIFF_LE = b"II*\x00"
_TIFF_BE = b"MM\x00*"
_RAF_MAGIC = b"FUJIFILMCCD-RAW "
_X3F_MAGIC = b"FOVb"
_CR3_TRIGGER = b"ftypcrx "

_MAX_JPEG_SIZE = 100 * 1024 * 1024
_MAX_TIFF_IFD_OFFSET = 4 * 1024 * 1024
_MAX_RAW_FILE_SIZE = 500 * 1024 * 1024
_MAX_CR3_SIZE = 500 * 1024 * 1024
_MAX_X3F_SIZE = 100 * 1024 * 1024

TIFF_MAKE_EXTENSIONS = {
    "canon": ".cr2",
    "nikon corporation": ".nef",
    "sony": ".arw",
    "olympus": ".orf",
    "olympus corporation": ".orf",
    "om digital solutions": ".orf",
    "panasonic": ".rw2",
    "pentax": ".pef",
    "ricoh imaging company, ltd.": ".pef",
    "hasselblad": ".3fr",
    "phase one": ".iiq",
    "leica camera ag": ".dng",
    "leica camera gmbh": ".dng",
}
_DEFAULT_TIFF_EXT = ".tif"


def _read_at(f, offset, length):
    if offset < 0 or length <= 0:
        return b""
    f.seek(offset)
    return f.read(length)


# ---------------------------------------------------------------------------
# JPEG - 세그먼트 인지 카빙(임베디드 썸네일 EOI 문제 회피)
# ---------------------------------------------------------------------------

def _jpeg_extent(f, start, file_size):
    pos = start + 2
    limit = min(file_size, start + _MAX_JPEG_SIZE)
    while pos + 4 <= limit:
        head = _read_at(f, pos, 4)
        if len(head) < 2 or head[0] != 0xFF:
            return None
        marker = head[1]
        if marker == 0xD9:
            return pos + 2
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if len(head) < 4:
            return None
        seg_len = struct.unpack(">H", head[2:4])[0]
        if seg_len < 2:
            return None
        if marker == 0xDA:
            return _scan_for_eoi(f, pos + 2 + seg_len, limit)
        pos += 2 + seg_len
    return None


def _scan_for_eoi(f, pos, limit):
    while pos < limit:
        chunk = _read_at(f, pos, min(1 << 20, limit - pos))
        if not chunk:
            return None
        idx = 0
        while True:
            idx = chunk.find(b"\xff", idx)
            if idx == -1 or idx + 1 >= len(chunk):
                break
            nxt = chunk[idx + 1]
            if nxt == 0xD9:
                return pos + idx + 2
            idx += 1
        pos += max(len(chunk) - 1, 1)
    return None


def _jpeg_extent_fn(f, start, file_size):
    end = _jpeg_extent(f, start, file_size)
    return (end, ".jpg", False) if end else (None, None, False)


# ---------------------------------------------------------------------------
# TIFF 기반 RAW - IFD/SubIFD 체인에서 Strip/Tile Offsets+ByteCounts 최댓값
# ---------------------------------------------------------------------------

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _uint(data, offset, size, le):
    return int.from_bytes(data[offset:offset + size], "little" if le else "big")


def _decode_ifd_entry(f, base, entry, le):
    tag = _uint(entry, 0, 2, le)
    typ = _uint(entry, 2, 2, le)
    cnt = _uint(entry, 4, 4, le)
    type_size = _TYPE_SIZES.get(typ, 0)
    if type_size == 0 or cnt <= 0 or cnt > 100000:
        return tag, []
    total = type_size * cnt
    if total <= 4:
        raw = entry[8:8 + total]
    else:
        off = _uint(entry, 8, 4, le)
        raw = _read_at(f, base + off, total)
        if len(raw) < total:
            return tag, []
    if typ == 2:  # ASCII
        return tag, [raw]
    if typ in (3, 8):  # SHORT
        return tag, [_uint(raw, i * 2, 2, le) for i in range(cnt)]
    if typ in (4, 9, 13):  # LONG
        return tag, [_uint(raw, i * 4, 4, le) for i in range(cnt)]
    return tag, [raw]


def _tiff_extent_and_make(f, start, file_size):
    header = _read_at(f, start, 8)
    if len(header) < 8:
        return None
    if header[:4] == _TIFF_LE:
        le = True
    elif header[:4] == _TIFF_BE:
        le = False
    else:
        return None
    ifd0_offset = _uint(header, 4, 4, le)
    if not (8 <= ifd0_offset < _MAX_TIFF_IFD_OFFSET):
        return None

    max_extent = 0
    make = None
    visited = set()

    def walk(ifd_offset, depth):
        nonlocal max_extent, make
        if depth > 4 or ifd_offset in visited or ifd_offset <= 0:
            return
        visited.add(ifd_offset)
        abs_off = start + ifd_offset
        count_raw = _read_at(f, abs_off, 2)
        if len(count_raw) < 2:
            return
        count = _uint(count_raw, 0, 2, le)
        if not (1 <= count <= 500):
            return
        entries_raw = _read_at(f, abs_off + 2, count * 12)
        if len(entries_raw) < count * 12:
            return
        tags = {}
        for i in range(count):
            tag, values = _decode_ifd_entry(f, start, entries_raw[i * 12:(i + 1) * 12], le)
            tags[tag] = values
        for offs_tag, cnts_tag in ((273, 279), (324, 325)):
            if offs_tag in tags and cnts_tag in tags:
                for o, c in zip(tags[offs_tag], tags[cnts_tag]):
                    if isinstance(o, int) and isinstance(c, int):
                        max_extent = max(max_extent, o + c)
        if make is None and 271 in tags and tags[271]:
            raw_make = tags[271][0]
            if isinstance(raw_make, bytes):
                s = raw_make.split(b"\x00")[0].decode("ascii", "replace").strip().lower()
                if s:
                    make = s
        next_ifd_raw = _read_at(f, abs_off + 2 + count * 12, 4)
        next_ifd = _uint(next_ifd_raw, 0, 4, le) if len(next_ifd_raw) == 4 else 0
        for sub in tags.get(330, []):
            if isinstance(sub, int):
                walk(sub, depth + 1)
        if next_ifd:
            walk(next_ifd, depth + 1)

    walk(ifd0_offset, 0)
    if max_extent <= 0:
        return None
    end = start + max_extent
    if end <= start + 8 or end - start > _MAX_RAW_FILE_SIZE or end > file_size:
        return None
    return end, make


def _tiff_extent_fn(f, start, file_size):
    result = _tiff_extent_and_make(f, start, file_size)
    if result is None:
        return None, None, False
    end, make = result
    ext = TIFF_MAKE_EXTENSIONS.get(make, _DEFAULT_TIFF_EXT) if make else _DEFAULT_TIFF_EXT
    return end, ext, False


# ---------------------------------------------------------------------------
# RAF(Fuji) - 헤더에 CFA 오프셋+길이가 그대로 있다
# ---------------------------------------------------------------------------

def _raf_extent(f, start, file_size):
    header = _read_at(f, start, 108)
    if len(header) < 108 or header[:16] != _RAF_MAGIC:
        return None
    (_jpeg_off, _jpeg_len, _cfa_hdr_off, _cfa_hdr_len,
     cfa_offset, cfa_length) = struct.unpack(">IIIIII", header[84:108])
    if cfa_offset <= 0 or cfa_length <= 0:
        return None
    end = start + cfa_offset + cfa_length
    if end <= start or end - start > _MAX_RAW_FILE_SIZE or end > file_size:
        return None
    return end


def _raf_extent_fn(f, start, file_size):
    end = _raf_extent(f, start, file_size)
    return (end, ".raf", False) if end else (None, None, False)


# ---------------------------------------------------------------------------
# CR3(Canon) - ISO BMFF 박스를 순서대로 걸으며 크기를 더한다
# ---------------------------------------------------------------------------

def _looks_like_box_type(t):
    return len(t) == 4 and all(0x20 <= c < 0x7F for c in t)


def _cr3_extent(f, start, file_size):
    pos = start
    limit = min(file_size, start + _MAX_CR3_SIZE)
    n_boxes = 0
    while pos + 8 <= limit and n_boxes < 128:
        head = _read_at(f, pos, 8)
        if len(head) < 8:
            break
        size = struct.unpack(">I", head[:4])[0]
        box_type = head[4:8]
        if n_boxes == 0 and box_type != b"ftyp":
            return None
        if not _looks_like_box_type(box_type):
            break
        header_len = 8
        if size == 1:
            ext = _read_at(f, pos + 8, 8)
            if len(ext) < 8:
                break
            size = struct.unpack(">Q", ext)[0]
            header_len = 16
        elif size == 0:
            size = limit - pos
        if size < header_len or pos + size > limit:
            break
        pos += size
        n_boxes += 1
    if n_boxes == 0:
        return None
    return pos


def _cr3_extent_fn(f, start, file_size):
    end = _cr3_extent(f, start, file_size)
    return (end, ".cr3", False) if end else (None, None, False)


# ---------------------------------------------------------------------------
# X3F(Sigma) - 디렉토리가 파일 끝에 있어 카빙 시점엔 정확한 크기를 모른다.
# 매직만 확인하고 넉넉한 상한 + 다음 파일 시작 안전망에 맡긴다(근사치).
# ---------------------------------------------------------------------------

def _x3f_extent_fn(f, start, file_size):
    end = min(start + _MAX_X3F_SIZE, file_size)
    return end, ".x3f", True


_EXTENT_FUNCS = {
    "jpeg": _jpeg_extent_fn,
    "tiff": _tiff_extent_fn,
    "raf": _raf_extent_fn,
    "cr3": _cr3_extent_fn,
    "x3f": _x3f_extent_fn,
}

_SIMPLE_SIGNATURES = [
    (_JPEG_SOI, "jpeg"),
    (_TIFF_LE, "tiff"),
    (_TIFF_BE, "tiff"),
    (_RAF_MAGIC, "raf"),
    (_X3F_MAGIC, "x3f"),
]


def _scan_candidates(f, file_size):
    """전체 이미지를 청크+겹침으로 훑어 (offset, kind) 후보를 모은다 -
    실제 파일 개수 대비 거짓양성(4바이트 TIFF 매직의 우연한 일치 등)은
    드물어서 전체를 리스트로 들고 있어도 메모리 문제가 없다."""
    candidates = []
    pos = 0
    while pos < file_size:
        read_len = min(_CHUNK, file_size - pos)
        f.seek(pos)
        buf = f.read(read_len)
        if not buf:
            break
        for magic, kind in _SIMPLE_SIGNATURES:
            idx = buf.find(magic)
            while idx != -1:
                candidates.append((pos + idx, kind))
                idx = buf.find(magic, idx + 1)
        idx = buf.find(_CR3_TRIGGER)
        while idx != -1:
            if pos + idx >= 4:
                candidates.append((pos + idx - 4, "cr3"))
            idx = buf.find(_CR3_TRIGGER, idx + 1)
        if read_len < _CHUNK:
            break
        pos += read_len - _OVERLAP
    candidates.sort()
    deduped = []
    seen = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def _write_extent(f, start, end, out_path):
    remaining = end - start
    f.seek(start)
    with open(out_path, "wb") as out:
        while remaining > 0:
            chunk = f.read(min(_WRITE_BLOCK, remaining))
            if not chunk:
                break
            out.write(chunk)
            remaining -= len(chunk)


def carve(image_path, out_dir):
    """이미지에서 시그니처로 파일을 찾아 out_dir에 잘라 쓴다. 각 결과
    항목: kind, start, end, size, out_path, approx(bool - 끝 추정이
    근사치인 경우 True: X3F는 항상, 그 외는 다음 파일 시작 안전망이
    실제로 잘라낸 경우)."""
    os.makedirs(out_dir, exist_ok=True)
    file_size = os.path.getsize(image_path)
    results = []
    with open(image_path, "rb") as f:
        candidates = _scan_candidates(f, file_size)
        cursor = 0
        for i, (offset, kind) in enumerate(candidates):
            if offset < cursor:
                continue
            end, ext, approx = _EXTENT_FUNCS[kind](f, offset, file_size)
            if end is None:
                continue
            for nxt_offset, _ in candidates[i + 1:]:
                if nxt_offset <= offset:
                    continue
                if nxt_offset < end:
                    end = nxt_offset
                    approx = True
                break
            if end <= offset:
                continue
            out_path = os.path.join(out_dir, f"carved_{len(results):05d}{ext}")
            _write_extent(f, offset, end, out_path)
            results.append({"kind": kind, "start": offset, "end": end,
                             "size": end - offset, "out_path": out_path, "approx": approx})
            cursor = end
    return results
