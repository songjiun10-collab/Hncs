# 방법론 / 검증 기록

*[English](methodology.en.md)*

[메인 README](../README.md)로 돌아가기.

## 이미지 신뢰성 정책 (2026-07~)

imaging-resource.com의 media CDN이 여러 카메라 리뷰 갤러리에서 원본
파일 자체를 손상된 채로 저장하고 있는 걸 발견했다(Hasselblad X2D 100C
갤러리 72%, Phase One XF 100MP 갤러리 100%, Pentax 645Z/K-1 갤러리
40%가 디코드 도중 멈추고 나머지가 빈 채로 저장돼 있었음 - 재다운로드를
여러 방식으로 반복해도 똑같이 재현돼서 전송 문제가 아니라 사이트에
저장된 파일 자체의 결함으로 확인). `cv2.imread()`는 이런 파일도
"Premature end of JPEG file" 경고만 띄우고 나머지를 검은 픽셀로 채운 채
조용히 "성공"해버려서 로드 성공 여부나 shape만으로는 못 거른다.

**그래서 이제부터 모든 population 분석은 `core/validation.py`의
`is_image_usable()`(행 단위 표준편차로 손상 여부 판정)을 통과한
이미지만 쓴다.** `tools/analyze.py`의 모든 다운로드 경로(핫셀블라드
공식 CDN + imaging-resource.com 4개 브랜드)와 `tools/download.py`의
후지 Google Drive 다운로드 경로(`download_fuji_pairs()`) 전부에 이미
적용돼 있어 앞으로 새로 스크레이핑하는 이미지는 자동으로 걸러진다.

기존에 커밋된/캐시된 population 데이터를 전부 재검증한 결과:
  - Leica(45장), Fuji(mirrorlesscomparison.com, 10개 바디 40장 JPEG):
    손상 0장 - 수치 변경 없음
  - Ricoh GR: 기존 40장(GR III+IIIx) 손상 0장. 이후 GR/GR II 갤러리를
    추가로 찾아 n=80으로 확대(GR II의 HDR on/off 비교샷은 필터링) -
    재검증된 수치로 교체
  - Pentax(40장 중 16장 손상): 재수집으로 n=40 유지, 재검증된 수치로 교체
  - Phase One(30장 중 30장 전부 손상): 갤러리 전체(110장 후보)를
    재수집했지만 91장이 또 손상이라 n=16으로 축소, 재검증된 수치로 교체
    (표본 확대를 위해 Phase One XT 갤러리도 시도했으나 살아남은 이미지가
    전부 흑백 전용 Achromatic 백이라 컬러 population에는 못 써서 제외)
자세한 수치는 각 브랜드 파일 docstring 참고.

**핫셀블라드 X2D 100C 갤러리 후속 조사(2026-07) - 최종 결론: 사용 불가.**
위에서 "72% 손상"이라고만 언급하고 후속 결론을 안 남겼던 게 있어서
`tools.analyze`의 `run_imaging_resource_brand()`로 실제로 돌려봤다.
편집본("-MOD") 페어를 제외한 비-MOD 후보 45장 전부를 원본/scaled 두
버전 다 시도했지만 44장이 "Premature end of JPEG file"로 손상, 나머지
1장은 EXIF 기대 렌더러 불일치 - **생존 0장**. curl과 python urllib
두 경로로 동일 URL을 재다운로드해 바이트 단위로 완전히 동일하게 깨져
있음을 확인해서 우리 다운로드 파이프라인 버그가 아니라 imaging-resource.com
CDN에 저장된 파일 자체의 손상임을 재확인했다(Phase One XF 100MP 갤러리
100% 손상 사례와 같은 성격). Phase One XT 때처럼 `BRAND_CONFIGS`에는
넣지 않고 `tools/analyze.py` 주석으로만 시도 기록을 남김 - 핫셀블라드는
여전히 `cdn.hasselblad.com` 공식 124장 단일 소스가 최선이다.

## 브랜드 함수 QA 검증 (2026-07)

Canon/Sony/Nikon 추가 후 `brands/*.py`의 모든 `apply_*` 함수(핫셀블라드
4종 + 후지 프리셋 10종 + 라이카/Phase One/Pentax/Ricoh GR/Canon/Sony/
Nikon 7종, 총 21개)를 랜덤 BGR 배열에 돌려 shape/dtype이 그대로
보존되는지 확인함. 전부 정상 동작 확인 - 발견된 버그 없음
(주의: `apply_acros`/`apply_monochrome`은 설계상 1채널 그레이스케일을
반환하므로 shape 비교 시 별도 취급 필요, `core.curve`/`core.lut`에서
`fuji.py`로 재노출된 `apply_highlight_rolloff`/`apply_lut`은 브랜드
프리셋이 아니라 범용 헬퍼라 이 테스트 대상이 아님). 처음엔 수동
스모크테스트였다가 `tests/test_brands.py`로 정식 테스트화 - 이 과정에서
README가 후지 프리셋 개수를 9종으로 잘못 적어온 걸 발견해 10종으로
정정(코드 자체는 원래도 맞았음, 문서만 stale했음).

Canon/Sony/Nikon도 나머지 5개 브랜드처럼 픽셀 단위 5종 시그니처 분석
(tone/color/texture/gamut/joint_distribution)으로 확장 완료
(`datasets/canon,sony,nikon/`) - 이 과정에서 3개 병렬 에이전트가 각자
sharpening/micro_contrast 공식을 독립 추정하며 스케일이 갈린 걸 발견해
Sony를 재계산하고 Canon/Sony vs Nikon 간 micro_contrast 비교불가
caveat를 남겼다(각 브랜드 docstring 참고). 이 세 브랜드를 raw 기준선
있는 캘리브레이션(핫셀블라드급)으로 업그레이드할 수 있는 raw+jpeg 페어
소스도 조사했으나 mirrorlesscomparison.com(페어링 자체가 안 됨)/
imaging-resource.com(raw 다운로드 링크 사망) 둘 다 불가로 결론,
population-fit 방식 유지.

## population 통계 재현성 감사 (2026-07)

13개 브랜드 중 population-fit 방식 10개(leica/phaseone/pentax/ricoh_gr/
canon/sony/nikon/panasonic/olympus/sigma) 전부를 대상으로, 각 브랜드
docstring에 적힌 population 수치가 지금 로컬에 캐시된 이미지로 처음부터
다시 계산해도 재현되는지 `core.stats.image_stats()`로 전수 재검증했다
(캐시 파일 834장, `is_image_array_usable()` 무결성도 재확인 - 손상
0건). 결과: **10/10 전부 일치**, 실제 불일치 0건. Sigma에서 재구현한
버스트 중복 제거 로직이 `brands/sigma.py`에 이미 문서화된 것과 동일한
거짓양성(파일명 접두사가 다른데 프레임번호만 우연히 근접한 두 장을 같은
장면으로 오판 - "YC-78.jpg" vs "YSDIM0080.jpg")을 재현했지만, 이는 감사
스크립트가 원본 수집 스크립트의 접두사매칭 보강 로직을 재구현하지
않아서 생긴 것이지 실제 커밋된 데이터의 문제는 아님(원인 추적 후 확인).
`_TOE_LIFT`/`_WHITE_POINT` 상수도 10개 브랜드 전부 docstring의 최종
채택값과 정확히 일치.
