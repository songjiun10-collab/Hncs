"""SD카드(FAT32/exFAT) 이미지에서 삭제된 파일을 파일시스템 메타데이터로
복구한다 - 시그니처 카빙(`core/sdcard_carve.py`)보다 먼저 시도해야 하는
1차 경로. 디렉토리 엔트리와 클러스터 체인이 아직 살아있으면(포맷 전
단순 삭제) 원본 파일명/크기를 그대로 복구할 수 있어 카빙보다 훨씬
정확하다.

**FAT32**: 삭제 시 짧은 이름(8.3)의 첫 바이트가 0xE5로 덮이므로 그
글자는 영원히 복구 불가(관례대로 "_"로 치환) - 긴 파일명(LFN) 엔트리는
순번 바이트까지 0xE5로 덮여 순서를 못 맞춰 아예 버린다. 클러스터
체인은 FAT 테이블에 남아있으면 그대로 따라가고, 포맷 등으로 FAT가
초기화됐으면(체인이 비었거나 말이 안 되면) "카메라 파일은 대개 연속
할당"이라는 경험칙으로 파일 크기만큼 first_cluster부터 순번대로 읽는다
(PhotoRec 등 실제 도구도 쓰는 폴백) - 그마저 범위를 벗어나면 이 파일은
포기하고 카빙에 맡긴다.

**exFAT**: 삭제가 엔트리 타입 바이트의 InUse 비트(0x80)만 지우는
논리적 삭제라 이름/크기/타임스탬프가 새 데이터로 덮이기 전까진 그대로
남아있다 - FAT32보다 완전한 복구가 가능하다. 게다가 스트림 확장
엔트리의 NoFatChain 플래그가 서 있으면(사진처럼 이어서 한 번에 쓴
파일은 보통 이렇다) FAT 테이블을 아예 안 보고 first_cluster부터
ValidDataLength만큼 그냥 연속으로 읽으면 되므로 FAT가 초기화된
뒤에도 복구된다.

두 경우 다 디렉토리 트리(루트 + 하위 폴더, 예: DCIM/100XXXXX)를
재귀적으로 훑어 살아있는 엔트리와 삭제된 엔트리를 모두 찾는다 - 삭제된
디렉토리 자체도(그 클러스터 체인이 살아있다면) 하위까지 훑는다.
"""
import os
import struct

_FAT32_EOC_MIN = 0x0FFFFFF8
_FAT32_BAD = 0x0FFFFFF7
_EXFAT_EOC = 0xFFFFFFFF
_EXFAT_BAD = 0xFFFFFFF7


def detect_filesystem(path):
    """볼륨 부트섹터를 읽어 "fat32" / "exfat" / "unknown" 반환."""
    with open(path, "rb") as f:
        boot = f.read(90)
    if len(boot) < 90:
        return "unknown"
    if boot[3:11] == b"EXFAT   ":
        return "exfat"
    if boot[82:90] == b"FAT32   ":
        return "fat32"
    return "unknown"


# ---------------------------------------------------------------------------
# FAT32
# ---------------------------------------------------------------------------

class _Fat32Geometry:
    def __init__(self, boot):
        (self.bytes_per_sector, self.sectors_per_cluster, self.reserved_sectors,
         self.num_fats) = struct.unpack_from("<HBHB", boot, 11)
        self.fat_size_32, = struct.unpack_from("<I", boot, 36)
        self.root_cluster, = struct.unpack_from("<I", boot, 44)
        self.total_sectors_32, = struct.unpack_from("<I", boot, 32)
        self.fat_offset = self.reserved_sectors * self.bytes_per_sector
        self.data_offset = (self.reserved_sectors +
                             self.num_fats * self.fat_size_32) * self.bytes_per_sector
        self.cluster_size = self.sectors_per_cluster * self.bytes_per_sector
        self.total_clusters = (self.total_sectors_32 * self.bytes_per_sector -
                                self.data_offset) // self.cluster_size

    def cluster_offset(self, cluster):
        return self.data_offset + (cluster - 2) * self.cluster_size


def _fat32_next_cluster(f, geo, cluster):
    f.seek(geo.fat_offset + cluster * 4)
    raw = f.read(4)
    if len(raw) < 4:
        return None
    return struct.unpack("<I", raw)[0] & 0x0FFFFFFF


def _fat32_read_chain(f, geo, first_cluster, size):
    """기록된 FAT 체인을 따라가되, 첫 클러스터부터 말이 안 되면(비어있음
    등) None을 반환해 호출자가 연속-할당 폴백을 쓰게 한다."""
    if first_cluster < 2 or first_cluster >= geo.total_clusters + 2:
        return None
    clusters = []
    remaining = size
    cur = first_cluster
    seen = set()
    while remaining > 0:
        if cur in seen or cur < 2 or cur >= _FAT32_BAD:
            return None
        seen.add(cur)
        clusters.append(cur)
        remaining -= geo.cluster_size
        if remaining <= 0:
            break
        nxt = _fat32_next_cluster(f, geo, cur)
        if nxt is None or nxt == 0 or nxt >= _FAT32_EOC_MIN:
            if remaining > 0:
                return None
            break
        cur = nxt
    return clusters


def _fat32_contiguous_chain(geo, first_cluster, size):
    n = (size + geo.cluster_size - 1) // geo.cluster_size
    if n == 0:
        n = 1
    clusters = list(range(first_cluster, first_cluster + n))
    if clusters[-1] >= geo.total_clusters + 2:
        return None
    return clusters


def _fat32_write_clusters(f, geo, clusters, size, out_path):
    remaining = size
    with open(out_path, "wb") as out:
        for c in clusters:
            f.seek(geo.cluster_offset(c))
            chunk = f.read(min(geo.cluster_size, remaining))
            out.write(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break


def _fat32_full_chain(f, geo, first_cluster):
    """크기를 모르는 체인(디렉토리)을 EOC까지 그대로 따라간다 - 파일
    복구용 `_fat32_read_chain`과 달리 "몇 바이트가 필요한지" 미리 알
    필요가 없다."""
    if first_cluster < 2 or first_cluster >= geo.total_clusters + 2:
        return
    cur = first_cluster
    seen = set()
    while cur not in seen and 2 <= cur < _FAT32_BAD:
        seen.add(cur)
        yield cur
        nxt = _fat32_next_cluster(f, geo, cur)
        if nxt is None or nxt == 0 or nxt >= _FAT32_EOC_MIN:
            return
        cur = nxt


def _fat32_iter_dir_entries(f, geo, first_cluster):
    """(루트 포함) 한 디렉토리의 원본 32바이트 엔트리를 순서대로 낸다."""
    for c in _fat32_full_chain(f, geo, first_cluster):
        f.seek(geo.cluster_offset(c))
        data = f.read(geo.cluster_size)
        for off in range(0, len(data), 32):
            entry = data[off:off + 32]
            if len(entry) < 32:
                continue
            if entry[0] == 0x00:
                return
            yield entry


def _fat32_short_name(entry, deleted):
    name_raw = bytearray(entry[0:11])
    if deleted:
        name_raw[0] = ord("_")
    base = name_raw[0:8].decode("ascii", "replace").rstrip()
    ext = name_raw[8:11].decode("ascii", "replace").rstrip()
    return f"{base}.{ext}" if ext else base


def _fat32_walk(f, geo, first_cluster, rel_path, out_dir, results):
    for entry in _fat32_iter_dir_entries(f, geo, first_cluster):
        attr = entry[11]
        if attr == 0x0F:
            continue  # 긴 파일명 조각 - 순번 복구 불가하므로 무시
        first_byte = entry[0]
        if first_byte in (0x2E,):
            continue  # "." / ".."
        deleted = first_byte == 0xE5
        if attr & 0x08:
            continue  # 볼륨 라벨
        cluster_hi, cluster_lo, size = struct.unpack_from("<HxxxxHI", entry, 20)
        cluster = (cluster_hi << 16) | cluster_lo
        name = _fat32_short_name(entry, deleted)
        is_dir = bool(attr & 0x10)
        if is_dir:
            if cluster >= 2:
                _fat32_walk(f, geo, cluster, os.path.join(rel_path, name), out_dir, results)
            continue
        if not deleted or size == 0:
            continue
        chain = _fat32_read_chain(f, geo, cluster, size)
        method = "fat_chain"
        if chain is None:
            chain = _fat32_contiguous_chain(geo, cluster, size)
            method = "contiguous_guess"
        if chain is None:
            results.append({"name": name, "path": os.path.join(rel_path, name),
                             "size": size, "recovered": False, "method": None})
            continue
        safe_name = f"{len(results):04d}_{name}"
        out_path = os.path.join(out_dir, safe_name)
        _fat32_write_clusters(f, geo, chain, size, out_path)
        results.append({"name": name, "path": os.path.join(rel_path, name), "size": size,
                         "recovered": True, "method": method, "out_path": out_path})


def recover_fat32(image_path, out_dir):
    """FAT32 이미지에서 삭제된 파일을 복구해 out_dir에 쓰고 결과 리스트를
    반환한다. 각 항목: name(짧은 이름, 첫 글자 유실), path(디렉토리
    포함), size, recovered(bool), method("fat_chain"|"contiguous_guess"|
    None), out_path(recovered=True일 때만)."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    with open(image_path, "rb") as f:
        boot = f.read(90)
        geo = _Fat32Geometry(boot)
        _fat32_walk(f, geo, geo.root_cluster, "", out_dir, results)
    return results


# ---------------------------------------------------------------------------
# exFAT
# ---------------------------------------------------------------------------

class _ExfatGeometry:
    def __init__(self, boot):
        (fat_offset_sectors, fat_length_sectors, cluster_heap_offset_sectors,
         cluster_count, first_cluster_root) = struct.unpack_from("<IIIII", boot, 80)
        bytes_per_sector_shift = boot[112]
        sectors_per_cluster_shift = boot[113]
        self.bytes_per_sector = 1 << bytes_per_sector_shift
        self.cluster_size = 1 << (bytes_per_sector_shift + sectors_per_cluster_shift)
        self.fat_offset = fat_offset_sectors * self.bytes_per_sector
        self.cluster_heap_offset = cluster_heap_offset_sectors * self.bytes_per_sector
        self.cluster_count = cluster_count
        self.root_cluster = first_cluster_root

    def cluster_offset(self, cluster):
        return self.cluster_heap_offset + (cluster - 2) * self.cluster_size


def _exfat_next_cluster(f, geo, cluster):
    f.seek(geo.fat_offset + cluster * 4)
    raw = f.read(4)
    if len(raw) < 4:
        return None
    return struct.unpack("<I", raw)[0]


def _exfat_read_chain(f, geo, first_cluster, size, no_fat_chain):
    if first_cluster < 2 or first_cluster >= geo.cluster_count + 2:
        return None
    n_needed = (size + geo.cluster_size - 1) // geo.cluster_size
    n_needed = max(n_needed, 1)
    if no_fat_chain:
        clusters = list(range(first_cluster, first_cluster + n_needed))
        if clusters[-1] >= geo.cluster_count + 2:
            return None
        return clusters
    clusters = []
    remaining = size
    cur = first_cluster
    seen = set()
    while remaining > 0:
        if cur in seen or cur < 2 or cur >= _EXFAT_BAD:
            return None
        seen.add(cur)
        clusters.append(cur)
        remaining -= geo.cluster_size
        if remaining <= 0:
            break
        nxt = _exfat_next_cluster(f, geo, cur)
        if nxt is None or nxt == 0 or nxt == _EXFAT_EOC:
            return None
        cur = nxt
    return clusters


def _exfat_write_clusters(f, geo, clusters, size, out_path):
    remaining = size
    with open(out_path, "wb") as out:
        for c in clusters:
            f.seek(geo.cluster_offset(c))
            chunk = f.read(min(geo.cluster_size, remaining))
            out.write(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break


def _exfat_full_chain(f, geo, first_cluster, no_fat_chain):
    """크기를 모르는 체인(디렉토리)을 그대로 따라간다 - NoFatChain이면
    클러스터 힙 끝까지 연속으로, 아니면 FAT 체인을 EOC까지."""
    if first_cluster < 2 or first_cluster >= geo.cluster_count + 2:
        return
    if no_fat_chain:
        c = first_cluster
        while c < geo.cluster_count + 2:
            yield c
            c += 1
        return
    cur = first_cluster
    seen = set()
    while cur not in seen and 2 <= cur < _EXFAT_BAD:
        seen.add(cur)
        yield cur
        nxt = _exfat_next_cluster(f, geo, cur)
        if nxt is None or nxt == 0 or nxt == _EXFAT_EOC:
            return
        cur = nxt


def _exfat_iter_dir_entries(f, geo, first_cluster, no_fat_chain):
    for c in _exfat_full_chain(f, geo, first_cluster, no_fat_chain):
        f.seek(geo.cluster_offset(c))
        data = f.read(geo.cluster_size)
        for off in range(0, len(data), 32):
            entry = data[off:off + 32]
            if len(entry) < 32:
                continue
            if entry[0] == 0x00:
                return
            yield entry


def _exfat_walk(f, geo, first_cluster, rel_path, out_dir, results, dir_no_fat_chain=False):
    entries = list(_exfat_iter_dir_entries(f, geo, first_cluster, dir_no_fat_chain))
    i = 0
    while i < len(entries):
        entry = entries[i]
        entry_type = entry[0]
        base_type = entry_type & 0x7F
        in_use = bool(entry_type & 0x80)
        if base_type != 0x05:  # 0x85(사용중)/0x05(삭제) 파일 디렉토리 엔트리만 관심
            i += 1
            continue
        secondary_count = entry[1]
        attrs, = struct.unpack_from("<H", entry, 4)
        is_dir = bool(attrs & 0x10)
        if i + secondary_count >= len(entries):
            i += 1
            continue
        stream = entries[i + 1]
        if (stream[0] & 0x7F) != 0x40:
            i += 1
            continue
        flags = stream[1]
        no_fat_chain = bool(flags & 0x02)
        name_length = stream[3]
        valid_data_length, = struct.unpack_from("<Q", stream, 8)
        first_cluster_val, = struct.unpack_from("<I", stream, 20)
        chars = []
        remaining_chars = name_length
        for j in range(2, secondary_count + 1):
            name_entry = entries[i + j]
            if (name_entry[0] & 0x7F) != 0x41:
                continue
            raw = name_entry[2:32]
            take = min(remaining_chars, 15)
            chars.append(raw[:take * 2].decode("utf-16-le", "replace"))
            remaining_chars -= take
        name = "".join(chars) if chars else "(unknown)"
        deleted = not in_use
        if is_dir:
            if first_cluster_val >= 2:
                _exfat_walk(f, geo, first_cluster_val, os.path.join(rel_path, name),
                            out_dir, results, dir_no_fat_chain=no_fat_chain)
            i += secondary_count + 1
            continue
        if not deleted or valid_data_length == 0:
            i += secondary_count + 1
            continue
        chain = _exfat_read_chain(f, geo, first_cluster_val, valid_data_length, no_fat_chain)
        method = "contiguous_no_fat_chain" if no_fat_chain else "fat_chain"
        if chain is None and not no_fat_chain:
            chain = _exfat_read_chain(f, geo, first_cluster_val, valid_data_length, True)
            method = "contiguous_guess"
        if chain is None:
            results.append({"name": name, "path": os.path.join(rel_path, name),
                             "size": valid_data_length, "recovered": False, "method": None})
            i += secondary_count + 1
            continue
        safe_name = f"{len(results):04d}_{name}"
        out_path = os.path.join(out_dir, safe_name)
        _exfat_write_clusters(f, geo, chain, valid_data_length, out_path)
        results.append({"name": name, "path": os.path.join(rel_path, name),
                         "size": valid_data_length, "recovered": True, "method": method,
                         "out_path": out_path})
        i += secondary_count + 1


def recover_exfat(image_path, out_dir):
    """exFAT 이미지에서 삭제된 파일을 복구해 out_dir에 쓰고 결과 리스트를
    반환한다. exFAT은 삭제가 논리적(엔트리 타입의 InUse 비트만 해제)이라
    FAT32와 달리 원본 파일명이 그대로 남아있는 경우가 많다."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    with open(image_path, "rb") as f:
        boot = f.read(120)
        geo = _ExfatGeometry(boot)
        _exfat_walk(f, geo, geo.root_cluster, "", out_dir, results)
    return results
