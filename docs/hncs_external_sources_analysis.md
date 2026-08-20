# 외부 문서 분석: HNCS/Phocus 관련 (blog.tonalphoto.com + Luminous Landscape 포럼)

*[English](hncs_external_sources_analysis.en.md)*

[메인 README](../README.md)로 돌아가기.

이번 세션에서 조사한 외부 문서 17건(블로그 16건 + 포럼 스레드 1건)을
모아서 정리한다. 목적은 두 가지: (1) "실제 HNCS"에 대해 외부에서
얻을 수 있는 가장 신뢰할 만한 정보를 한 곳에 모으고, (2) 그 정보를
이번 세션에서 실행한 3개의 실측 실험(하드-클러스터 구조 실험, 색수차
보정 실험, 조명 블렌딩 실험)과 교차 대조해서 뭐가 확인됐고 뭐가
확인 안 됐는지 정직하게 정리하는 것.

## 출처와 신뢰도

**저자는 이 프로젝트의 실제 기여자다.** blog.tonalphoto.com의 저자
Konrad Michels는 `datasets/hasselblad/contributed/kmichels-x2dii-2026-07/`
(GitHub 이슈 #4를 통해 기여된 X2D II ColorChecker 데이터, 이미
`hasselblad.json` v1.3에 반영됨)의 바로 그 기여자다. 우연한 발견이
아니라 실제로 연결된 사람의 후속 공개 글이라는 뜻.

저자 본인이 매 글에서 명시하는 대로, 이 문서들은 **Hasselblad의
공식 기술지원이나 발표가 아니라 개인 조사/실측**이다. 방법론이
투명하고(측정 도구, 소프트웨어 버전, 원자료 명시) 스스로 실수를
정정한 이력(`.phos` 프리셋 저장 여부 관련 정정, 2026-05-04)도 있어서
신뢰도가 낮지 않지만, 어디까지나 리버스 엔지니어링이지 Hasselblad가
공식 확인한 사실이 아니라는 점을 계속 염두에 둬야 한다.

**Luminous Landscape 포럼 스레드**("Hasselblad Natural Color Solution
(HNCS) - how it works (probably)", 저자 미상, 커뮤니티 기술 분석)는
한 단계 더 신뢰도가 낮다 - 제목에 이미 "probably"가 붙어있고, 저자가
H4D-50 기종으로 직접 관찰한 정황 증거("같은 프로파일인데 텅스텐/
데이라이트 둘 다 색이 좋다")에서 역추론한 것이다. 다만 이 블로그
저자가 이 스레드를 인용하면서 자신의 Phocus 4.x 실측 결과와 일치한다고
확인했고, 이 프로젝트도 별도로 이 스레드의 핵심 주장(4개 광원, 자동
선택+블렌딩)이 물리적으로 말이 되는 구조라고 판단해 실험까지 진행했다.

## 1. HNCS 메커니즘 - 가장 중요한 발견

**출처**: `hasselblad-hncs-color-science-explained` (블로그, 2026-07-18) +
Luminous Landscape 포럼 스레드.

### 1-1. 렌더타임 파이프라인, 캡처타임 아님

HNCS는 RAW 파일에 구워지지 않는다. 3FR은 순수 센서 데이터고, HNCS는
Phocus가 파일을 **열 때마다** 매번 다시 실행하는 렌더 파이프라인이다.
화이트밸런스를 바꾸면 Phocus는 색상 매트릭스+chroma LUT 선택부터
다시 하고 전체 렌더를 처음부터 다시 돌린다 - 이게 Lightroom/Capture
One에서 같은 켈빈 값을 나중에 적용해도 Phocus와 다른 색이 나오는
이유다(둘 다 "이미 디코드된 이미지에 곱셈 계수만 얹는" 방식인데
Phocus는 아예 다른 매트릭스를 고른다).

**우리 프로젝트와의 관계**: 이건 `hybrid_engine/research/hncs_structural.py`가
처음부터 전제하고 있던 구조(조명별 매트릭스 → 조명별 chroma LUT →
공유 필름커브)와 정확히 일치한다. 즉 이번 세션 초반에 세운 "HNCS
실제 4단계 구조" 가설 자체는 외부 소스로 재확인됐다.

### 1-2. 조명 개수: 최소 4개, 우리는 2개로 근사

포럼 스레드가 제시하는 구체적 숫자: **Tungsten(~2950K), Low
Tungsten(~2100K), Flash(~5650K), Flash-Daylight** - 최소 4개 광원,
각각 고유 3x3 매트릭스. 색보정 LUT(chroma correction table)는
Tungsten/Flash 2개에만 존재하고(Low-Tungsten/Flash-Daylight는 "너무
비슷해서" 별도 LUT 없음), 각 LUT는 "Standard"(펀치 있는 주관적 톤)와
"Reproduction"(정확도 위주) 2가지 변형이 있다.

화이트밸런스 값 기준으로 매트릭스+LUT를 자동 선택하고 **중간값은
블렌딩**한다 - Lightroom의 dual-illuminant DCP와 같은 방식(광원 개수만
더 많음).

**우리 프로젝트와의 관계**: `hncs_structural.py`의 하드-클러스터
모델은 AsShotNeutral R/B 비율 임계값 0.9로 딱 2개 클러스터를 하드
분류한다 - "4개 조명" 대신 "2개", "블렌딩" 대신 "하드 분류"로 이중
단순화한 셈이다. 이 세션에서 후자(블렌딩 vs 하드분류)를 직접
검증했는데(아래 3절), 우리 13쌍 데이터에서는 블렌딩이 하드분류를
이기지 못했다 - 표본 크기 때문에 전자(2개 vs 4개)는 아예 시도하지도
못했다.

### 1-3. 프리셋(Standard/Nature/Portrait/Product/Square Crop)은 색과 무관

**출처**: `what-phocus-writes-to-phos-hncs-presets` (블로그, 2026-05-05,
`.phos` 사이드카 파일을 직접 diff해서 실측).

프리셋 간 차이는 **샤프닝 파라미터(USMAmount/USMRadius/USMNoiseLimit)와
톤커브(Gradations)뿐**이다. Brightness/Contrast/Saturation은 5개
프리셋 전부 동일값(0/0/0), 별도 색 매트릭스도 파일 포맷에서 못 찾았다고
저자가 명시. Nature의 "더 생생해 보이는" 인상은 S자 톤커브(그림자
압축, 하이라이트 리프트) + 샤프닝 180(Standard 대비 1.8배) 때문이지
채도 조작이 아니다.

**우리 프로젝트와의 관계**: 이건 우리 실험 설계가 이미 옳게 가정하고
있던 부분을 재확인해준다 - `apply_hncs()`나 구조 실험 모두 "프리셋"
개념 자체를 모델링하지 않고 단일 렌더 파이프라인만 다루는데, 이게
맞는 스코프였다는 뜻(프리셋은 색과학 레이어가 아니라 그 위에 얹는
후처리 레이어).

## 2. Phocus vs Capture One vs Lightroom 실측 비교

**출처**: `phocus-capture-one-lightroom-raw-color-test` (블로그, 데이터
페이지) + `phocus-capture-one-lightroom-hasselblad-measured` (같은
데이터의 서술형 버전). 인쇄 컬러차트 + ISO 사다리, X2D II 100C, 3개
앱 기본값으로 렌더 후 CIELAB(D65, Bradford) 측정, 어도베 검증
파이프라인(round-trip 오차 0.007 L*)까지 거친 결과.

| 비교 | 톤(밝기) | 색 |
|---|---|---|
| Capture One vs Phocus | 전 ISO에서 일관되게 5.4~6.8 L* 더 어두움(~0.4~0.5스톱) | 파란색 채도 +18.9~+27.7 C*(가장 큰 차이), 시안이 파랑쪽으로 11~17도 회전 |
| Lightroom vs Phocus | ISO 800까지 거의 일치, 고감도에서 밝아짐(ISO 12800 +6.7 L*) | 노랑~시안 파스텔 채도 -4~-9 C*, 하이라이트가 더 차가움(b* -6~-7) |

전체 ΔE00 중앙값: Capture One 4.0, Lightroom 2.4(지각 임계값
1.0~2.3 근처).

**중요한 한계(저자 스스로 명시)**: "셋 중 뭐가 정확한가"는 이 데이터로
답할 수 없다 - 실제 장면이 아니라 잉크젯 인쇄 차트를 촬영한 것이라
잉크 반사 스펙트럼이 실제 피사체와 다르게 각 앱의 프로파일과
상호작용할 수 있다. 방향성은 신뢰할 만하지만 정확한 수치를 실제
장면(하늘, 물 등)에 그대로 적용하면 안 된다고 명시.

**렌즈 보정 차이**(같은 저자, 코너 폴오프 실측): Lightroom +23.1 L*,
Capture One(기본 Light Falloff=100) +20.9 L*, **Phocus는 +8.1
L*뿐** - 두 서드파티 앱은 비네팅을 거의 완전히 펴는데 Phocus는 약
1/3만 보정하고 렌즈의 자연스러운 코너 어두움을 남긴다.

**우리 프로젝트와의 관계**: 코너 폴오프 결과는 이 프로젝트가 이미
`brands/hasselblad.py` docstring에 적어둔 HNCS 철학("눈은 대비를
강화해서 본다 → 약한 마이크로 콘트라스트", "렌즈의 자연스러운 특성을
존중")과 독립적으로 일치하는 실측 확인이다.

## 3. 우리 내부 실험 3건과의 교차 대조

이번 세션에서 실행한 3개 실험을 외부 문서가 시사하는 구조와 나란히
놓고 정리한다. 셋 다 통계적으로 정직한 방법론(LOO 교차검증 + 부호검정
+ 부트스트랩 CI + drop-one 민감도, `hybrid_engine/EVALUATION.md`에
전부 기록)을 썼고, **셋 다 "판정 보류" 또는 "무신호"로 끝났다** - 이건
우연이 아니라 13쌍이라는 표본 크기의 근본적 한계일 가능성이 높다.

### 3-1. 하드-클러스터 구조 실험 (외부 문서 조사 이전에 실행)

`apply_hncs()`의 3단계 단순화를 실제 HNCS의 4단계(매트릭스→chroma
LUT→필름커브, 조명별로 앞 2단계 분기)로 미러링한 첫 시도. AsShotNeutral
R/B 비율로 2-클러스터 하드 분류. 결과: 평균 ΔE 4.1% 개선처럼
보였지만 부트스트랩 95% CI가 [-15.8%, +22.9%]로 0을 넉넉히 포함,
부호검정 p=1.000(6승 7패) - **판정 보류**.

### 3-2. 색수차 보정 실험

디코드 단계(rawpy `chromatic_aberration` 파라미터) 자체를 처음
건드린 실험. 13쌍 LOO에서 **13개 폴드 전부**가 독립적으로 "보정
없음"을 최적으로 선택 - 완전히 평평한 null(부호검정 p=1.000, CI
[0.000, 0.000]). 최종 리뷰가 포지티브 컨트롤로 파라미터 자체는
실제로 작동함을 확인(94% 픽셀 변화) - 즉 "안 먹혀서" 무신호가 아니라
"먹히긴 하는데 도움이 안 돼서" 무신호.

**외부 문서와의 연결**: `capture-one-hasselblad-raw-support`가
Capture One의 XCD 렌즈 보정 프로파일이 "초점거리 정보가 3FR에 없어서
항상 기본 보정만 적용된다"고 명시한 부분과 맞아떨어진다 - 진짜 렌즈
색수차 보정은 초점거리별로 달라야 정확한데, 우리도 C1도 전역 스칼라
하나(또는 초점거리 무관 기본 프로파일)로는 유의미한 신호를 못 잡는다는
방증. 이 관찰은 색수차 실험의 EVALUATION.md 기록에 아직 반영 안
됨 - 다음 섹션에서 후속 조치로 제안.

### 3-3. 조명 블렌딩 실험 (외부 문서 조사 직후 실행)

포럼 스레드의 "4개 조명 + 블렌딩" 힌트를 받아, 표본 제약상 앵커
2개는 유지하되 **하드 분류 대신 연속 블렌딩**으로 바꾸면 개선되는지
검증. R/B 선형, CCT/mired 두 가중치 공식 각각 LOO. 결과: 둘 다
하드-클러스터보다 근소하게 나쁨(RB -1.6%, CCT -1.4%), 둘 다 CI가
0을 포함 - **판정 보류**, 서로 간 비교도 판정 보류.

최종 리뷰가 전체 실험을 처음부터 재실행해서 모든 수치를 비트 단위로
재현했고, 가중 최소자승 피팅이 정말로 13쌍 전부를 올바르게 쓰는지도
직접 계측 검증함 - "구현이 잘못돼서 무신호"가 아니라 진짜 무신호임을
확인.

## 4. 종합 결론

**외부 문서가 강하게 시사하는 구조(조명별 매트릭스+LUT의 연속
블렌딩, 최소 4개 조명)는 우리 13쌍 데이터로는 재현/검증되지
않았다.** 세 실험 모두 방법론상 결함이 아니라(최종 리뷰가 매번
독립 재검증함) 표본 부족으로 수렴한다:

- **표본 자체가 작다**: 13쌍, 그마저 조명 클러스터 분포가
  불균등(cluster_a 10쌍, cluster_b 3쌍) - 4개 조명으로 쪼개면 조명당
  2~4장 수준이라 애초에 시도할 수 없었다.
- **타깃이 진짜 HNCS 출력이 아니다**: 이 프로젝트의 모든 실험은
  "카메라 내장 JPEG에 얼마나 가까운가"를 재는 것이지 "Phocus의
  실제 HNCS 렌더에 얼마나 가까운가"가 아니다(카메라 JPEG도 어떤
  렌더 파이프라인을 거치지만 Phocus의 HNCS와 동일하다는 보장이
  없음 - `hncs_structural.py` docstring에 이미 명시된 한계).
- **색수차 실험의 "전역 스칼라로는 무의미"라는 결과는 외부 문서(C1의
  초점거리 정보 부재 고백)와 독립적으로 같은 방향을 가리킨다** - 이건
  우연의 일치라기보다 "카메라 RAW에 없는 정보(초점거리, 조명 종류의
  정확한 개수)로는 정밀한 렌더타임 보정을 재현하기 어렵다"는 더 일반적인
  패턴일 수 있다.

## 5. 후속 조치 제안 (이 문서 밖, 별도 논의 필요)

1. `hybrid_engine/EVALUATION.md`의 "색수차 보정 실험" 절 한계 항목에
   Capture One의 초점거리-미지원 고백을 한 줄 추가할지(사소한 문서
   보강, 즉시 가능).
2. GitHub 이슈 #4에 실사진(차트 아닌) X2D II raw+jpeg 페어 기여를
   재요청할지 - kmichels 기여자의 블로그에 이미 실사진 프레임(XCD
   90V, ISO 12800)이 존재한다고 언급됨. 이게 되면 표본이 늘어나
   4-조명 모델이나 세대 간 pooling 재검증(이슈 #4 3번 지적) 둘 다
   가능해짐.
3. 이 세 실험(하드클러스터/색수차/조명블렌딩) 모두 "판정 보류"로
   수렴한 지금, 같은 13쌍으로 더 파라메트릭 방향을 시도하는 건
   수확체감 구간에 들어섰다고 봄 - 다음 각도는 표본을 늘리거나,
   완전히 다른 종류의 데이터(예: 실제 Phocus HDR TIFF 출력을 타깃으로
   삼아 "진짜 HNCS"에 대한 ΔE를 재는 것)로 가는 게 나을 수 있음.

## 6. Phocus 4.1.1 앱 번들 1차 실측 (2026-08-03)

위 5-3에서 제안한 "완전히 다른 종류의 데이터" 방향을 렌더 결과물이
아니라 **Phocus 앱 자체**로 시도해본 기록. 이 절의 출처는 블로그/포럼이
아니라 실제 설치한 Phocus 4.1.1(`brew install --cask phocus`) 바이너리
자체이므로, 이 문서의 다른 절보다 근거 등급이 다르다(1차 소스) - 단,
방법을 정적 리소스 파일 열람과 `strings`/`otool -L`으로만 제한했다
(디스어셈블/디컴파일은 라이선스 경계를 이유로 하지 않음). 그래서
"구조가 존재한다"는 확인은 되지만 실제 매트릭스/LUT 숫자값은 얻지
못했다 - 아래 6-2의 한계 그대로.

### 6-1. ICC 프로파일 = HNCS 룩과 무관 (음성 결과)

`Contents/Frameworks/HBImageProcessing.framework/Versions/A/Resources/Profiles/`에
번들된 8개 `.icc`(`Hasselblad RGB`, `HasselbladLStarRGB`/`v1`,
`Hasselblad Rec709`, `Hasselblad Rec2100PQ`, `Hasselblad Lab`,
`Hasselblad Gray`, 필름스캔용 `330Skel 30K75`/`350Skel 30K90`)를 raw
바이너리 태그(`wtpt`/`rTRC`/`rXYZ` 등)까지 직접 파싱했다. 결과:

- `Hasselblad RGB.icc`: 순수 감마 2.1992, wtpt≈D50(0.964, 1.0, 0.825)
- `Hasselblad Rec709.icc`: 순수 감마 1.9609, wtpt≈D65
- `HasselbladLStarRGB(v1).icc`: TRC가 700점 LUT(CIE L* 곡선과 일치하는
  형태) - ProPhoto의 L* 변형과 같은 컨셉

전부 **범용 컬러매니지먼트 워킹스페이스**(ProPhoto RGB류) 정의이지,
"이 사진을 이렇게 톤/색으로 그려라"는 HNCS 룩 자체가 아니다.
`Settings/Standard/Standard.xml`(기본 프리셋)도 확인해보니
`ColorCorr` 배열이 전부 0 - 프리셋 자체는 중립 조정값만 담고 있고
베이스 룩은 여기 없다(1-3절의 "프리셋은 색과 무관, 샤프닝+톤커브뿐"
결론과 일치 - 프리셋 XML에 색 로직이 없는 이유가 애초에 그게 있을
자리가 아니었기 때문이라는 게 이번에 더 명확해짐).

### 6-2. 바이너리 strings 조사 - 1-2절의 "광원별 매트릭스+LUT" 구조를 직접 확인

`HBRawCorrections.framework`(1.2MB)에 `strings -a` + 관련 포맷 문자열을
뒤진 결과, 다음 심볼/포맷 문자열 이름이 나왔다(디버그/코드덤프용
`%s`/`%.1ff` 템플릿으로 보임 - 실제 카메라별 숫자값은 컴파일된 데이터
섹션에 있어 텍스트로 안 잡힘):

```
kMatrixFlash, kMatrixTungsten, kMatrixLowTungsten          # 조명별 3x3 매트릭스
kLUTTableFlashCb/Cr, kLUTTableTungstenCb/Cr                # 조명별 Cb/Cr 크로마 LUT
kColorTempFlash, kColorTempTungsten, kColorTempLowTungsten # 조명별 색온도 상수
kNeutralVector                                             # (조명별로 보이는) 중립점 벡터
```

**1-2절과의 대조**: 포럼 스레드는 "Tungsten/Low-Tungsten/Flash/
Flash-Daylight 4광원, 각각 고유 매트릭스, 크로마 LUT는 Tungsten/Flash
2개에만 존재(Low-Tungsten/Flash-Daylight는 LUT 없음)"이라고 주장했다.
이번 실측에서 나온 심볼이 정확히 **매트릭스는 Flash/Tungsten/
LowTungsten 3개, LUT는 Flash/Tungsten 2개뿐**(LowTungsten용
`kLUTTableLowTungsten*`은 없음) - LUT가 있는 조명이 정확히 어느
것들인지까지 블로그/포럼의 주장과 구조적으로 일치한다. `strings`
결과에서 4번째 광원(Daylight/Flash-Daylight)에 해당하는 별도 이름은
못 찾았다 - 접미사 없는 "기본값"으로 존재하거나, 다른 이름 규칙을
쓰거나, 문자열 추출 한계일 수 있음(미확인).

**한계**: 위 이름들은 전부 소스코드 심볼/디버그 포맷 문자열이지 실제
데이터가 아니다 - 실제 3x3 매트릭스 9개 float, LUT 테이블 값은
바이너리 데이터 섹션의 특정 주소에 있고 이걸 읽으려면 심볼이 어느
주소를 가리키는지부터 알아야 해서(디스어셈블 필요) 이번 조사
범위(strings/otool만) 밖이다. 사용자와 상의해 여기서 멈췄다 -
Phocus EULA의 리버스엔지니어링 금지 조항을 넘어서는 작업이라고
판단했기 때문.

### 6-3. 우리 프로젝트와의 관계

`apply_hncs()`(v11)는 여전히 조명 매트릭스 없이 **단일 파라메트릭
톤+채도 커브**다 - 이번 실측으로 "실제 HNCS가 조명별 매트릭스+
크로마LUT 구조를 갖고 있다"는 1-2절의 외부 주장이 (블로그 저자의
추론이 아니라) 실제 배포된 바이너리의 내부 명명으로 한 번 더
뒷받침됐다. 다만 이게 `apply_hncs()`를 바꿔야 한다는 뜻은 아니다 -
숫자값이 없으니 이 구조를 모사할 근거 자체가 없고, 설령 있어도
raw_calib_cache 13쌍에 촬영 광원(색온도) 라벨이 없어 조명별로 나눠
검증할 수도 없다(이 자체가 후속 조치 후보 - 이 문서 스코프 밖).

(같은 세션 후속: 조명별 분해는 아니지만, raw_calib_cache 13쌍 전부를
실제 Phocus로 Import/Export해서 apply_hncs()를 카메라 JPEG뿐 아니라
**진짜 Phocus 렌더와도** 직접 대조하는 실측은 진행했다 -
`docs/measurements.md` "Phocus 실제 렌더 대조 (2026-08, 최초)" 절.)

## 7. 참고 문서 목록

**직접 인용/심층 분석**:
- Konrad Michels, "How HNCS Actually Works: Hasselblad's Color Science
  Explained", blog.tonalphoto.com, 2026-07-18
- Konrad Michels, "Phocus, Capture One, or Lightroom for Hasselblad?
  Measured" + 데이터 페이지("How Phocus, Capture One, and Lightroom
  Render Hasselblad RAW Files"), blog.tonalphoto.com, 2026-07-18
- Konrad Michels, "What Phocus Writes to the .phos When You Switch
  HNCS Presets", blog.tonalphoto.com, 2026-05-05
- Luminous Landscape Forums, "Hasselblad Natural Color Solution
  (HNCS) - how it works (probably)" (forum.luminous-landscape.com,
  topic 96679)
- Hasselblad Phocus 4.1.1 앱 번들 (Homebrew cask `phocus`, 2026-08-03
  설치) - 정적 리소스 파일(`.icc`, `.xml`, `Targets/*.txt`) 열람 +
  `HBRawCorrections.framework`/`HBImageProcessing.framework`에
  `strings -a`/`otool -L`만 적용(디스어셈블/디컴파일 없음). 1차 소스,
  6절 참고.

**훑어봤으나 색과학과 직접 관련 없음(UI/워크플로우/HDR 별도 파이프라인)**:
- "Phocus Histogram vs Capture One Levels" (2026-01-10)
- "A Complete Hasselblad RAW Workflow" (2026-07-18)
- "Capture One's Hasselblad Support: What You Get and What Stays in
  Phocus" (2026-07-02)
- "What You Keep and Lose When You Skip Phocus" (2026-07-18)
- "Cull Hasselblad Shoot Fast Before Phocus", "Phocus Thumbnail
  Options Menu", "Phocus Crop Tool Grid Options" (워크플로우/UI)
- HDR 5부작("HNCS HDR", "Output Formats Trilemma", "Phocus 4.x HDR
  Workflow", "HDR Display Requirements", "HDR Print & Archival
  Recommendations") - HNCS와 별개 파이프라인(gain-map 인코딩 추가
  레이어)이라 이 문서의 스코프 밖.
