# HNCS GUI 개발 (설계)

## 배경

이 프로젝트는 지금까지 "이미지 → 이미지" 라이브러리 + CLI 모음이었다
(`MEMORY.md`: "이 리포는 서버도 GUI도 아니라..."). 유일한 시각적 검증
수단은 `.claude/skills/run-hncs/driver.py`의 `sheet`/`look` 서브커맨드
(24개 룩을 한 장에 타일링한 PNG)뿐이다. 루트 `CLAUDE.md`는 "Deprioritized:
UI/frontend"라고 명시하지만 이번은 명시적 요청("야 gui 개발 ㄱㄱ")이라
그 우선순위 밖에서 진행한다.

`AskUserQuestion`으로 스코프 2가지를 먼저 확정했다:

- **범위**: 개별 기능 하나가 아니라 기존 CLI 4종을 탭으로 묶은 통합 앱.
- **기술스택**: 데스크톱 앱(서버 없이 로컬 실행).

## 조사한 것 (실측)

- `brands/*.py`에 브랜드별 레지스트리 딕셔너리가 따로 없다 - 대신
  `.claude/skills/run-hncs/driver.py`의 `shipped_looks()`가 `ast.parse`로
  각 파일을 스캔해서 `apply_*` 함수명을 동적으로 찾는다(비디오 프레임
  변형 `*_video_frame`은 제외). 이 GUI의 브랜드 목록도 이 함수를 그대로
  재사용한다 - 별도 레지스트리를 새로 만들지 않는다.
- 나머지 3개 도구는 전부 파일 경로 in/out CLI로 이미 완성돼 있고, 내부
  로직을 재사용 가능한 형태로 따로 분리해두지 않았다(`main()` 안에 로직이
  같이 있음):
  - `hybrid_engine.convert` - JPEG 전용, `--source`(생략시 EXIF 자동인식)
    + `--target`(필수, 브랜드/프리셋 이름).
  - `hybrid_engine.main` - RAW 전용, `--profile`(생략시 EXIF 자동인식,
    `assets/profiles/*.json` 근거 없으면 에러) + `--jpeg-quality` +
    `--max-megapixels`(기본 50.0, 고해상도 RAW OOM 방지용 다운샘플) +
    `--evaluate`.
  - `tools.raw_pipeline` - RAW 전용, `--log-space`(필수, `core.log_pipeline
    .LOG_SPACES`의 12개 키 중 하나) + `--lut`(선택, `.cube`) +
    `--exposure`/`--auto-expose-mode`(`average`/`highlight_safe`/`matrix`) +
    `--exr-compression`. 출력 확장자로 `.tif`(16비트)/`.exr`(32비트)
    분기.
  - `tools.lens_correction` - RAW/일반 이미지 둘 다, `--make`/`--model`/
    `--lens`/`--focal-length`/`--aperture`(전부 생략시 EXIF/exiftool에서
    읽음) + `--distance`(기본 1000.0).
- `tools/CLAUDE.md`에 이미 있는 subprocess 컨벤션(명시적 `env=`, 부모
  `OMP_NUM_THREADS` 누출로 darktable-cli가 75% 검게 렌더링된 사고 - exit
  code만으로 성공 판단 금지, 출력 그럴듯한지 확인)을 그대로 따른다.
- `requirements.txt` 현재 의존성: opencv-python, numpy, rawpy, requests,
  gdown, colour-science, lensfunpy, OpenEXR, imageio-ffmpeg. Tkinter는
  포함 안 됨(표준 라이브러리라 당연히 없음) - 신규로 필요한 건 이미지
  표시용 `Pillow`뿐(cv2 배열을 Tk 캔버스에 직접 못 그림).

## 설계

### 1. 백엔드 호출 방식 - 탭마다 다르다

- **탭 1 (브랜드 Look 미리보기)**: 순수 함수 호출이라 subprocess 오버헤드가
  불필요 - `brands.<module>.<apply_func>(img: np.ndarray) -> np.ndarray`를
  in-process로 직접 import해서 호출.
- **탭 2, 3, 4**: 이미 파일 경로 in/out으로 완성된 CLI라 로직을
  재구현/추출하지 않고 그대로 subprocess로 감싼다(`subprocess.run([sys.
  executable, "-m", "hybrid_engine.convert", ...], env=..., capture_output=
  True)`). 입력을 임시 파일로 안 만들어도 되게, 사용자가 고른 원본
  경로를 그대로 CLI 인자로 넘기고 출력은 임시 디렉토리(`tempfile.
  mkdtemp()`)에 받아서 로드 후 화면에 표시.
  - 탭 2는 입력 확장자로 `hybrid_engine.convert`(jpg/jpeg/png/tif/tiff)
    vs `hybrid_engine.main`(RAW 확장자 - `tools/lens_correction.py`의
    `_RAW_EXTS` 집합과 동일한 목록을 재사용)을 자동 분기. 사용자가 타깃
    브랜드만 고르면 되고, 소스는 EXIF 자동인식 결과를 화면에 보여주되
    수동 오버라이드 드롭다운도 제공(`--source`/`--profile`).
  - 탭 3은 Log space 드롭다운(`LOG_SPACES` 12개 키), 노출/자동노출 모드는
    이번 버전에서는 노출 슬라이더(EV, `--exposure`) + 자동노출 모드
    라디오(3개 + "없음") 정도만 노출하고 `--lut`/`--exr-compression`
    같은 세부 옵션은 스펙 밖(필요해지면 별도 요청).
  - 탭 4는 EXIF에서 읽은 make/model/lens/focal-length/aperture를 화면에
    보여주고, 없는 필드만 입력 칸을 활성화(EXIF에 다 있으면 인자 없이
    바로 실행 가능).
- 각 탭의 "실행" 로직(명령 조립, 입력 검증, 출력 파일 로드)과 "위젯
  조립"(버튼/드롭다운 배치)을 분리한 함수로 작성 - 전자만 유닛테스트
  대상.

### 2. 파일 구조

```
gui/
  __init__.py
  __main__.py             # python3 -m gui 진입점, app.py의 main() 호출
  app.py                   # 메인 윈도우 - ttk.Notebook에 탭 4개 등록
  widgets/
    __init__.py
    image_view.py          # before/after 나란히 표시하는 재사용 위젯
                           # (PIL Image -> ImageTk.PhotoImage 변환 포함)
  tabs/
    __init__.py
    brand_preview.py       # 탭 1
    hybrid_convert.py       # 탭 2
    raw_pipeline_tab.py     # 탭 3
    lens_correction_tab.py  # 탭 4
  CLAUDE.md                # 이 디렉토리 컨벤션(아래 "3. gui/CLAUDE.md" 참고)
tests/
  test_gui_brand_preview.py
  test_gui_hybrid_convert.py
  test_gui_raw_pipeline_tab.py
  test_gui_lens_correction_tab.py
```

각 `tabs/*.py`는 위젯 클래스 하나 + 그 클래스가 호출하는 순수 로직
함수(들)로 구성. 로직 함수는 Tk에 의존하지 않아 위젯 없이 직접
호출/테스트 가능해야 한다(예: `build_hybrid_convert_command(input_path,
target, source_override) -> list[str]`, `run_brand_preview(module_name,
func_name, img) -> np.ndarray`).

### 3. 공통 컴포넌트

- `widgets/image_view.py`: OpenCV BGR `np.ndarray`(또는 파일 경로) 두
  장(before/after)을 받아 `ttk.Frame` 안에 나란히 그린다. 큰 이미지는
  미리보기용으로 화면 폭에 맞춰 축소(`cv2.resize`, 원본 저장용 파일은
  건드리지 않음).
- 백그라운드 실행: RAW 디코딩/변환은 몇 초~몇 분 걸릴 수 있으므로(
  `tools/CLAUDE.md`: "RAW-decode 실험은 시간 단위") 각 탭의 "실행" 버튼은
  `threading.Thread`로 작업을 돌리고, 완료 시 `root.after()`로 메인
  스레드에 결과를 넘겨 위젯을 갱신한다(Tk는 워커 스레드에서 위젯 직접
  조작 불가). 실행 중엔 버튼 비활성화 + `ttk.Progressbar`(indeterminate
  모드 - 진행률을 모르므로).
- 에러 처리: subprocess 탭은 `returncode != 0`이면 stderr를 그대로
  라벨/텍스트박스에 표시(CLI가 이미 사람이 읽을 에러 메시지를 찍는다 -
  `tools/lens_correction.py`의 "에러: ..." 패턴 등). 브랜드 탭은 예외를
  잡아 메시지 표시.

### 4. 의존성 변경

- `requirements.txt`에 `Pillow` 추가 (cv2 배열 -> Tk 캔버스 표시용).
- Tkinter 자체는 표준 라이브러리라 `requirements.txt`에 안 올라감 - 단
  일부 배포판(예: Homebrew Python)은 `python3-tk`/`python-tk`를 시스템
  패키지로 따로 설치해야 할 수 있음. 이건 `README.md`의 GUI 실행 섹션에
  안내 문구로만 남기고 코드로 처리하지 않는다(환경 문제, 스펙 대응
  범위 밖).

### 5. 테스트 전략

CI(GitHub Actions)는 헤드리스라 실제 Tk 윈도우를 인스턴스화하면 실패할
수 있다. 그래서:

- 탭 1: `run_brand_preview()` 같은 순수 함수는 작은 합성 `np.ndarray`
  (예: 8x8 랜덤 BGR)를 넣어 결과 shape/dtype만 확인 - 실제 픽셀 값의
  정확성은 이미 `tests/test_brands.py`가 검증하므로 중복하지 않는다.
- 탭 2~4: `build_*_command()` 류의 명령 조립 함수를 각 CLI의 실제
  argparse 옵션과 대조해서(위 "조사한 것" 절의 옵션 목록) 올바른 인자
  리스트를 만드는지 확인. `subprocess.run` 자체는 호출하지 않거나
  monkeypatch로 대체(무거운 RAW 디코딩을 테스트에서 실행하지 않음).
- `widgets/image_view.py`, `app.py`(탭 등록/윈도우 생성)는 Tk 인스턴스가
  필요해 유닛테스트 대상에서 제외 - 대신 로컬에서 수동 실행 확인만(이
  스펙 문서에 "수동 검증 체크리스트"로 남긴다, 아래).
- 기존 534개 테스트 스위트는 그대로 통과해야 하고, 새 GUI 테스트가 Tk를
  띄우지 않으므로 CI 환경(디스플레이 없음)에서도 안전하게 돌아간다.

### 6. `gui/CLAUDE.md` 신설

기존 6개 area(`brands/`, `tools/`, `hybrid_engine/`, `docs/`, `tests/`,
`datasets/`)와 동일한 패턴으로 짧은 area rule 파일을 추가한다. 내용:
"이 디렉토리는 기존 backend 모듈의 순수 wrapper - 로직 재구현 금지, 항상
existing CLI/함수를 호출", "로직과 위젯 분리 원칙", "Tk 인스턴스가 필요한
코드는 유닛테스트 대상 아님" 정도의 3~4줄.

### 7. 수동 검증 체크리스트 (자동테스트로 커버 안 되는 부분)

플랜 마지막 태스크에서 실행하고 기록:

- `python3 -m gui` 실행 → 창이 뜨고 탭 4개가 보이는지.
- 탭 1: `docs/images/before_after_hncs.jpg`에서 원본을 잘라(run-hncs
  driver의 `default_source()`와 동일한 방식) 아무 브랜드나 골라 적용 →
  Before/After가 다르게 보이는지.
- 탭 2~4: 실제 RAW/JPEG 파일이 있으면(`raw_calib_cache/` 등, 없으면 이
  스텝은 "데이터 없어 스킵"으로 기록) 하나씩 돌려 에러 없이 결과가
  뜨는지.

## 건드리지 않는 것

- `brands/`, `hybrid_engine/`(특히 `assets/profiles/*.json`/`*.dcp`),
  `tools/`, `core/`의 기존 함수·CLI - 순수 호출만, 로직 변경 없음.
- 루트 `CLAUDE.md`의 Never 목록(`apply_hncs()` 등) 그대로 적용.

## 다음 단계 (이 스펙 밖)

- 패키징(pyinstaller/py2app 등 단일 실행파일화)은 하지 않음 - 소스
  체크아웃에서 `python3 -m gui`로 실행하는 것까지가 이번 스코프.
- 탭 3의 `--lut`/`--exr-compression` 등 세부 옵션 노출, 탭 2의 `--evaluate`
  (ΔE 비교) 노출은 필요해지면 별도 요청으로.
