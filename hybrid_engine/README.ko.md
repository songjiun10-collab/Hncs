# hybrid_engine/ - EXIF 기반 카메라 간 색상 변환 (V0.1)

*[English README](README.md)*

`brands/*.py`, `tools/raw_pipeline.py`와도 또 다른 목적을 가진 세
번째 독립 모듈이다: "카메라 A로 찍어 완성된 JPEG을 마치 카메라 B가
찍은 것처럼 다시 렌더링한다." 진입점은 두 개다 - RAW 입력용
(`HybridCameraEngine`: Phase 0 색상 통일 + Gray World 정규화 + LAB
톤/채도 커브)과 JPEG 전용 입력용(`preset_inverse`: EXIF로 원본
브랜드를 판별하고, `brands/*.py`의 해당 브랜드 population-fit 톤커브를
역변환한 뒤, 실제 타깃 브랜드의 기존 `apply_*` 함수를 재적용).

`hybrid_engine/` 안이 아니라 저장소 루트에서 실행해야 `core`/
`brands`/`hybrid_engine` import 경로가 제대로 풀린다.

```
# JPEG만 - EXIF로 원본 카메라를 자동 판별
python3 -m hybrid_engine.convert photo.jpg out.jpg --target hasselblad

# RAW 있음 - 전체 파이프라인(매트릭스 + WB 통일 + Gray World +
# 톤/색 커브), EXIF로 카메라를 자동 판별해 맞는 프로필을 고름 -
# 그걸 덮어쓸 때만 --profile 필요
python3 -m hybrid_engine.main photo.3FR out.jpg
python3 -m hybrid_engine.main photo.3FR out.tiff --profile hasselblad  # 추가 편집용 16비트
```

![hybrid_engine 데모 - 후지 RAW를 핫셀블라드 프로필로 렌더링](../docs/images/hybrid_engine_demo.jpg)

*후지 GFX50S II RAW(`DSCF9556.RAF`, 이 페이지 다른 데모와 같은
`999_FUJI` raw+jpeg 라이브러리 출처)를 두 가지로 렌더링: 카메라
자체 JPEG(왼쪽) vs `hybrid_engine.main --profile hasselblad`(오른쪽) -
`hybrid_engine.convert`가 아니라 RAW 파이프라인(색매트릭스 + Gray
World + LAB 톤/색 커브)을 썼다 - 후지의 필름 시뮬레이션 프리셋은
`preset_inverse`가 필요로 하는 closed-form 역변환 가능 톤커브가 없기
때문이다(`core/preset_inverse.py` - `BRAND_FUNCS`의 population-fit
브랜드만 역변환 가능).*

![hybrid_engine 데모, 사진 4장 추가 - 도서관/건축물/궁궐/거리](../docs/images/hybrid_engine_demo_more.jpg)

*`999_FUJI` RAW+JPEG 페어 4개(코엑스 별마당 도서관, 서울시청 앞
조형물, 경복궁 정문, 명동 거리)를 위와 같은 `hybrid_engine.main
--profile hasselblad` RAW 파이프라인으로 처리한 결과. 도서관/궁궐/거리
사진에 멀리 보이는 사람은 얼굴을 알아볼 수 있는 클로즈업이 아니다.*

**알려진 한계**(각 모듈 독스트링에도 문서화):
- `core/color_matrix.py`: 카메라별 색매트릭스 정규화를 해도 센서
  분광감도가 CIE 표준관측자에 정확히 비례하지 않는다(메타머리즘) -
  물리적으로 완벽한 카메라 독립 색공간은 불가능하다, ΔE 루프로
  잔차를 줄일 수 있을 뿐 없앨 수는 없다
- `core/preset_inverse.py`: population-fit 브랜드의 L채널 톤커브만
  역변환 가능(closed-form 역함수가 있음) - CLAHE(지각적 대비 보정)는
  적응형 연산이라 역변환되지 않고, raw+jpeg 페어가 없는 브랜드(예:
  후지)는 애초에 이런 종류의 커브 자체가 없어 설계상 범위 밖이다
- `calibrate_profile.py`는 핫셀블라드 실제 raw+jpeg 페어 13개로
  CIEDE2000 ΔE 루프를 돌린다. 아래 실험 전부 in-sample이 아니라
  교차검증 ΔE로 판정한다 - 여러 실험이 in-sample에서는 좋아 보였다가
  제대로 검증하고 나면 실패하거나(부호가 뒤집히거나) 했는데, 이 자체가
  표를 읽을 때 염두에 둘 반복적인 발견이다. `recalibrate.py`는 v1.2를
  배포할 때 쓴 실제 "매트릭스 + 재학습, nested CV, 교차검증 ΔE가 진짜
  개선될 때만 갱신" 절차를 명령 하나로 감싼다(`python3 -m
  hybrid_engine.recalibrate --write`, 기본은 dry-run, `--cache-dir`로
  다른 raw+jpeg 페어 디렉토리 지정) - 더 큰 데이터셋(예: 이슈 #4의
  실제 장면 X2D 페어)이 들어오면 유용:

  | 실험 | 방법 | In-sample | 교차검증 | 판정 |
  |---|---|---|---|---|
  | v1.1 baseline | `tone_core`/`color_core` 파라미터 좌표하강 | ΔE00 15.01 | - | 출발점 |
  | 톤 학습 LUT | 1D LUT, L채널 256 bin | +4.9% | 실행 안 함(CV는 이후 추가) | 기각, 기준 미달 |
  | Hue 학습 LUT(v1.1) | 1D 원형 LUT, 36 bin | +2.1% | 실행 안 함 | 기각, 기준 미달 |
  | 3D 잔차 LUT | L/a/b 결합 그리드, 729셀 | +11.1% | **-5.7%** | 기각 - 순수 과적합으로 검증됨 |
  | 2D 잔차 LUT | a/b 결합 그리드, 81셀 | +1.4% | -2.7% | 기각 - 교차검증에서 손해로 확인됨 |
  | 공간/로컬 대비(v1.1) | unsharp-mask L채널 clarity | +0.0% | +2.0%(노이즈) | 기각 - 무신호로 확인됨(null result) |
  | **Raw-baseline 3x3 매트릭스(단독)** | 색차트 없이 전역 최소자승 색매트릭스(GitHub 이슈 #4) | +42.4% | **+32.6%** | 첫 실질적 개선으로 검증됨 |
  | 파이프라인에 매트릭스 연결(1차 시도) | 매트릭스 + 기존 Phase 0/1/2 | - | +0.0% | 버그로 확인됨: 강제 노출정규화가 매트릭스 이득을 지워버림 |
  | 매트릭스 + 재학습된 톤/색(수정) | `--mode raw_baseline_pipeline`, nested CV | +34.8% | **+29.7%** | **v1.2로 배포 - 교차검증으로 확인됨** |
  | Hue LUT를 v1.2에서 재시도 | 같은 1D 원형 LUT, 새 baseline | +4.6% | +1.4% | 기각, 기준 미달로 확인됨 |
  | 공간 보정을 v1.2에서 재시도 | 같은 로컬대비 단계, 새 baseline | +0.3% | -1.6% | 기각으로 확인됨 |
  | Robust(백분위) Gray World | neutral-cast 추정에서 고채도 픽셀 제외 | +0.0%(최선 후보=끔) | -3.4% | 기각 - 야간 장면 하늘 과보정을 노렸으나 도움 안 되는 걸로 확인됨 |
  | Hue-조건부 chroma LUT | 36-bin 원형 chroma 게인, hue-rotation LUT와 직교 | **-2.0%** | -4.0% | 기각 - in-sample에서도 마이너스인 것으로 검증된 첫 LUT 실험 |
  | Gray World 완전 제거 | 카메라 as-shot WB만 사용(`unify_to_d65`), 픽셀 기반 neutral-cast 추정 없음 | - | **-90.3%**(ΔE00 9.69 → 18.43) | 강하게 기각 - Gray World가 13쌍 전부에 걸쳐 필수임이 확인됨(노이즈 아님) |
  | Zoned Gray World(2-5 luma 존) | 밝기 존별 독립 neutral-cast 추정, 가우시안 블렌딩 | +0.0%(최선=1존) | +0.0%, 1존 이후 단조 악화, 13개 LOO 폴드 전부 baseline 선택 | 기각 - 자유도를 늘려도 이 표본 크기에서는 노이즈만 느는 걸로 확인됨 |
  | Gray World 강도(파인튜닝) | identity ↔ full correction 보간 블렌드 강도 1개, 0.6-1.4 세밀 그리드 | +0.7%(최선=0.95) | **-0.0%**(사실상 무변화) | 기각 - 가장 보수적인 조정(자유파라미터 1개)조차 실제 신호 없는 걸로 확인됨 |
  | X2D II 차트 페어를 캘리브레이션에 pooling | X1D 13쌍 + 큐레이션된 X2D II ColorChecker 2쌍(9프레임 버스트를 2개로 중복제거, 9개 전부는 게인이 희석됨) | -2.5% | **+3.7%**(진짜 LOO, held-out X1D 페어는 학습에 안 들어감) | 손해가 아니라 도움이 된 첫 pooling 시도로 확인됨 |
  | Gray Edge 색편향 보정 알고리즘 | Gray World를 공간-미분 기반 neutral-cast 추정(van de Weijer 2007)으로 교체, 매트릭스/톤/색은 그대로 | - | **+2.1%** | 채택됨(White Patch는 -18.5%, Shades of Gray는 약한 +1.9%로 검증됨) |
  | **Gray Edge + 차트 pooling, 함께 재학습** | `color_cast_algorithm=gray_edge`와 페어 15개로 매트릭스+톤/색을 처음부터 재피팅 | +9.9% | **+11.1%** | **v1.3으로 배포 - v1.2 이후 처음으로 5% 기준을 넘은 것으로 확인됨** |

  배포된 v1.3 프로필은 페어 15개(X1D 13 + 큐레이션된 X2D II
  ColorChecker 2)로 매트릭스와 톤/색 커브를 Phase 0의 색편향 보정에
  Gray World 대신 Gray Edge를 써서 다시 피팅한 것이다 -
  `EVALUATION.md` 후속실험 17/18에 전체 비교표와 왜 이 조합이
  단독보다 나은지에 대한 근거가 있다. 비선형 RBF 색매칭
  프로토타입(`scipy.interpolate.RBFInterpolator`,
  [ethan-ou/camera-match](https://github.com/ethan-ou/camera-match)에서
  영감)과 픽셀 단위 gradient-boosting 회귀도 매트릭스 전체 대체용으로
  시도했으나 - 둘 다 같은 실패 패턴(이미 어려운 장면에서는 크게
  개선되지만 이미 쉬운 장면에서는 순손실)을 보여 기준을 넘지 못했고,
  둘 다 배포 파이프라인에 없다.

  배포된 v1.2 프로필(위 v1.3으로 대체됨)은 공식 평가 하네스에서
  ΔE00 15.01 → **9.82**를 검증했다(-34.6%, CIE 2000 등급으로
  "완전히 다른 색"에서 "언뜻 봐도 다름"으로 상승). 전체 방법론, 실패
  -> 원인진단 -> 수정 스토리, 남은 한계(중간톤 잔차, hue는 거의 안
  움직임)는 `EVALUATION.md`에 있고, 기각된 LUT 실험들은
  `assets/luts/README.md`에 별도로 자세히 정리돼있다. 픽셀 단위
  진단(`EVALUATION.md` 후속실험 10)은 남은 가장 큰 실패 모드를 구체적
  메커니즘까지 짚었다: Gray World의 전역 스케일 팩터 하나로는 야간
  장면의 하늘과 가로등이 지배하는 전경을 동시에 만족시킬 수 없다 -
  "자유도를 늘리는" 쪽부터 "줄이는" 쪽까지 네 가지 다른 수정을(위
  표) 전부 시도해 교차검증에서 기각했으므로, 배포 우회책 대신 문서화된
  미해결 한계로 남겨둔다.

## 더 읽을거리

- `EVALUATION.md` - 이 모듈의 전체 측정 기록(위 표뿐 아니라 번호가
  매겨진 모든 후속 실험)
- `assets/luts/README.md` - 기각된 LUT 실험들의 상세 기록
- `CLAUDE.md`(이 디렉토리) - 이곳 수정 규칙
