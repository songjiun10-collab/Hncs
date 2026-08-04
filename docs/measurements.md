# 핫셀블라드 실측 결론

*[English](measurements.en.md)*

[메인 README](../README.md)로 돌아가기.

v12/day-night v3 기준 (`brands/hasselblad.py` docstring 참고).

- **픽셀 단위 5종 시그니처 분석(2026-07, 공식 샘플 124장 전량 진짜 원본)**:
  `datasets/hasselblad/{tone,color,texture,gamut}_signature.json` +
  `joint_distribution.npz`로 저장. 진짜 원본(리사이즈/재인코딩 없음) 기준
  픽셀 단위로 톤/채도-hue/샤프닝-노이즈-헤일로/Lab a·b 색역을 전수 계산.
  - **전체 픽셀을 그냥 풀링해서 percentile을 구하면 안 된다는 걸 실측으로
    확인**: 124장 해상도가 30만~2억 픽셀로 최대 676배 차이나서, 픽셀
    풀링 방식은 큰 사진 몇 장에 통계가 지배당함(풀링 b2=1.0으로 급락,
    사진당 동일가중 평균은 b2=18.1 - 10배 이상 차이). population 타깃은
    "사진 단위 동일가중 평균"으로 계산해야 함 - 풀링 히스토그램 자체는
    `joint_distribution.npz`에 그대로 남겨뒀지만 타깃으로는 안 씀.
  - **캐시(downloaded_samples/, resize+재인코딩) vs 진짜 원본을 124장
    전부 1:1로 재검증**: 그림자유효(dark_pct>5%) 94장 기준 블랙p2
    11.27(캐시) vs 10.63(원본) - 차이 0.6, 5.7%. 화이트p99.5
    223.85(캐시) vs 225.56(원본) - 차이 1.7, 0.8%. 둘 다 노이즈 수준의
    차이라 **캐시가 톤 커브 보정 타깃(b2/w995)을 왜곡시키지는 않았음을
    확인** - v9/apply_hncs가 근거한 기존 타깃(11.3/223.9)은 유효함.
    (참고: 이 재검증 과정에서 파일 인덱스 매핑 실수로 "캐시 vs 원본이
    60% 차이난다"는 오판을 한 번 냈다가, 124장 전부 1:1 재대조해서
    바로잡음 - 위 최종 수치가 맞는 값)
  - **결론: `apply_hncs`/day-night 파라미터에 수정 사항 없음.** 톤
    타깃은 이미 정확했고, 채도/hue/텍스처/색역(color/texture/gamut
    시그니처)은 HNCS가 애초에 안 건드리는 채널이라 "타깃"이 아니라
    population이 실제로 어떤 값을 갖는지 기록하는 참고 자료로만 저장.
- **파이프라인 시그니처 분석(2026-07, 공식 샘플 124장 전량 진짜 원본 재다운로드)**:
  `downloaded_samples/`(자체 캐시: resize+재인코딩으로 노이즈 지표를 왜곡시킴)를
  거치지 않고 124장 전부 `curl`로 무가공 원본을 새로 받아(`/tmp/true_originals/`,
  4.5GB) 샤프닝 강도/미세대비/노이즈/에지 헤일로/JPEG 압축 특성을 측정.
  다운로드 URL 목록에 이전 5장짜리 파일럿 표본과 18장이 중복돼 있어
  제거(105장 고유). 단, 실제 population 통계·day/night v3 보정에 쓰인
  `orig_*.jpg`(124장, CSV 행과 1:1) 자체에는 내부 중복이 전혀 없음을
  재확인 — 기존 재보정 결과는 안전.
  - JPEG 품질: 77%(81/105)가 Q99·YCbCr 4:4:4(사실상 무손실), 소수
    (17장)만 Q75·4:2:0(초기 X1D 계열로 보이는 파일명). 브랜드 필터 자체는
    JPEG로 재인코딩하지 않으므로 이 값은 참고용 메타데이터.
  - 샤프닝 에너지(고주파 평균절대값, 중앙값 2.65)와 미세대비(DoG std,
    중앙값 6.37)는 서로 강하게 상관(r=0.77) — 일관된 로컬 대비 처리
    스타일이 있다는 신호. 그러나 이 값들은 "가공 안 된 원본"과의 짝
    비교가 아니라 완성 JPEG끼리의 자기참조 통계라서, 중립 렌더 대비
    얼마나 강한지 정량화할 기준선이 없음 → 커브 모듈에 별도 샤프닝
    파라미터를 새로 추가할 근거로 쓰기엔 부족하다고 판단, 반영 보류
  - 에지 헤일로(overshoot): 품질 구간별 중앙값은 사실상 평탄(7~8%,
    Q<=80/81-95/>95 전부 비슷) — 5장 파일럿에서 보였던 "저품질일수록
    헤일로 큼" 패턴은 표본을 키우니 사라짐(평균이 튀는 건 소수 극단치
    때문, 중앙값 기준으론 무관). 샤프닝 에너지와의 상관도 약함(r=0.24).
    극단치(orig_133 129.9%, orig_68 45.6% 등)는 실제 스펙큘러 하이라이트
    경계를 halo로 오검출한 것으로 보임 — 이 지표는 JPEG 링잉/진짜 halo/
    장면 자체의 밝은 반사를 못 가른다는 기존 caveat 그대로 확인됨.
    → 헤일로 기반 파라미터도 반영 보류
  - 노이즈: 파일별 편차가 극단적(0.001~6.6)이고 서브샘플링 그룹별
    평균이 서로 겹치는 범위(4:2:0 0.34 / 4:4:4 1.19 / 4:2:2 0.32,
    n=7~81)라 크로마 서브샘플링이나 JPEG 품질로 설명되지 않음 — 장면
    콘텐츠(ISO, 조도, 텍스처) 의존이라는 기존 결론 재확인. 브랜드
    전역에 적용할 고정 그레인/디노이즈 파라미터를 새로 만들 근거 없음
  - **결론**: 표본을 124장 전량으로 늘려도 샤프닝/헤일로/노이즈 중
    어느 것도 "이 값을 새 파라미터로 코드에 반영하자"고 할 만큼
    확실하고 비혼재된 신호가 나오지 않았음. 기존 과적합 방지 원칙에
    따라 `brands/hasselblad.py`에는 변경을 가하지 않기로 결정 — 이번
    분석의 실질적 산출물은 "반영 안 하는 게 맞다"는 근거 있는 결론.
- **재검증(2026-07, brands/core/tools 리팩토링 후)**: `apply_hncs`(순정)와
  `apply_hncs_learned`(런드)를 `tools.calibrate grid_search`/`learn_curve`로
  다시 돌려서 RMSE가 리팩토링 전과 완전히 동일하게 재현됨을 확인
  (23.31→16.51 grid_search, 23.31→15.41 learn_curve) - raw+jpeg 페어가
  여전히 10장뿐이라(나머지는 죽은 링크) 더 재보정할 새 데이터는 없음
- **day/night v3**: 공식 샘플 124장을 콘택트시트로 만들어 한 장씩 육안
  검토, 확실한 야간 장면 12장(가로등/네온/오로라/은하수/도심야경 등)을
  골라내고 나머지 112장을 day로 재분류(v2는 day 5장+night 4장뿐이었음).
  새 타깃: day 블랙p2=11.5/화이트p99.5=224.1(n=112), night 블랙p2=9.7/
  화이트p99.5=221.3(n=12) - v2보다 표본이 훨씬 크고 여전히(오히려 더)
  전체 population 타깃(11.3/223.9)에 수렴함. `apply_hasselblad_day`는
  새 타깃으로 재피팅(midtone_gamma 0.95→0.85, contrast_n 1.15→1.35,
  white_point 0.96→0.92, RMSE 22.01→18.65), `apply_hasselblad_night`는
  그리드서치해도 기존 기본값이 그대로 최적으로 나와 변경 없음. day/night를
  별개 프리셋으로 유지할 근거는 계속 약해지는 중(통합은 아직 안 함)

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
- `apply_hncs_learned` (v12): toe/shoulder 모양을 가정하지 않고
  raw+jpeg 페어에서 neutral_L→target_L 매핑을 픽셀 단위(1,078만 쌍)로
  직접 학습 — RMSE 15.4로 파라메트릭(23.3)보다 더 나음. 다만 raw+jpeg
  페어가 10장뿐이라 표본 수 제약은 동일하게 있고, 8비트 변환 왕복
  과정에서 나오는 hue 오차가 `apply_hncs`보다 약간 큼(평균 |delta|~3.0/179,
  여전히 육안상 무시할 수준)
- 학습 LUT을 표본 부족 우려로 파라메트릭 커브 쪽에 정규화해봤지만, 10장
  leave-one-out 교차검증 결과 정규화 없는 순수 경험적 LUT이 가장 좋음
  (LOO RMSE 14.6, 정규화를 강하게 걸수록 20.7→28.0으로 악화) — bin당
  픽셀 표본이 충분히 많아 분산 문제보다 파라메트릭 커브 자체의 모양
  편향이 더 크기 때문. `apply_hncs_learned`는 정규화 없이 그대로 유지
- **표본 확대 재시도(2026-07) - 전부 음성 결과**: 124장 외에 더 쓸 수
  있는 소스가 있는지 재조사했다.
  - `hasselblad.com/learn/sample-images/`의 X/H/V system 갤러리 페이지를
    Storyblok CMS의 `page-data.json`까지 직접 파싱해서 전수 대조 - 기존
    124장(139행) 대비 새로 추가된 파일 0장. 공식 소스는 이미 포화 상태.
  - 하셀블라드 공식 Instagram 게시물(사용자 제공 스크린샷 8장 검증) -
    EXIF가 플랫폼 재인코딩으로 전부 소실, 그중 한 장은 협찬/편집 콘텐츠로
    확인 - 못 씀
  - explorecams.com(500px 소스) X1D 갤러리 51장(1장은 상세페이지 404로
    제외, 50장 검증) 전수 EXIF 검증 - 44% Lightroom/Photoshop 편집,
    36% EXIF 완전 삭제, 14% Instagram 재인코딩, 진짜 SOOC로 보이는 건
    6%(3장)뿐인데다 전부 동일 작가(Raymond Cheung) - population에 넣기엔
    표본도 작고 편중돼서 제외
  - imaging-resource.com X2D 100C 리뷰 갤러리(다른 4개 population-fit
    브랜드와 같은 소스) - 비편집 후보 45장 전부 imaging-resource.com
    CDN 자체 손상("Premature end of JPEG file", curl/urllib 두 경로로
    바이트 단위 재현 확인)으로 생존 0장. 상세: `docs/methodology.md`
    "이미지 신뢰성 정책"
  - dpreview.com 샘플 갤러리(`/samples/album/hasselblad-*`) - 실제로
    갤러리 자체는 존재하지만 사이트가 Cloudflare 봇 챌린지로 막혀 있어
    (`cf-mitigated: challenge`, 프록시가 아니라 dpreview.com 자체 오리진
    응답) 자동 스크레이핑이 불가능 - 우회 시도 안 하고 제외
  - **결론**: 현재 알려진 경로로는 124장에서 표본을 더 늘릴 방법이 없다.
    `apply_hncs`/`apply_hncs_learned`/day-night 파라미터는 변경 없이
    유지.

## 외부 리뷰 반영 (2026-07, GitHub 이슈 #4)

X2D II 사용자가 방법론을 상세히 리뷰하고 제기한 지적들을 코드/데이터로
직접 대조 검증했다 - 전부 사실로 확인됨:

- **표본 출처가 100% hasselblad.com 공식이 아님**: 124장 중 99장이
  `hasselblad.com (공식)`, 25장이 `cameralabs.com (신뢰 서드파티)` -
  `run_hasselblad()`가 `source` 컬럼으로 거르지 않고 그냥 다 섞어서
  분석함. 캐시된 `csv_stats_result.csv` 기준 재계산: 전체 풀
  블랙p2=11.27(기존 문서 수치와 일치) vs 공식만=10.60 - 차이
  0.67(6%), 기존에 "노이즈 수준"으로 판단했던 캐시-vs-원본 차이(0.6,
  5.7%)와 비슷한 크기라 큰 왜곡은 아니지만, "124장 전부 공식"이라는
  문서 표현 자체는 부정확했음.
- **`genuine_render_check()`(Photoshop/Lightroom/Phocus 등 제3자 편집
  검출)가 imaging-resource.com 4개 브랜드 경로에만 걸려있고
  `run_hasselblad()`엔 없음** - 확인됨. 더 파보니 캐시된 124장 전부
  EXIF Software 태그가 비어있는데, 이건 Phocus로 편집 안 됐다는 뜻이
  아니라 `_hasselblad_download()`가 `cv2.imwrite`로 리사이즈+재저장하며
  EXIF를 통째로 날려서 애초에 검증이 불가능한 상태였던 것 - 실제로
  Phocus 렌더/편집이 섞여 있는지는 원본을 EXIF 보존한 채로 다시 받아야
  확인 가능. 아직 미해결.
- **바디 세대별 population이 문서화된 적 없음**: `run_hasselblad()`가
  콘솔에 세대별(X1D/X2D/907X·CFV) 그룹 통계를 이미 찍고 있었는데
  문서에는 한 번도 안 옮겨졌음. 캐시로 재계산한 실제 수치:

  | 세대 | n (그림자유효) | 블랙p2 | 화이트p99.5 |
  |---|---|---|---|
  | X2D 계열 | 74 (63) | 9.7 | 224.8 |
  | X1D 계열 | 11 (9) | 13.1 | 227.8 |
  | 907X/CFV | 39 (22) | 14.9 | 221.0 |

  세대 간 블랙p2가 9.7~14.9로 꽤 벌어져 있다 - 전체 풀링(11.3)이 세
  세대를 다 대표한다는 "설계 판단"이 이 표로 보면 낙관적이었을 수
  있음을 인정한다.
- **raw+jpeg 캘리브레이션 페어(13장)가 전부 X1D/X1D II 세대, X2D 계열은
  0장** - 확인됨. `apply_hncs`가 "X 시스템 전체에 걸쳐 일관 적용되는
  색철학"이라는 전제로 X1D 페어에서 학습한 커브를 X2D population
  타깃(공식 샘플의 62%가 X2D)에도 그대로 쓰고 있는데, 이 전제 자체를
  raw 기준으로 검증한 적은 없다.
- **raw 렌더링 베이스라인이 libraw 기본 디모자이크/카메라매트릭스에
  의존**(컬러차트 기반 최소자승 매트릭스로 특성화한 적 없음) - 지적
  타당함. `linear 감마로 바꿔봤더니 RMSE 악화` 실험(위 기록)이 바로 이
  불확실성의 증거였는데, 원인을 "raw 파이프라인 자체가 특성화 안 됨"
  으로 명시적으로 못박은 적은 없었음.

### Phocus 오염 재검증 결과 (2026-07)

원본을 리사이즈 전 상태로 Range-fetch(첫 256KB)해서 139장 전부 EXIF
Software 태그를 다시 확인했다 - 기존 캐시(124장)는 `_hasselblad_download()`가
`cv2.imwrite`로 재저장하며 EXIF를 통째로 날려서 이 검증 자체가 불가능한
상태였다(이 함수가 진짜 원인이었음). 결과:

- **34장(24%)에서 Adobe Photoshop/Lightroom/Camera Raw Software 태그
  확인** - 명백한 제3자 편집. 이슈 #4의 우려가 실제로 맞았음
- 6장은 `1.1.6.3`/`3.1.0`/`3.0.0` 같은 순수 버전 문자열(Make=Hasselblad,
  Model=X2D/X2D II) - explorecams.com 검증(위 기록) 때와 같은 패턴으로
  편집 도구가 아니라 카메라/Phocus 자체 렌더러 표시로 판단, 편집으로
  분류 안 함
- 84장은 Software 태그 자체가 없음(진짜 무편집인지, 핫셀블라드 CMS
  업로드 과정에서 스트립된 건지는 구분 불가 - "미확인"이지 "확인된
  무편집"은 아님)
- 3장은 HTTP 403(레이트리밋으로 추정) - 미확인

**cameralabs.com 제외 + Adobe 편집 확인분 제외 후 population 재계산**
(n=124 → n=65, 거의 절반으로 줄었지만):

| | n (그림자유효) | 블랙p2 | 화이트p99.5 |
|---|---|---|---|
| 기존 채택값(전체 풀링) | 124 (94) | 11.3 | 223.9 |
| 정제 후(공식+비편집만) | 65 (50) | 10.9 | 224.4 |

차이는 블랙p2 3%, 화이트p99.5 0.2% - 이 프로젝트가 이미 여러 번
"노이즈 수준"으로 판단한 기준(5~7%)보다도 작다. **결론: 오염된 표본이
섞여 있었던 건 사실이지만, 다행히 population 타깃 자체를 유의미하게
왜곡시키진 않았다** - `apply_hncs`/`apply_hncs_learned` 파라미터는
변경하지 않는다(과적합 방지 원칙과도 일치).

세대별 재계산(정제된 65장 기준)도 확인:

| 세대 | n (그림자유효) | 블랙p2 | 화이트p99.5 |
|---|---|---|---|
| X2D 계열 | 48 (38) | 10.2 | 227.0 |
| X1D 계열 | 4 (4) | 11.8 | 229.0 |
| 907X/CFV | 13 (8) | 14.1 | 213.3 |

X1D 표본이 4장까지 줄어서 결론을 내리기엔 너무 얇다 - 세대 간 pooling
타당성 문제(위 3번 지적)는 여전히 raw+jpeg 페어가 X1D 세대뿐이라는
근본 원인과 함께 미해결로 남는다. X2D II raw+jpeg 페어 기여 제안이
실제로 이 공백을 메울 수 있는 유일한 경로.

**코드 수정**: `tools/analyze.py`의 `_hasselblad_download()`에 리사이즈
*전* 원본 바이트 단계에서 EXIF Software 검사(`_check_genuine_bytes()`)를
추가해서, 앞으로 `python3 -m tools.analyze hasselblad`를 재실행하면
Photoshop/Lightroom 편집분이 자동으로 제외되고 제외 건수가 콘솔에
찍힌다. cameralabs.com은 하드 제외하지 않음(위 표에서 보듯 왜곡 효과가
노이즈 수준이라 서드파티 소스 자체를 배제할 근거는 약함) - 대신
`source` 컬럼이 이미 CSV에 명시돼 있어 필요하면 언제든 필터링 가능.

X2D II raw+jpeg 페어 기여 제안은 별도로 진행 중(GitHub 이슈 #4 코멘트
참고).

## 로컬 기여 데이터셋으로 세대 간 pooling 첫 실측 (2026-08, local-mixed-2026-07)

위에서 미해결로 남겼던 "raw+jpeg 페어가 X1D 세대뿐이라 세대 간 pooling
전제를 검증할 수 없다"는 공백을, 프로젝트 소유자 개인 사진 라이브러리에서
확보한 raw+jpeg 페어로 처음 메웠다. 공개 웹 스크레이핑(위 "표본 확대
재시도")과 달리 소유자 본인 소유 파일이라 라이선스 문제 없이 바로 쓸 수
있었다.

**방법론** (`tools/build_local_manifest.py`, 신규):
- EXIF `DateTimeOriginal`이 2초 이내로 일치하는 raw/jpeg를 "동일 셔터"로
  매칭 (`tools/verify_contributed_pairs.py`의 기존 허용치와 동일)
- 매칭 도중 발견: 2017년 촬영분 X1D raw 8장이 jpeg보다 정확히 **7시간**
  빠르게 기록되어 있었다(분·초 단위까지 완전 일치 - 우연으로는 사실상
  불가능한 패턴). 카메라/펌웨어가 raw와 jpeg에 서로 다른 타임존 기준으로
  타임스탬프를 찍은 것으로 추정된다. ±12시간 정수 오프셋 탐색을 추가해서
  이런 페어도 놓치지 않게 했다(단, 이 8장은 최종적으로 jpeg 자체가
  Lightroom 편집본이라 아래 검증에서 어차피 제외됨)
- 후보 104쌍 중 `verify_contributed_pairs`가 **61쌍(59%) 통과, 43쌍(41%)
  탈락** - 탈락 사유는 전부 jpeg EXIF Software에 Photoshop/Lightroom
  흔적(위 explorecams.com 검증의 44%, 오염 재검증의 24%와 같은 범주의
  오염률). 카메라 순정 jpeg만 골라내는 이 필터가 없었다면 핫셀블라드가
  아니라 Lightroom의 색과학을 측정하게 됐을 것

**통과분 61쌍의 세대 구성** - 처음으로 X2D/907X·CFV 세대의 실측 raw+jpeg
페어 확보:

| 카메라 | n |
|---|---|
| CFV 100C/907X | 30 |
| X2D 100C | 24 |
| X1D II 50C | 6 |
| X1D | 1 |

공식 샘플 13쌍(전량 X1D 계열) + 로컬 61쌍 = 총 74쌍으로
`python3 -m tools.calibrate learn_curve` 재실행. 세대별 RMSE 분해:

| 카메라 | n | 파라메트릭(v11) RMSE | 학습 LUT(v12) RMSE |
|---|---|---|---|
| CFV 100C/907X | 30 | 10.82 | 19.11 |
| X2D 100C | 24 | 19.15 | 19.64 |
| 공식 샘플(X1D 계열) | 13 | 22.38 | 23.09 |
| X1D II 50C | 6 | 41.89 | 37.17 |
| X1D | 1 | 8.25 | 32.45 |
| **전체** | **74** | **19.94** | **22.20** |

**재검증(2026-08, 공식 13쌍 중 편집 오염 9쌍 제외 후 재실행)** - 위
"Phocus 실제 렌더 대조" 절 정정에서 확인된 편집 오염 9쌍(로컬 61쌍은
이미 `verify_contributed_pairs`가 같은 기준으로 걸러낸 뒤라 무관 -
104쌍 후보 중 43쌍이 이 필터로 이미 탈락됨, 위 "방법론" 참고)을
`tools/calibrate.py`의 `_resolve_pairs()`에서 제외하도록 고치고
(`_CONTAMINATED_OFFICIAL_PAIRS` 상수) `learn_curve`를 65쌍(클린 공식
4쌍 + 로컬 61쌍)으로 재실행:

```
파라메트릭(v11) RMSE=19.11
학습 LUT RMSE=21.85
```

74쌍(오염 포함) 19.94 vs 22.20 → 65쌍(오염 제외) 19.11 vs 21.85 -
**결론 방향은 그대로**(v11이 v12를 이김), 둘 다 소폭 개선(오염된
타깃을 빼니 어느 모델이든 더 깨끗한 정답과 비교하게 된 것으로 해석).
세대별 분해는 이번엔 다시 안 돌림(재현: 위와 같은 커맨드).

**결론 - 세대 간 pooling 전제는 실측으로 기각됐다.** X1D 10장뿐이던
원래 표본에서는 `apply_hncs_learned`(v12)가 파라메트릭보다 나았다
(RMSE 15.4 vs 23.3, 위 기록 참고). 그런데 X2D/CFV 실측 데이터를 넣고
보니 뒤집힌다 - 특히 CFV 100C/907X에서는 파라메트릭이 학습 LUT보다
거의 2배 낫다(10.82 vs 19.11). X1D 페어만으로 학습한 LUT을 다른
세대에 그대로 적용하는 게 과적합이었다는 뜻으로, 위에서 지적만 하고
못 풀었던 "이 전제가 raw 기준으로 한 번도 검증된 적이 없다"는 우려가
실제로 맞았던 사례. **`apply_hncs`(파라메트릭 v11)를 기본값으로 계속
쓴다** - `apply_hncs_learned`는 세대 풀링 전제가 깨졌으므로 현재 형태로는
채택하지 않는다. 세대별로 각각 학습한 LUT이 세대 내에서는 더 나을 수
있지만(미검증), 세대당 표본이 아직 30장 안팎이라 이번엔 시도하지 않았다.

재현: `python3 -m tools.build_local_manifest <원본 폴더> datasets/hasselblad/contributed/local-mixed-2026-07`
로 페어 추가 → `python3 -m tools.calibrate learn_curve`로 재학습.

**하이브리드(regularize) 재검증(2026-08)** - 위 두 버전(v11/v12)
재검증과 같은 74쌍으로 `tools/calibrate.py regularize` 모드(v11↔v12
ridge 하이브리드, `lut = (sums + λ·prior)/(counts + λ)`)도 재실행.
최적 λ=1e9(=순수 파라메트릭) - λ를 0(이 λ=0 arm은 v12 자체가 아니라
`_build_lut_from_counts`가 평균 기반·빈 bin은 prior로 채워 근사한
것이고, v12 자체는 중앙값 기반에 np.interp 보간을 쓴다)에서 1e9까지
키우는 동안 LOO RMSE가 33.61에서 22.18로 단조 감소(전체 LOO RMSE
기준 개선폭 34.0%), 중간 지점에서 더 나아지는 구간은 전혀 없었다.
최적(=v11) vs v12(λ=0) 유의성 검정: 폴드별 페어드 비교 기준 개선폭
46.4%, 60승 14패, 부호검정 p=0.000, 부트스트랩 95% CI [+35.5%,
+56.4%](0 미포함) - 위 학습LUT 재검증(19.94 vs 22.20)과 방향은
같지만 이쪽이 이 스크립트 고유의 percentile 기반 LOO 오차라 절대값은
직접 비교 대상이 아니다. 세대별 RMSE 분해(λ=1e9 기준 - 이 표도 이
스크립트 고유의 LOO-percentile 오차라 위 v11/v12 표와 절대값이 직접
비교되지 않는다. 예: λ=1e9가 사실상 순수 v11인데도 CFV 100C/907X가
여기선 15.37, 위 v11 열은 10.82로 다르다):

| 카메라 | n | 하이브리드(λ=1e9) RMSE |
|---|---|---|
| CFV 100C/907X | 30 | 15.37 |
| X2D 100C | 24 | 13.37 |
| 공식 샘플(X1D 계열) | 13 | 27.40 |
| X1D II 50C | 6 | 48.77 |
| X1D | 1 | 31.48 |

**결론: 하이브리드는 도움이 안 된다.** v11이 이미 v12를 압도적으로
이기는 상황이라 둘을 섞을 이유가 없고, 그리드서치 자체가 그걸
정량적으로 확인해줬다. 재현: `python3 -m tools.calibrate regularize`.

## Phocus 실제 렌더 대조 (2026-08, 최초)

지금까지 `apply_hncs()`의 정답지는 항상 카메라 내장 JPEG(`raw_calib_cache/
*.target.jpg`)이었지, Phocus(Hasselblad 공식 데스크톱 RAW 컨버터) 자체의
출력은 아니었다. 이번에 처음으로 raw_calib_cache 13쌍 전부를 실제
Phocus 4.1.1(`brew install --cask phocus`)로 Import → (기본 Standard
프리셋, 조정 없음) → Export해서 진짜 HNCS 렌더 TIFF를 얻었다 - 배경은
`hncs_external_sources_analysis.md` 6절 참고.

**방법**: `tools/calibrate.py`의 `load_neutral_render()`와 동일한 레시피
(`rawpy.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8,
gamma=(2.222, 4.5))`)로 raw를 "무가공 중립" 베이스라인으로 디코드해
`apply_hncs()`에 입력, `hybrid_engine.utils.evaluate.mean_delta_e`
(CIEDE2000)로 세 이미지(카메라 JPEG target / Phocus 실제 렌더 / apply_hncs
출력)를 서로 비교. 메모리 때문에 세 이미지 전부 긴 변 512px로 축소 후
비교(기존 `evaluate_*.py` 스크립트들의 `DOWNSAMPLE_MAX_DIM` 컨벤션과
동일 - global-statistics ΔE는 다운샘플에 왜곡되지 않는다는 전제).

| 페어 | target vs apply_hncs | target vs Phocus실제 | Phocus실제 vs apply_hncs |
|---|---|---|---|
| 00378 | 5.195 | 2.573 | 5.395 |
| 02709 | 11.684 | 2.929 | 11.248 |
| B0000994 | 10.333 | 11.437 | 6.230 |
| B0001395 | 16.931 | 21.277 | 12.603 |
| x1d-II-sample-01 | 8.422 | 5.844 | 8.112 |
| x1d-II-sample-02 | 11.566 | 6.707 | 11.419 |
| x1d-II-sample-06 | 9.647 | 3.309 | 11.404 |
| x1d-II-sample-09 | 16.356 | 6.905 | 22.427 |
| x1d-ii-xcd45p-01 | 9.336 | 5.028 | 8.088 |
| x1d-ii-xcd45p-02 | 9.909 | 6.219 | 11.682 |
| x1d-xcd45-01 | 12.047 | 4.115 | 14.885 |
| x1d-xcd45-03 | 4.247 | 3.897 | 3.264 |
| x1d-xcd45-04 | 3.364 | 3.443 | 3.109 |
| **평균(n=13)** | **9.926** | **6.437** | **9.990** |
| **중앙값** | **9.909** | **5.028** | **11.248** |

**읽는 법**:
- **target vs Phocus실제(평균 6.44)가 target vs apply_hncs(평균
  9.93)보다 낮다** - 예상대로 Phocus 데스크톱 렌더가 카메라 내장
  JPEG(둘 다 "진짜 HNCS" 계열)에 더 가깝고, 우리 파라메트릭 근사가
  그보다 한 단계 더 멀다. 다만 완전히 일치하지도 않는다(0이 아님) -
  데스크톱 렌더와 인카메라 렌더 사이에도 실제 차이가 있다는 뜻(펌웨어/
  Phocus 버전 차이, 혹은 일부 target.jpg 자체의 편집 오염 가능성 -
  `hncs_external_sources_analysis.md`의 "Phocus 오염 재검증" 사례처럼
  이 13쌍도 개별 검증된 적은 없다).
- **phocus실제 vs apply_hncs(평균 9.99)가 target vs apply_hncs(9.93)와
  거의 같다** - 정답지를 카메라 JPEG에서 진짜 Phocus 렌더로 바꿔도
  결론(우리 근사와 진짜 HNCS 사이엔 여전히 격차가 있다)은 안 바뀐다는
  뜻.
- **B0000994/B0001395 두 페어가 뚜렷한 이상치**(target vs Phocus실제가
  11.4/21.3로 나머지 페어의 2~4배) - n=13 중 2개뿐이라 전체 평균을
  왜곡할 수 있다. 이 두 페어의 target.jpg가 실제로 순정 카메라 렌더가
  맞는지(위 우려 그대로) 별도 검증 없이는 위 평균 수치에 과도한 확신을
  두지 않는 게 맞다.
- **표본 수(n=13)가 작고, 이건 어디까지나 1회 실측**(부트스트랩/부호검정
  등 `hybrid_engine/CLAUDE.md`급 통계 처리는 안 함 - "A가 B를 이긴다"는
  판정이 아니라 "이 정도 격차가 있다"는 서술적 기록이라서다).

재현: Phocus에서 `raw_calib_cache/*.3FR`/`*.fff` 13개를 Import(기본
Standard 프리셋) → TIFF Export 후, 이 문서를 생성한 1회성 스크립트
(경로는 세션 스크래치 - 재현 시 `tools/calibrate.py`의
`load_neutral_render()` + `hybrid_engine.utils.evaluate.mean_delta_e` +
`hybrid_engine.utils.io.load_image_linear`를 조합하면 동일 로직).

**하우스키핑**: Phocus로 `raw_calib_cache/`를 직접 Import하면 그 폴더에
`*.phos` 사이드카 파일이 새로 생긴다(Phocus의 조정값 저장 파일) -
`raw_calib_cache/`는 이미 `.gitignore` 대상이라 커밋에는 안 잡히지만,
로컬에 남아있다는 점은 기록해둔다.

> **정정(2026-08-03, 위 "이 13쌍도 개별 검증된 적은 없다"는 우려를
> 실제로 검증해서 발견)**: `raw_calib_cache` 13쌍 전부의 `target.jpg`
> EXIF `Software` 태그를 확인했다 - **13개 중 9개가 제3자 편집
> 소프트웨어 태그를 갖고 있다**, `apply_hncs()`(v11)의 원 캘리브레이션
> 데이터셋 자체에서 이 검증이 이번이 처음이다:
>
> | 페어 | Software 태그 |
> |---|---|
> | 00378 | 없음(순정 추정) |
> | 02709 | 없음(순정 추정) |
> | B0000994 | Adobe Photoshop CC 2018 (Windows) |
> | B0001395 | Adobe Photoshop CC 2018 (Windows) |
> | x1d-II-sample-01 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-02 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-06 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-09 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-ii-xcd45p-01 | 없음(순정 추정) |
> | x1d-ii-xcd45p-02 | 없음(순정 추정) |
> | x1d-xcd45-01 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
> | x1d-xcd45-03 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
> | x1d-xcd45-04 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
>
> "Software 태그 없음"은 위 "Phocus 오염 재검증" 절과 같은 이유로
> "확인된 무편집"이 아니라 "미확인"이다 - 다만 최소한 명백한 편집
> 흔적은 없다는 뜻이므로 아래에서 "클린 4쌍"으로 취급한다.
>
> **클린 4쌍(00378/02709/x1d-ii-xcd45p-01/02)만으로 재계산한 ΔE00**
> (n=13 표와 나란히 - 표본이 4개뿐이라 참고용이지 대체용이 아니다):
>
> | | target vs apply_hncs | target vs Phocus실제 | Phocus실제 vs apply_hncs |
> |---|---|---|---|
> | 평균(n=4, 클린) | 9.031 | 4.187 | 9.103 |
> | 중앙값(n=4, 클린) | 9.623 | 3.978 | 9.668 |
> | 평균(n=13, 전체) | 9.926 | 6.437 | 9.990 |
>
> 방향은 안 바뀐다(클린 4쌍만 봐도 target-vs-apply_hncs가 target-vs-
> Phocus실제보다 여전히 크다) - 다만 n=4는 통계적으로 사실상 아무것도
> 증명 못 하는 크기라, 이 정정의 요점은 "결론이 바뀌었다"가 아니라
> **"apply_hncs() v11을 학습시킨 원본 13쌍 중 9쌍이 편집 소프트웨어를
> 거쳤을 가능성이 이번에 처음 확인됐다"**는 것이다 - 이건 이 Phocus
> 비교 실험보다 훨씬 근본적인 문제이고, v11 자체의 재캘리브레이션
> 여부는 이 문서 스코프 밖의 별도 결정이다(`apply_hncs()`는 이 세션에서
> 손대지 않았다).

## White Patch / Shades of Gray 자동 화이트밸런스 정확도 (2026-08)

`tools/raw_pipeline.py --auto-wb-mode {white_patch,shades_of_gray}`(신규,
`core/log_pipeline.py`)가 raw_calib_cache 13장(실사진, 컬러차트 아님)에서
카메라의 실제 AsShotNeutral(DNG 스펙, 정답으로 취급) 대비 얼마나
정확한지 실측.

**방법**: 각 RAW를 (a) `use_camera_wb=True`(카메라 실제 WB, 기준)와 (b)
`use_camera_wb=False`(무보정) 두 번 디코드. (b)에 `estimate_wb_white_patch`/
`estimate_wb_shades_of_gray`를 적용해 두 추정 렌더를 만들고, (a)와
ΔE00(CIEDE2000, ProPhoto RGB Linear 색공간 - `hybrid_engine.utils.
evaluate.mean_delta_e`는 sRGB 가정이라 이 모듈에는 못 쓰고 같은 로직을
ProPhoto로 복사)로 비교. 별도로 R/G, B/G 채널비(화이트밸런스 게인 자체)의
AsShotNeutral 대비 상대오차%도 같이 쟀다.

| 페어 | ΔE00(white_patch) | ΔE00(shades_of_gray) |
|---|---|---|
| 00378 | 14.72 | 5.23 |
| 02709 | 21.06 | 21.67 |
| B0000994 | 13.92 | 18.30 |
| B0001395 | 23.53 | 24.71 |
| x1d-II-sample-01 | 16.75 | 7.19 |
| x1d-II-sample-02 | 6.50 | 7.57 |
| x1d-II-sample-06 | 26.07 | 17.56 |
| x1d-II-sample-09 | 20.14 | 22.00 |
| x1d-ii-xcd45p-01 | 8.15 | 10.42 |
| x1d-ii-xcd45p-02 | 4.28 | 7.67 |
| x1d-xcd45-01 | 14.14 | 11.83 |
| x1d-xcd45-03 | 22.54 | 24.74 |
| x1d-xcd45-04 | 13.56 | 3.66 |
| **평균(n=13)** | **15.80** | **14.04** |
| **중앙값** | 14.72 | 11.83 |

R/G+B/G 상대오차%(보조 지표): white_patch 평균 100.1%(중앙값 78.8%),
shades_of_gray 평균 95.7%(중앙값 101.6%) - 방향은 ΔE00과 일치(둘 다
큰 오차, shades_of_gray가 근소하게 나음).

**결론**: 이 프로젝트 기준 ΔE00 < 2.0이 "사람 눈에 구별 안 됨"인데,
평균 14~16이면 **명백히 다른 색감**이다. 두 알고리즘 다 "장면 안에
진짜 중립(흰/회색) 표면이 있다"는 전제에 의존하는데, raw_calib_cache가
컬러차트가 아니라 실사진이라 이 전제가 자주 깨진다 - 특히 white_patch는
밝은 색유리/하늘/조명이 있으면 채널 비율이 1.000/1.000으로 완전
saturate(B0001395, x1d-xcd45-03, x1d-II-sample-09에서 R/G,B/G 상대오차
150~214%)되는 사례가 여러 건. **실사용 권장 안 함** - 카메라 자체
화이트밸런스를 대체하는 용도가 아니라, 조명 정보 없이 "다른 느낌"을
실험해보는 창작 워크플로우용으로만 의미가 있다. 재현: 위 방법 그대로
raw_calib_cache 13장에 대해 반복(1회성 스크립트, 리포에는 없음).

**관련 실측(다른 서브시스템)**: 이 실패는 새로운 발견이 아니라 이
프로젝트가 이미 알고 있던 한계의 재확인이다. `hybrid_engine/EVALUATION.md`
("Protocol 2: Cross-camera generalization" 절, 후속 실측 12~19 부근)가
`hybrid_engine`의 색치우침(color-cast) 보정 단계에서 Gray World(전역
무채색 평균 가정)와 그 변형(robust/percentile, 밝기 구간별 zoned,
strength 미세조절)은 물론 Gray Edge(공간 미분 기반, van de Weijer 2007)
까지 광범위하게 실측했는데, 결론이 같다 - "장면 전체가 대략 무채색"
같은 전역 가정은 야경/색이 편중된 실사 장면에서 구조적으로 깨진다(Gray
World를 완전히 제거하니 오히려 ΔE 9.687->18.431로 거의 2배 악화됐을
정도로, 제거보다는 있는 편이 나았지만 그 반대로 "더 정교하게 다듬으면"
하는 시도들은 전부 +0.7% 이내의 무의미한 개선에 그침). White
Patch/Shades of Gray는 같은 문제(전역 무채색/중립표면 가정)를 다른
알고리즘으로 시도한 것뿐이라 같은 벽에 부딪힌 것으로 해석할 수 있다.
README.ko.md/`.md`가 이미 명시한 메타메리즘("센서 분광감도가 CIE
표준관측자와 정확히 비례하지 않아... 잔차는 ΔE 루프로만 줄일 수 있음")
한계와도 같은 결의 문제다.
