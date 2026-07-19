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

1번(세대 간 pooling 판정)은 이 데이터가 다양한 실사진이 아니라
ColorChecker 차트 반복 촬영이라 아직 미실행 - 실사진 X2D II raw+jpeg
페어가 따로 확보되면 그때 실행.
