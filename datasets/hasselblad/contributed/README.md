# 기여 데이터셋 수용 규격 (Contributed dataset intake)

GitHub 이슈 #4에서 제안된 X2D II raw+jpeg 페어 같은 외부 기여 데이터를
받는 자리. 이 프로젝트의 나머지 데이터와 같은 수준의 출처 엄밀성을
유지하기 위해, 기여 데이터는 **manifest + 자동 검증**을 통과해야
분석에 편입된다.

## 디렉토리 구조

```
datasets/hasselblad/contributed/
  <기여자별-세트-이름>/          예: kmichels-x2dii-2026-07/
    manifest.csv                 아래 스키마
    raw/                         .3FR/.fff
    jpeg/                        인카메라 JPEG (RAW와 동시 촬영)
    phocus_tiff/                 (선택) Phocus 16bit TIFF 익스포트
    chart/                       (선택) ColorChecker 프레임
```

이미지 파일 자체는 용량 때문에 커밋하지 않는다(외부 호스팅 링크를
manifest에 기록) - manifest.csv와 검증 결과만 커밋.

## manifest.csv 스키마

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `filename_raw` | O | raw/ 안의 파일명 |
| `filename_jpeg` | O | jpeg/ 안의 파일명 (같은 셔터의 인카메라 JPEG) |
| `camera` | O | 예: `X2D II 100C` |
| `lens` | O | 예: `XCD 2,5/55V` |
| `iso` | O | 촬영 ISO |
| `wb_setting` | O | `auto` 또는 켈빈값(예: `5600K`) |
| `scene_type` | O | `daylight`/`overcast`/`tungsten`/`mixed`/`lowlight`/`chart` |
| `filename_phocus_tiff` | X | phocus_tiff/ 안의 대응 파일명 |
| `phocus_settings` | X | `default` 또는 사용한 프리셋 이름 |
| `illuminant` | X | chart 프레임일 때 측정 광원(예: `D50 measured`) |
| `download_url` | O | 원본 파일 호스팅 위치 |
| `notes` | X | 자유 기록 |

## 자동 검증 (`python3 -m tools.verify_contributed_pairs <세트 디렉토리>`)

1. manifest의 모든 필수 컬럼 존재 + 파일 실재 여부
2. **EXIF 대조**: raw/jpeg 각각의 EXIF Make/Model이 manifest `camera`와
   일치하는지 (기존 `hasselblad_raw_jpeg_pairs.csv`의
   `exif_pair_verified` 패턴)
3. **페어 동기 검증**: raw와 jpeg의 `DateTimeOriginal`이 2초 이내인지
   (동시 촬영 확인)
4. **편집 오염 검사**: jpeg의 EXIF Software에 Photoshop/Lightroom류
   흔적이 없는지 (`tools.analyze._check_genuine_bytes`와 동일 기준)

검증 통과분만 `hasselblad_raw_jpeg_pairs.csv`에 편입한다.

## 데이터 도착 시 실행할 분석 (미리 명세)

1. **세대 간 pooling 타당성 최종 판정**: X2D II 페어에 기존 X1D 학습
   커브(`apply_hncs`/`apply_hncs_learned`)를 적용해서 RMSE가 X1D
   페어에서와 동급인지 비교 - 동급이면 "X 시스템 공통 색과학" 전제가
   raw 기준으로 처음 검증되는 것, 크게 다르면 세대별 분리 캘리브레이션
   필요 (이슈 #4 3번 지적의 해소)
2. **camera-to-XYZ 최소자승 매트릭스**: ColorChecker 프레임 + 측정
   광원으로 libraw 기본 매트릭스 대비 특성화된 매트릭스를 구해서 raw
   베이스라인 불확실성을 정량화 (이슈 #4 4번 지적의 해소) - **완료**,
   `kmichels-x2dii-2026-07/`(ColorChecker Classic 차트 10장)로 실행함.
   `hybrid_engine/core/chart_baseline.py` +
   `tools/analyze_colorchecker_matrix.py`, 결과는
   `hybrid_engine/EVALUATION.md` 후속 실측 9 참고 - 요약: 보정 없는
   raw 베이스라인 ΔE00 7.58, 차트 매트릭스로 교차검증 기준 2.78(-63.3%).

1번(세대 간 pooling 판정, `apply_hncs` 커브를 X2D II에 그대로 적용했을
때 RMSE 동급 여부)은 `kmichels-x2dii-2026-07/`이 다양한 실사진이 아니라
ColorChecker 차트 반복 촬영이라 그 데이터로는 미실행이었다 - **이후
`local-mixed-2026-07/`(아래)로 확보한 실사진 X2D/907X·CFV raw+jpeg
페어로 실행 완료**. 결과는 세대 간 pooling 전제 기각(파라메트릭이
학습 LUT보다 나음, 특히 CFV 100C/907X에서 거의 2배) -
`docs/measurements.md` "로컬 기여 데이터셋으로 세대 간 pooling 첫 실측"
참고.

## 현재 수용된 세트

- **`kmichels-x2dii-2026-07/`** (이슈 #4 기여): ColorChecker Classic
  차트 10장, X2D II. camera-to-XYZ 매트릭스 특성화용 (위 2번 항목)
- **`local-mixed-2026-07/`** (프로젝트 소유자 개인 라이브러리): 실사진
  raw+jpeg 61쌍 (CFV 100C/907X 30, X2D 100C 24, X1D II 50C 6, X1D 1).
  `tools/build_local_manifest.py`로 EXIF 시각 매칭 + 자동 검증까지
  한 번에 생성 - 후보 104쌍 중 43쌍(41%)이 Lightroom/Photoshop 편집
  흔적으로 탈락. 위 1번 항목(세대 간 pooling 판정)에 사용됨.
- **`owner-x2dii-2026-08/`** (프로젝트 소유자, Google Drive 폴더로 공유):
  X2D II 100C raw 9장(2025-08-28~09-02, 여러 날에 걸친 실촬영, 렌즈
  XCD 55V) - **jpeg가 별도로 없어서 RAW 내장 프리뷰(rawpy
  `extract_thumb()`)를 jpeg 대신 씀**. 원본 11904x8842 대비 프리뷰는
  2918x3888로 훨씬 작고, 프리뷰 자체의 EXIF Software가 `dcraw v9.26`이라
  카메라 순정 임베디드 프리뷰인지 확실치 않음(각 행 manifest notes에
  명시) - 다른 세트의 "진짜 동시촬영 풀해상도 카메라 JPEG"보다 약한
  근거이니 분석에 쓸 때 이 점을 감안할 것. `verify_contributed_pairs`는
  9/9 PASS(단, DateTimeOriginal은 프리뷰에 없어서 raw 값을 그대로
  복사해 넣은 것 - 페어 자체가 raw에서 뽑은 프리뷰라 실제 촬영시각과
  다르지 않음).

별개로, **hybrid_engine 자체 캘리브레이션 데이터셋에 챠트 페어를
직접 pooling하는 실험은 실행했고 실제로 배포까지 됐다** - 챠트 10장
중 버스트 중복을 피해 대표 2장만 골라 X1D 13쌍에 합쳐서(15쌍) 매트릭스
+톤/채도를 재학습, Gray World를 Gray Edge로 바꾸는 것과 결합해서
13-fold 교차검증 +11.1% 개선을 얻어 `hasselblad.json` v1.3으로
배포됐다(`hybrid_engine/EVALUATION.md` 후속 실측 16/17/18). 나머지
챠트 7장은 같은 버스트(94초 내 10샷)라 정보량이 거의 없다고 판단해
제외했다.
