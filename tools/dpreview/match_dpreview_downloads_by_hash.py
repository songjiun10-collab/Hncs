"""dpreview 위젯 DB RAW를 브라우저 `<a>`+blob 다운로드로 받을 때, 이 앱
샌드박스가 실제 파일명을 익명 해시(`.Q6L2SF6YDW.com.anthropic.claudefordesktop.*`)로
바꿔버려서 어떤 이미지 id에 해당하는지 알 수 없다 - 같은 스튜디오씬
RAW는 파일 사이즈도 거의 동일해서(몇 바이트 차이) 사이즈 매칭도
충돌 다발. 콘텐츠 SHA-256으로 정확히 매칭한다.

짝을 이루는 브라우저 쪽 코드(사용자가 승인한 브라우저 pane에서
`javascript_tool`로 실행): 반드시 **순차**(await 체인, `Promise.all`
금지)로 fetch+해시+다운로드해야 한다 - 병렬로 여러 개를 한 번에
트리거하면 크롬이 "자동 다운로드 남발" 방지로 대부분 조용히 드롭하고,
반대로 `setTimeout` 지연을 넣으면 이 pane이 숨겨진 탭 취급을 받아
스로틀링이 심해서 몇 배로 느려진다. 순차 await는 fetch+해시 계산
자체가 자연스러운 텀이 되어 둘 다 피한다.

```js
async function run(items, prefix) {
  const results = [];
  for (const item of items) {
    const res = await fetch(item.url);
    const buf = await res.arrayBuffer();
    const hashBuf = await crypto.subtle.digest('SHA-256', buf);
    const hash = Array.from(new Uint8Array(hashBuf)).map(b=>b.toString(16).padStart(2,'0')).join('');
    const blob = new Blob([buf]);
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `${prefix}_${item.id}.dng`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(blobUrl);
    results.push({id: item.id, hash, size: buf.byteLength});
  }
  return results;
}
```

`items`는 dpreview 위젯 API(`wp-json/wayfinder-image-compare/v1/widgets/<id>/frontend`
의 `images`를 `product_id`+`filetype==="Raw"`로 필터한 `{id, url}` 배열
- `EVALUATION.md` "dpreview 스튜디오씬 비교위젯" 절 참고. 결과
(`{id, hash, size}` 배열)를 이 스크립트의 `match_and_copy()`에 넘기면
된다. `datasets/leica/contributed/dpreview-*-studio-chart-2026-09/`
9바디를 이 방식으로 받았다(2026-09-04).
"""
import hashlib
import os
import shutil

DOWNLOADS = "/Users/songjiun/Downloads"
_DOWNLOAD_PREFIX = ".Q6L2SF6YDW"  # 이 머신/앱 인스턴스 한정, 다른 환경이면 바뀔 수 있음


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def match_and_copy(hashes, prefix, dest_dir, cutoff_mtime, ext="dng"):
    """hashes: [{"id":..., "hash":..., "size":...}, ...] (브라우저 run()의 반환값).
    cutoff_mtime 이후 Downloads에 새로 생긴 익명 파일들을 SHA-256으로
    hashes와 매칭해 dest_dir/{prefix}_{id}.{ext}로 복사하고 원본은 지운다.
    (matched_ids, missing_ids) 반환 - missing이 있으면 그 id만 다시
    브라우저에서 받아 재호출하면 됨(다운로드가 아직 진행 중이었거나
    크롬이 드롭했을 때 발생)."""
    os.makedirs(dest_dir, exist_ok=True)
    by_hash = {h["hash"]: h["id"] for h in hashes}
    candidates = [
        os.path.join(DOWNLOADS, fn)
        for fn in os.listdir(DOWNLOADS)
        if fn.startswith(_DOWNLOAD_PREFIX)
        and os.path.getmtime(os.path.join(DOWNLOADS, fn)) > cutoff_mtime
    ]
    matched, unmatched_files = [], []
    for p in candidates:
        img_id = by_hash.get(sha256_of(p))
        if img_id is None:
            unmatched_files.append(p)
            continue
        shutil.copy(p, os.path.join(dest_dir, f"{prefix}_{img_id}.{ext}"))
        os.remove(p)
        matched.append(img_id)
    missing = sorted(set(h["id"] for h in hashes) - set(matched))
    print(f"matched {len(matched)}/{len(hashes)}; missing ids: {missing}; "
          f"unmatched leftover files: {len(unmatched_files)}")
    return matched, missing


if __name__ == "__main__":
    print("import this module and call match_and_copy(...) instead of running directly")
