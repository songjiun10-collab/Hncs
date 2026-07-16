"""
Nikon 색감 근사 - population 통계 기반 1차 버전

imaging-resource.com 카메라 리뷰 갤러리에서 미편집 SOOC JPEG를 모아
population 통계를 냈다. 원래 5개 바디(Z9/Z6/Z6 II/D850/D780)를 시도했지만
아래 이유로 Z9/D850은 population 표본에서 제외됐고, Z6/Z6 II/D780 세
바디(n=69)로 최종 계산했다. EXIF Make="NIKON CORPORATION"(Model은
"NIKON Z 6"/"NIKON Z 6_2"/"NIKON D780" 등)으로 진짜 SOOC 확인, Software에
Photoshop/Lightroom/Capture One/Camera Raw가 있으면 제3자 편집으로 거절.

Nikon Z9/D850 갤러리 결함(2026-07 신규 발견 - 기존에 문서화된 CDN
행단위 손상과는 다른 종류): 갤러리 목록 페이지에는 각각 69장/189장의
(편집·테스트샷 파일명 필터 통과) 후보가 있었지만, 상세페이지가 "이
이미지는 브라우저 창에 맞게 축소됐습니다. 원본을 보려면 클릭하세요"라고
안내하는 그 링크(FULL_IMG_RE가 잡는 <a href>)가 실제로는 EXIF가 통째로
빠진 100~150px짜리 자리표시자 JPEG(파일 크기 2~8KB, 흑백 1채널인 경우도
있었음)를 가리키고 있었음. cv2로는 멀쩡히 디코드되고 is_image_usable()의
행단위 분산 검사도 통과하지만(작아서 애초에 "손상된 큰 이미지"가
아니라 원래 그 크기의 정상 파일이라 검사 대상 자체가 아님) -
genuine_render_check()가 EXIF Make 부재로 전부 걸러내서 결국 사용
불가로 판정됨. Z9는 69장 후보를 전부 시도(균등 인덱스 샘플링 + HEAD
요청으로 파일 크기도 별도 재확인)해서 단 한 장도 못 건졌고, 최신
"/cameras/nikon-z9-review/gallery/" URL로도 같은 상세페이지 세트라
결과가 같았음 - 이 갤러리는 그 사이트에서 완전히 죽어있는 것으로 결론.
D850도 갤러리 목록의 189장 중 187장이 같은 결함(2017/08 업로드 배치,
파일명 접두어 "Y-wb-"/"Y-JG-")이었고, 나머지 2장만 다른 업로드 배치
(2018/04, 파일명 접두어 "94718_Y-D850-", 다른 촬영자로 추정)로 정상
EXIF가 붙어 있어 통과함 - 그러나 그 2장 다 그림자유효(dark_pct>5)가
아니라서 블랙포인트 계산에 아예 못 쓰고, n=2는 population 타깃에
넣기엔 표본이 너무 작아 제외했다(라이카의 존재하지 않는 T 슬러그,
Phase One XT의 흑백전용 백 제외와 같은 이유의 판단 - leica.py/
phaseone.py 참고).

population 통계 (2026-07, n=69, Z6+Z6 II+D780만):
  전체:              블랙p2=13.7(그림자유효 43)  화이트p99.5=237.3  채도=94.9
  Z6    (n=23, 그림자유효 16):  블랙p2=13.6  화이트p99.5=239.7  채도=96.3
  Z6 II (n=23, 그림자유효 18):  블랙p2=10.6  화이트p99.5=236.7  채도=77.3
  D780  (n=23, 그림자유효  9):  블랙p2=20.0  화이트p99.5=235.7  채도=111.0

D780(DSLR, 2020)이 Z6/Z6 II(미러리스)보다 블랙포인트가 뚜렷하게 높고
채도도 높음 - DSLR과 미러리스의 JPEG 렌더링 파이프라인 차이일 수도,
D780 표본의 그림자유효 비율이 유독 낮아서(9/23=39% vs Z6 16/23=70%,
Z6 II 18/23=78%) 애초에 그림자 콘텐츠가 적은 촬영 세트(밝은 야외 위주)
였을 수도 있어 원인은 미확인. Z6와 Z6 II는 파일명 접두어(둘 다
"Y-JG-")로 보아 같은 촬영자의 비슷한 촬영 세트로 보이고, 실제로 서로
값이 더 가까웠다.

무결성 검증(core/validation.py is_image_usable()): 다운로드 시도 중
기존에 문서화된 CDN 행단위 손상(위 자리표시자 결함과는 별개)으로
거부된 파일이 Z9 쪽에서 1장 있었음 - 이미 갤러리 자체가 죽어있어
population에 영향 없음.

leica.py/phaseone.py/pentax.py/ricoh_gr.py와 동일한 한계: raw 기준선이
없어 population 타깃을 film_curve의 toe_lift/white_point에 직접 대입한
것이고, shoulder_start/clahe_clip/hue·채도 무조작 가정은 검증 없이
핫셀블라드 기본값을 차용.

raw 기준선 업그레이드 가능성 조사(2026-07): mirrorlesscomparison.com과
imaging-resource.com 양쪽에서 Nikon raw+jpeg 페어 소스를 재확인했으나
둘 다 불가로 결론(canon.py 참고 - 동일 조사를 세 브랜드 공통으로 진행).
mirrorlesscomparison.com은 Fuji 때와 같은 이유(RAW/JPEG 폴더가 같은
프레임 페어가 아님)로 못 씀 - 이 사이트엔 Z6/Z7 갤러리만 있고
population-fit에 쓴 Z6 II/D780은 아예 없음. imaging-resource.com의
raw 다운로드 링크는 사이트 마이그레이션으로 죽어서 사용 불가. 억지로
raw 기준선을 만들 근거가 없어 population-fit 방식을 유지하기로 결정.

픽셀 시그니처 분석(2026-07, `datasets/nikon/{tone,color,texture,gamut}_signature.json`
+ `joint_distribution.npz`): Leica/Pentax/Ricoh GR/Phase One과 동일
방법론(사진 단위 동일가중 평균, 중앙 2400x2400 크롭에서 샤프닝/미세대비/
노이즈/에지헤일로 측정)으로 재분석. 이 분석은 population-fit 타깃 계산과
달리 D850 정상 EXIF 2장(94718_Y-D850- 접두어, 표본 크기가 작아 population
fit에서만 제외됐던 것으로 진위 문제는 아니었음)까지 포함해 n=71로 계산
(population.py의 n=69는 Z6/Z6 II/D780 3바디만). 톤 재계산 결과 그림자유효
(43장) 블랙p2=13.67로 population 타깃값(13.7)과 거의 정확히 일치해 방법론
일관성 재확인. 채도=93.14, 샤프닝=4.03(Laplacian std/10 - Canon의 Sobel
std/15와는 다른 연산자지만 자릿수는 Leica 2.48/Ricoh GR 3.36과 비슷하게
맞음), micro_contrast=8.29(DoG sigma 1.0/4.0 - Leica/Pentax/Ricoh GR과
비슷한 8~12대, Canon/Sony의 sigma(1,2) 조합보다 이쪽이 기존 관례에 더
가까움), chroma_mean=17.24. hue/채도를 안 건드리는 설계라 color/gamut
수치는 보정 타깃이 아니라 참고 자료.
"""
from core.engine import apply_population_fit_look

_TOE_LIFT = 13.7 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_nikon_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
