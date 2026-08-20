# darktable vs rawpy RAW 디코드 비교 실험 (설계)

## 배경

직전 실험(`docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md`)에서
rawpy 안에서 데모자이크 알고리즘만 바꾸는 접근(DHT)이 X-Trans에서는
아예 무의미하다는 게 밝혀졌다(LibRaw가 quality>2 알고리즘을 전부 같은
Markesteijn 경로로 합침). 그 문서의 "다음 단계"에서 이미 "darktable-cli
도입도 '더 나은 데모자이크를 위해서'라는 이유로는 동기가 약해졌다"고
적어뒀다.

이번 요청은 그 동기와 다르다: 데모자이크 하나만 바꾸는 게 아니라
**RAW 디코드 프로그램 자체를 rawpy(LibRaw)에서 darktable로 바꿔서
비교**한다 - 데모자이크뿐 아니라 카메라 매트릭스(colorin), 화이트밸런스,
하이라이트 복구 등 파이프라인 전체가 다른 프로그램이라 rawpy 안에서는
볼 수 없었던 차이가 있을 수 있다. 범위는 핫셀블라드(기존 raw+jpeg
13쌍)와 Fuji(기존 3쌍) 둘 다 - 사용자가 명시적으로 "하셀도 적용"이라고
요청함.

**중요한 스코프 결정(사용자 확인 완료)**: `decode_raw()`를 darktable로
**교체하지 않는다**. 기존 모든 브랜드의 매트릭스/커브(`hasselblad.json`,
DCP 프로파일 등)는 rawpy 출력에 맞춰 피팅돼 있어서, 디코더를 바꾸면
전부 무효화된다. 대신 `decode_raw_darktable()`이라는 **별도 함수**를
추가해서 이 비교 실험 전용으로만 쓴다 - 기존 파이프라인은 전혀
안 건드린다.

## 조사한 것

- `darktable-cli 4.6.1`은 apt로 설치 가능(`apt-get install darktable`,
  약 180개 패키지, GUI 스택 포함하지만 CLI만 쓴다). 이 컨테이너에
  실제로 설치해서 확인함.
- **기본 설정으로 export하면 톤매핑(filmic)이 걸려서 `decode_raw()`와
  비교 불가능하다**: `darktable-cli raw.RAF out.tif`만 실행하면
  파이프라인에 `filmicrgb`/`channelmixerrgb`가 자동 포함되고, 8비트
  sRGB로 나온다(같은 파일 기준 평균 104/255, 중앙값 97/255 - 시각적으로
  이미 톤매핑된 "완성 사진" 밝기다).
- **해결책 확인**: 아래 세 옵션을 조합하면 `decode_raw()`와 통계적으로
  비슷한 성격의(순수 선형) 결과가 나온다 - 실제 핫셀블라드 RAW
  (`raw_calib_cache/00378.jpg.3FR`)로 직접 비교 확인함:
  - `--icc-type LIN_REC709`: 출력을 선형(감마 없음), Rec.709 프라이머리
    (sRGB와 같은 프라이머리)로 - `decode_raw()`의 `gamma=(1,1)`,
    `output_color=rawpy.ColorSpace.sRGB`와 대응.
  - `--core --conf plugins/imageio/format/tiff/bpp=32`: 32비트 float
    TIFF export(8비트로는 이 비교에 정밀도가 부족).
  - `--conf plugins/darkroom/workflow=none`: darktable의 "scene-referred
    workflow" 자동 적용을 꺼서 filmicrgb/노출 모듈이 기본 히스토리
    스택에 안 들어가게 한다 - **이게 핵심**, 이거 없이는 톤매핑을
    피할 방법이 없었다.
  - 결과 비교(같은 핫셀블라드 RAW 파일 1장, `raw_calib_cache/00378.jpg.3FR`):

    | | `decode_raw()`(rawpy) | 위 설정의 darktable-cli |
    |---|---|---|
    | 평균 | 0.0265 | 0.0217 |
    | 중앙값(p50) | 0.0135 | 0.0110 |
    | p99 | 0.232 | 0.190 |
    | 최소값 | 0.0(클립됨) | -0.248(클립 안 됨) |

    완전히 같지는 않다(다른 카메라 매트릭스/화이트밸런스 계산 로직을
    쓰니 당연히 다름) - 하지만 같은 "순수 선형, 톤매핑 없음" 성격의
    결과라 공정 비교의 기반이 된다. darktable 출력은 음수를 클립하지
    않으므로 읽어올 때 0으로 클립해서 `decode_raw()`와 하한을 맞춘다.
  - 처리 시간: 핫셀블라드 100MP 파일 1장에 darktable-cli export가
    약 13초 걸렸다(`decode_raw()`는 수 초 이내) - 16쌍(핫셀블라드
    13 + Fuji 3)을 rawpy+darktable 양쪽 다 돌리면 총 실행 시간이
    수 분 걸릴 것으로 예상된다.

## 이번엔 결정론성부터 먼저 확인한다

직전 두 실험에서 사후에 발견한 문제:
1. HNCS 구조 실험(`docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md`) -
   n=13의 "4.1% 개선"이 통계적으로 노이즈와 구분 안 됨(재검증 후
   "판정 보류"로 정정).
2. Fuji 데모자이크 실험 - "작지만 진짜인 차이"가 사실 LibRaw의 X-Trans
   멀티스레드 디코드 논디터미니즘이었음(같은 파일을 반복 디코드해도
   약 1e-6 ΔE 수준 잡음이 낌 - 정정 후에야 발견).

이번 실험은 **비교를 신뢰하기 전에 노이즈 크기부터 먼저 잰다**:
`tools/evaluate_darktable_vs_rawpy.py`가 실제 16쌍 비교를 돌리기 전에,
대표 파일 1장(핫셀블라드 1장, Fuji 1장)을 각 백엔드로 두 번씩
디코드해서 "같은 입력을 반복 디코드했을 때 얼마나 다른가"(재현성
노이즈 바닥)를 먼저 측정하고 출력한다 - 이후 rawpy vs darktable의
ΔE 차이가 이 노이즈 바닥보다 작으면 결과를 "노이즈와 구분 불가"로
정직하게 표시한다.

`decode_raw()`(rawpy)는 이미 알려진 대로 X-Trans 파일에서 멀티스레드시
논디터미니즘이 있다(`OMP_NUM_THREADS=1`로 고정하면 사라짐) - 이
스크립트는 `OMP_NUM_THREADS=1`을 프로세스 환경변수로 고정해서 이
알려진 노이즈 원인을 원천 제거한 뒤 비교한다(핫셀블라드 Bayer 파일은
애초에 멀티스레드에서도 결정론적이었다는 게 직전 실험에서 이미
확인됨 - 이 고정은 주로 Fuji 페어를 위한 안전장치). darktable-cli
자체의 재현성은 알려진 바가 없어서 위 반복-디코드 체크로 직접 잰다.

## 설계

### 1. `hybrid_engine/utils/io.py`: `decode_raw_darktable()` 신규 함수

```python
def decode_raw_darktable(raw_path):
    """RAW -> Linear RGB, darktable-cli 경유(연구용 전용 - decode_raw()를
    대체하지 않는다). float64 [0, ~) 범위, shape (H, W, 3), RGB 순서,
    decode_raw()와 같은 sRGB(Rec.709) 프라이머리 기준 선형광 값이지만
    데모자이크/카메라 매트릭스/화이트밸런스를 rawpy(LibRaw)가 아니라
    darktable이 계산한다는 점이 다르다.

    subprocess로 darktable-cli를 호출해 32비트 float TIFF로 export한다.
    --icc-type LIN_REC709(선형, Rec.709 프라이머리)와
    plugins/darkroom/workflow=none(filmic/노출 자동보정 끔 - 안 끄면
    darktable 기본값이 톤매핑까지 적용해서 decode_raw()와 비교
    불가능한 결과가 나온다, 직접 확인함)이 핵심이다. darktable 출력은
    음수를 클립하지 않으므로 읽어온 뒤 0으로 클립해서 decode_raw()와
    하한을 맞춘다.

    subprocess+임시파일 기반이라 decode_raw()보다 훨씬 느리다(파일당
    10초 이상) - 프로덕션 경로가 아니라
    tools/evaluate_darktable_vs_rawpy.py 전용이다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "out.tif")
        result = subprocess.run(
            ["darktable-cli", raw_path, out_path,
             "--icc-type", "LIN_REC709", "--out-ext", "tif",
             "--core",
             "--conf", "plugins/imageio/format/tiff/bpp=32",
             "--conf", "plugins/darkroom/workflow=none"],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"darktable-cli failed for {raw_path}: {result.stderr}")
        bgr = cv2.imread(out_path, cv2.IMREAD_UNCHANGED)
        if bgr is None:
            raise RuntimeError(
                f"failed to read darktable-cli output for {raw_path}")
    rgb = bgr[:, :, ::-1].astype(np.float64)
    return np.clip(rgb, 0.0, None)
```

`decode_raw()`/`decode_raw_native()`는 전혀 수정하지 않는다 - 새 함수를
같은 파일에 추가만 한다. `import subprocess`, `import tempfile`이
`hybrid_engine/utils/io.py` 상단에 새로 필요하다(`os`, `cv2`, `numpy`는
이미 있음).

### 2. `tools/evaluate_darktable_vs_rawpy.py` (신규)

- 핫셀블라드 13쌍(`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`의
  `jpeg_url` 컬럼 basename으로 `raw_calib_cache/{name}.jpg.3FR`/`.fff`
  (raw)와 `raw_calib_cache/{name}.jpg.target.jpg`(target) 위치 - 기존
  `tools/evaluate_hncs_structural.py`의 `_pair_names()`/`_raw_path_for()`/
  `_target_path_for()`와 정확히 같은 규칙, 이 스크립트 안에 독립적으로
  재구현한다) + Fuji 3쌍(`fuji_pairs_manifest.csv`,
  `tools/evaluate_fuji_demosaic.py`의 `load_pairs()`와 같은 파싱 규칙)
  총 16쌍을 합쳐서 순회한다.
- 대표 파일(핫셀블라드 1개, Fuji 1개)로 반복-디코드 노이즈 바닥을
  먼저 측정하고 출력한다.
- 각 쌍에 대해 `decode_raw()`(rawpy)와 `decode_raw_darktable()`
  (darktable)로 각각 디코드하고, 같은 카메라 JPEG 타깃 대비
  ΔE(CIEDE2000)를 잰다(`hybrid_engine.utils.evaluate.mean_delta_e`/
  `load_image_linear_for_evaluate` 재사용).
- `OMP_NUM_THREADS=1`을 스크립트 시작 시 `os.environ`에 설정한다(rawpy
  쪽 알려진 X-Trans 논디터미니즘 제거).
- 결과를 카메라별/전체 평균으로 출력하고, 반복-디코드 노이즈 바닥과
  비교해서 "노이즈보다 큰 차이인지"를 명시한다.

### 3. 결과 기록

`hybrid_engine/EVALUATION.md`에 새 섹션 - 이기든 지든 애매하든 정직하게
기록하는 이 프로젝트 관례대로. 노이즈 바닥 수치를 반드시 같이 적어서
"이 차이가 노이즈보다 큰가"를 독자가 판단할 수 있게 한다.

### 4. 건드리지 않는 것 / 새 의존성 고지

- `decode_raw()`, `decode_raw_native()` - 수정하지 않음.
- `apply_hncs()`(`brands/hasselblad.py`), `brands/fuji.py`의 실제
  프리셋 함수들 - 이 실험과 무관.
- `hasselblad.json`, DCP 프로파일 등 기존 캘리브레이션 산출물 - 전부
  rawpy 출력에 맞춰 피팅돼 있으므로 이 실험으로 재피팅하지 않는다
  (재피팅은 이 결과가 유의미할 경우 별도 후속 논의).
- **새 시스템 의존성 고지**: `darktable-cli`는 `requirements.txt`
  (Python 패키지)로 못 잡는 시스템 패키지(`apt-get install darktable`)
  다 - README에 "이 실험을 재현하려면 darktable이 시스템에 설치돼
  있어야 한다"는 걸 명시해야 한다(Task 4 스코프).

## 테스트 계획

- `decode_raw_darktable()`은 darktable-cli+실제 RAW 파일 의존적이라
  이 프로젝트의 기존 관례대로(`decode_raw()`처럼) 커밋되는 자동화
  단위테스트 없이 수동 실행으로 검증하고 보고서에 결과를 남긴다.
- `tools/evaluate_darktable_vs_rawpy.py`의 CSV/manifest 파싱 같은
  순수 로직만 단위 테스트(`tools/evaluate_hncs_structural.py`/
  `tools/evaluate_fuji_demosaic.py`와 동일 패턴 - 실제 raw+jpeg 페어
  경로 리스트는 임시 파일로 테스트, 진짜 `raw_calib_cache/`/
  `fuji_pairs_manifest.csv`는 안 건드림).

## 다음 단계(이 스펙 밖)

- 이 실험에서 darktable이 유의미하게(노이즈보다 크게) 낫다고 나오면:
  실제로 캘리브레이션 파이프라인을 darktable 기반으로 옮길지는 완전히
  별도의, 훨씬 큰 논의(기존 hasselblad.json/DCP 전부 재피팅 필요).
- 애매하거나 rawpy가 나으면: 이 실험은 여기서 종결.
