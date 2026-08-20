# 기여 데이터셋 수용 규격 (Contributed dataset intake) - Leica

스키마/디렉토리 구조/검증 절차는 `datasets/hasselblad/contributed/README.md`와
완전히 동일하다(브랜드 무관 공통 규격, 2026-08부터 `tools/build_local_manifest.py`
/`tools/verify_contributed_pairs.py`가 `--make` 인자로 제조사를 받도록
일반화됨). 이 파일은 Leica에 특화된 부분만 적는다.

## 왜 지금 이게 중요한가

`brands/leica.py`(`apply_leica_look`)는 현재 **raw+jpeg 페어가 하나도
없다** - imaging-resource.com에서 모은 이미 그레이딩된 SOOC JPEG 45장
(M9/X Vario/SL2)의 population 통계만으로 만든 1차 버전이다. 핫셀블라드
v8/v9 단계(진짜 raw 기준 전/후 피팅인 v10~v12 이전)에 해당한다.
`brands/leica.py` docstring이 명시한 미검증 항목:

- `toe_lift`/`white_point`만 population 타깃에서 직접 대입, 나머지
  (`shoulder_start`/`clahe_clip`)는 핫셀블라드 기본값을 그대로 가져다
  쓴 미검증 추정
- hue/채도 무조작 가정 자체가 미검증(before가 없어서 판단 불가)
- M9(2009, CCD)와 SL2(2019, CMOS) 10년 차이를 커브 하나로 뭉뚱그리는
  게 타당한지 미검증

## 뭘 찍어야 가장 값어치가 큰가

핫셀블라드에서 실제로 있었던 두 갈래 기여가 각각 다른 문제를 풀었다 -
Leica도 같은 순서를 따르는 게 효율적이다.

1. **ColorChecker Classic 24패치 차트** (raw+jpeg 페어, 여러 장 - 조명
   하나로 버스트 촬영해도 됨). `kmichels-x2dii-2026-07/`이 이 방식으로
   raw 베이스라인 색채측정 오차를 ΔE00 7.58→2.78(또는 X2D II 단독
   재현 시 29.31→2.83)까지 줄였다 - 카메라 네이티브 매트릭스가 얼마나
   틀리는지, 차트로 직접 피팅하면 얼마나 나아지는지 정량화할 수 있다.
   `tools/analyze_colorchecker_matrix.py`/`hybrid_engine/core/chart_baseline.py`가
   그대로 재사용 가능(브랜드 무관 - `cv2.mcc` 자동검출 + colour-science
   내장 참조값).
2. **실사진 raw+jpeg 페어** (daylight/overcast/tungsten/lowlight 등
   다양한 장면, 가진 바디 전부 - M9/X Vario/SL2 외 다른 Leica 바디도
   전부 환영). `local-mixed-2026-07/`이 이 방식으로 핫셀블라드의
   "세대 간 pooling 전제"를 처음 raw 기준으로 검증했다(기각됨 -
   `docs/measurements.md` 참고) - Leica도 `apply_leica_look`의
   toe_lift/white_point를 실제 raw 기준으로 재피팅하고, 위에 나열한
   미검증 가정들을 하나씩 확인하는 데 쓴다.

둘 다 있으면 가장 좋지만, 굳이 하나만 고른다면 **1번(차트)** - 데이터
자체는 적어도 되고(버스트 몇 장), 재현성 있는 정량적 결과(ΔE00 개선폭)
를 가장 빨리 준다.

## 로컬 라이브러리에서 manifest 만들기

```
python3 -m tools.build_local_manifest ~/Pictures/leica_shoot datasets/leica/contributed/<세트 이름> --make Leica
```

`--make Leica`를 빠뜨리면 기본값(Hasselblad)으로 검증돼서 전부 FAIL
처리된다. `.DNG` 확장자는 이미 `tools/build_local_manifest.py`의
`RAW_EXT`에 포함돼 있음(2026-08 추가).

## 검증만 다시 돌리기

```
python3 -m tools.verify_contributed_pairs datasets/leica/contributed/<세트 이름> --make Leica
```

## 현재 수용된 세트

(아직 없음 - 최초 기여 대기 중)
