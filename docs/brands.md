# 브랜드별 상세 방법론

*[English](brands.en.md)*

[메인 README](../README.md)로 돌아가기.

population-fit 방식으로 추가한 브랜드 중, 접근 자체가 브랜드마다 달라서
정리해둘 가치가 있는 5개(후지필름/라이카/Phase One/Pentax/Ricoh GR)의
상세 기록. Canon/Sony/Nikon/Panasonic/Olympus/Sigma는 방법론이
거의 동일해서(imaging-resource.com population + 5종 시그니처 분석) 각
`brands/*.py` docstring에만 기록돼 있다.

## 후지필름 (`brands/fuji.py`)

후지는 카메라에 내장된 필름시뮬레이션(Provia/Astia/Velvia/Classic
Chrome/Pro Neg Std 등) 프리셋이 여러 개 있어서, 핫셀블라드와 다른
검증 방법을 씀: mirrorlesscomparison.com 리뷰 갤러리에서 진짜
미편집 SOOC JPEG를 모으고, exiftool로 읽은 실제 Film Mode 태그별로
population 통계를 비교해서 각 프리셋이 실측과 같은 방향으로 채도/톤을
움직이는지 확인 (`tools/analyze.py fuji_film_modes`).

- raw+jpeg 같은 사진 페어를 노려봤지만(`tools/download.py fuji-pairs`),
  이 사이트의 "RAW samples"와 "SOOC JPG samples" 폴더는 애초에 같은
  촬영을 짝지어 올린 게 아니라 그냥 각각 다른 사진들이었음 - 10개
  카메라, RAW 57장+JPEG 40장을 받았는데 EXIF 촬영시각이 정확히 일치하는
  페어는 3쌍뿐(그마저 다 Provia). raw 기반 캘리브레이션(핫셀블라드
  v10~v12급)은 포기하고 population 비교로 전환.
- 실측(n=8~15) vs `apply_astia`/`apply_pro_neg_std`를 Provia 사진에
  적용했을 때의 방향 비교 결과, 둘 다 실측과 정반대로 채도가 올랐음
  (Astia 실측 -12.9 vs 프리셋 +9.4, Pro Neg Std 실측 -19.4 vs 프리셋
  +11.3). 원인은 톤커브를 BGR 채널에 개별로 걸어서 채널 간 격차가
  벌어지며 채도가 재상승하는 것 (원본 125.0 -> HSV desaturation 후
  109.4 -> BGR별 커브 후 139.7, 원본보다도 높아짐). Lab L채널에만
  커브를 적용하도록 두 프리셋 다 수정.
- Pro Neg Std는 L채널로 옮긴 뒤에도 여전히 반대 방향이었는데, 커브
  모양 자체가 틀렸던 것으로 판명 - 기존엔 대비를 강조하는 S커브
  (n=1.4)를 썼는데 실측은 Pro Neg Std가 Provia보다 오히려 대비가 낮은
  플랫한 프로파일(블랙p2 +2.7, 화이트p99.5 -19.0)이었음. 대비 완화
  커브(n=0.65)로 교체.
- 수정 후 재검증: Astia 1/3 → 2/3 방향 일치, Pro Neg Std 0/3 → 3/3
  방향 일치.

## 라이카 (`brands/leica.py`)

라이카는 후지식 다중 필름시뮬레이션이 없고, 핫셀블라드 공식 킷 같은
raw+jpeg 페어 세트도 못 찾음 (dpreview/kenrockwell/photographyblog는
Cloudflare 봇 차단, stevehuffphoto.com은 Photoshop/Lightroom 편집본이라
SOOC 아님, leicarumors.com이 링크한 DNG는 Dropbox 폴더인데 JS
렌더링이라 목록을 못 긁음 - Fuji 때 Google Drive는 `gdown`으로
우회했지만 Dropbox는 동급 도구가 없었음. 라이카 공식 사이트를 Drupal
jsonapi까지 파봤지만 역시 노출 안 됨, imaging-resource.com 갤러리도
M9/X Vario/SL2 외에 추가로 찾은 슬러그가 전부 무효였음). 대신
imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG 45장
(M9/X Vario/SL2, exiftool Software 태그로 Photoshop/Lightroom 편집본
제외)을 모아 population 통계만 냈음 - 핫셀블라드 v8/v9와 같은 급, raw
대비 진짜 전/후 피팅은 아직 없음.

- population 통계(n=45): 블랙p2=9.2, 화이트p99.5=229.8, 채도=98.6.
  카메라별 편차가 커서(SL2 화이트p99.5=192.1 vs M9 251.6) 표본이 더
  모일 때까지 전체 평균을 타깃으로 사용
- `apply_leica_look()`은 이 population 타깃을 `film_curve`의
  toe_lift/white_point에 직접 대입해서 만든 1차 버전 - raw 기준선이
  없어 그리드서치로 피팅한 게 아니고, shoulder_start/clahe_clip/
  hue·채도 무조작 가정은 전부 핫셀블라드 값을 검증 없이 차용한 것.
  raw 페어를 구하면 제일 먼저 검증해야 할 부분

## Phase One (`brands/phaseone.py`)

Phase One 디지털백은 스튜디오/테더링 중심이라 컨슈머 카메라 같은
인카메라 JPEG 엔진이 사실상 없음 - imaging-resource.com에서 받은 샘플
전부 EXIF Software가 "Capture One"(Phase One 자체 RAW 컨버터)이었음.
그래서 이 프로젝트가 재현하려는 건 "카메라 JPEG"가 아니라 "Capture One
기본 렌더링"이 됨. raw(IIQ) 다운로드 링크는 imaging-resource.com 현재
사이트 템플릿에서 못 찾음(라이카 SL2도 마찬가지였음 - 개편되며 사라진
기능으로 보임) - 라이카와 같은 population 통계 방식으로 접근.

- 1차 실행(n=20)에서 8/20이 ISO 노이즈 테스트 차트(ISO-50~25600, 같은
  장면 반복 촬영)였는데 이게 population을 왜곡시킴 - 채도 평균이 76.9로
  나왔다가 차트 샷을 빼니 118.6으로 확 달라짐. 파일명 "-iso-" 필터를
  추가하고 표본을 30장으로 늘려 재실행
- population 통계(n=30, ISO 차트 제외): 블랙p2=11.4(그림자유효 9장),
  화이트p99.5=228.4, 채도=96.0
- `apply_phaseone_look()`도 라이카와 같은 방식(raw 기준선 없이
  population 타깃을 toe_lift/white_point에 직접 대입) - shoulder_start/
  clahe_clip/hue·채도 무조작 가정 미검증인 것도 동일

## Pentax (`brands/pentax.py`)

imaging-resource.com 리뷰 갤러리(645Z 중형포맷 + K-1 풀프레임)에서
미편집 SOOC JPEG 40장을 모음. EXIF Make="RICOH IMAGING COMPANY, LTD."
(펜탁스는 리코이미징 소유 브랜드), Software가 카메라 펌웨어 버전
문자열인 것으로 진짜 SOOC 확인. 이 사이트에서 DNG 링크는 라이카/Phase
One 때와 마찬가지로 못 찾아서 population 통계만 사용.

- population 통계(n=40): 전체 블랙p2=10.8, 화이트p99.5=239.1, 채도=124.1
- 바디별: 645Z(n=20) 블랙p2=10.4/화이트p99.5=247.2/채도=141.1, K-1(n=20)
  블랙p2=11.1/화이트p99.5=231.0/채도=107.1 - 블랙포인트는 거의 같은데
  645Z가 화이트/채도 둘 다 높음. 중형포맷 특성인지 표본(리뷰어 1인)
  편향인지는 미확인, raw 페어 없이는 판단 불가
- `apply_pentax_look()`도 동일한 population-fit 방식, 동일한 미검증
  한계(shoulder_start/clahe_clip/hue·채도 무조작)

## Ricoh GR (`brands/ricoh_gr.py`)

imaging-resource.com 리뷰 갤러리(GR III + GR IIIx)에서 population 통계
추출. 펜탁스와 같은 리코이미징 브랜드라 EXIF 패턴도 동일.

- 1차 수집(n=40)에서 GR IIIx에 조리개 브라케팅 테스트샷(-f2.8/-f4.0/
  -f8.0 등, 같은 장면 반복 촬영 6장)이 섞여 population을 왜곡 - Phase
  One의 ISO 차트와 같은 종류 문제. 파일명 정규식(`-f\d`)으로 걸러내고
  재계산(영향은 작았음: 채도 87.7→84.9, 표본 비중이 15%로 ISO 테스트
  30%보다 적었기 때문). `tools/analyze.py`의 스킵 패턴에 반영해서 다음
  실행부터는 자동 제외
- population 통계(n=34, f값 테스트 제외): 블랙p2=10.3, 화이트p99.5=243.9,
  채도=84.9
- `apply_ricoh_gr_look()`도 동일한 population-fit 방식, 동일한 미검증
  한계
