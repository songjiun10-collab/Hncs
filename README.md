# HNCS

핫셀블라드(Hasselblad) 공식 샘플 이미지를 실측 분석해서 HNCS(Hasselblad
Natural Colour Solution)의 톤/색 특성을 코드로 근사하는 프로젝트.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `hasselblad_hncs.py` | X 시스템(X1D~X2D II) 통합 HNCS 근사 - film curve + 지각보상 대비, hue/채도 무조작 |
| `hasselblad_day.py` | 낮 장면 그레이딩 프리셋 |
| `hasselblad_night.py` | 밤 장면 그레이딩 프리셋 (DR 중앙 압축) |
| `film_sim_presets.py` | 후지필름 스타일 필름 시뮬레이션 프리셋 8종 (Astia, PRO Neg, Eterna, Acros 등) |
| `hasselblad_sample_images.csv` | 공식 샘플 이미지 메타데이터 (카메라/렌즈/작가/jpeg_url/raw_url) |
| `analyze_all_samples.py` | CSV의 jpeg_url 전체를 받아 블랙포인트/화이트포인트/채도 통계 추출 |
| `portrait_skin_analysis.py` | 얼굴 검출(YuNet)로 인물 서브셋 추출 + `apply_hncs` 적용 전/후 피부톤 hue 불변성 검증 |
| `calibrate_from_raw.py` | raw_url이 있는 행을 rawpy로 중립 렌더링해서 진짜 전/후(raw→공식JPEG) 페어 기반 그리드서치 |
| `learn_tone_curve.py` | 같은 raw+jpeg 페어에서 neutral_L→target_L 매핑을 픽셀 단위로 직접 학습해 256단계 LUT 생성 (파라메트릭 커브 가정 없음) |
| `hasselblad_hncs_learned.py` | `learn_tone_curve.py`로 학습한 LUT을 내장한 데이터 기반 대안 - `apply_hncs_learned()` |
| `regularized_lut_loocv.py` | 학습 LUT을 파라메트릭 커브 쪽으로 정규화해보고 10장 leave-one-out 교차검증으로 실제 도움이 되는지 검증 (결론: 정규화 안 하는 게 나음) |
| `face_detection_yunet.onnx` | `portrait_skin_analysis.py`가 쓰는 얼굴 검출 모델 (OpenCV Zoo, YuNet 2023mar) |

## 설치

```
pip install -r requirements.txt
```

`.claude/settings.json`은 이 리포에서 Claude Code로 분석 스크립트를 돌릴 때
`cdn.hasselblad.com`, `live.staticflickr.com` 등으로의 네트워크 접근을
자동 허용하는 샌드박스 설정입니다.

## 사용법

```python
import cv2
from hasselblad_hncs import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

`hasselblad_day` / `hasselblad_night`, `film_sim_presets`의 각 `apply_*`
함수도 동일하게 BGR `np.ndarray`를 받아 BGR `np.ndarray`를 반환합니다.

### 실측 재현/재검증

```
python3 analyze_all_samples.py       # 전체 샘플 통계
python3 portrait_skin_analysis.py    # 인물 서브셋 + 피부톤 hue 검증
python3 calibrate_from_raw.py        # raw 기반 진짜 전/후 그리드서치 (rawpy 필요, 대용량 다운로드)
python3 learn_tone_curve.py          # raw+jpeg 픽셀 대응으로 톤커브 직접 학습 (rawpy 필요)
```

## 현재까지의 실측 결론 (v12 기준, `hasselblad_hncs.py` docstring 참고)

- 공식 샘플 124장 통합 풀 기준 블랙p2=11.3, 화이트p99.5=223.9, 인물
  서브셋(43장)은 10.2/226.3 — v8(19~20장) 대비 큰 변동 없음
- 인물 43장 자동 검증에서 `apply_hncs` 적용 전/후 피부톤 hue는 사실상
  불변 (평균 |delta|=0.21, 최대 2.0 / hue 스케일 0~179)
- raw→JPEG 진짜 전/후 페어(10장)로 그리드서치한 결과, 커브에 전역
  노출/감마 보정 단계(`exposure_gamma`)가 없어서 그레이딩 전/후 밝기
  격차를 못 메꾸는 문제를 확인 (v10) → `exposure_gamma` 파라미터 추가,
  극단적 하이키 샘플(오큘러스 실내, 그림자 없음)을 블랙포인트 피팅에서
  제외하고 재탐색 (v11)
- 최종 채택(`apply_hncs`, v11): `white_point=1.0`, `exposure_gamma=0.7`
  반영, `toe_lift`/`shoulder_start`는 원안(0.001/0.78) 유지 —
  RMSE 36.3→23.3 개선. 숄더 시작점을 0.5까지 낮추면 RMSE가 16.5까지
  더 떨어지지만 그림자유효 표본이 8장뿐이라 커브 모양 자체를 바꾸는 건
  과적합으로 보고 보류
- raw 렌더링 베이스라인을 파이프라인상 더 정확해 보이는 linear
  감마(1,1)로 바꿔봤지만 RMSE가 오히려 악화(23.3→28.2) — rawpy 자체
  디모자이크/컬러매트릭스가 핫셀블라드 실제 파이프라인과 다른 알고리즘
  이라 "센서에 더 가깝게" 만드는 게 도움이 안 됨 (음성 결과, 되돌림)
- `apply_hncs_learned` (v12, `hasselblad_hncs_learned.py`): toe/shoulder
  모양을 가정하지 않고 raw+jpeg 페어에서 neutral_L→target_L 매핑을
  픽셀 단위(1,078만 쌍)로 직접 학습 — RMSE 15.4로 파라메트릭(23.3)보다
  더 나음. 다만 raw+jpeg 페어가 10장뿐이라 표본 수 제약은 동일하게 있고,
  8비트 변환 왕복 과정에서 나오는 hue 오차가 `apply_hncs`보다 약간 큼
  (평균 |delta|~3.0/179, 여전히 육안상 무시할 수준)
- 학습 LUT을 표본 부족 우려로 파라메트릭 커브 쪽에 정규화해봤지만, 10장
  leave-one-out 교차검증 결과 정규화 없는 순수 경험적 LUT이 가장 좋음
  (LOO RMSE 14.6, 정규화를 강하게 걸수록 20.7→28.0으로 악화) — bin당
  픽셀 표본이 충분히 많아 분산 문제보다 파라메트릭 커브 자체의 모양
  편향이 더 크기 때문. `apply_hncs_learned`는 정규화 없이 그대로 유지
