# HNCS 구조 리서치: 실제 파이프라인 vs `apply_hncs()`

*[English](hncs_structural_research.en.md)*

[메인 README](../README.md)로 돌아가기.

`brands/hasselblad.py`의 `apply_hncs()`(⭐ Stable, 실사용 중)는 실제
HNCS 파이프라인을 3단계로 단순화한 근사다. 이 문서는 실제 구조를
출처와 함께 정리하고, 그 구조를 반영한 별도의 **연구용** 실험 모듈
(`hybrid_engine/research/hncs_structural.py`)이 실제로 정확도를
개선하는지 측정한 결과를 담는다. `apply_hncs()` 자체는 이 리서치로
수정되지 않는다 - 설계 근거는
[2026-07-28-hncs-structural-research-design.md](superpowers/specs/2026-07-28-hncs-structural-research-design.md).

## 출처

- Hasselblad 공식 사이트: hasselblad.com/learn/hasselblad-natural-colour-solution
  - "필름커브 톤, 지각보상 대비, rich saturation 무조작, 스킨톤
    hue/채도 무조작, X시스템 전체 일관 적용" 5개 설계 원칙을 공개.
    **파이프라인의 정확한 단계 수/구현 방식은 공개하지 않음.**
- blog.tonalphoto.com, "How HNCS Actually Works" - Phocus `.phos`
  사이드카를 바이트 단위로 diff한 독립 기술 분석. 저자 본인이 글
  안에서 "공식 지원/가이드가 아니라 개인적 조사와 테스트"라고 명시.
  **공식 화이트페이퍼는 존재하지 않는다** - 검색으로 확인.
- "최소 4개 조명(Tungsten/Low Tungsten/Flash/Flash-Daylight)"이라는
  구체적 개수는 위 블로그 글이 다시 인용한 Luminous Landscape 포럼의
  커뮤니티 기술 분석 출처 - Hasselblad가 공개한 숫자가 아니다.

세 출처의 확실성 등급이 다르다: 공식 사이트(설계 원칙, 공식) >
tonalphoto.com(`.phos` 바이트 diff, 비공식이지만 직접 실측) >
Luminous Landscape 포럼 인용(비공식, 재인용).

## 구조 대비

| 단계 | `apply_hncs()` (Stable, 실사용) | 실제 HNCS (조사 결과) |
|---|---|---|
| 입력 | RAW를 이미 카메라 JPEG로 디코드한 8비트 BGR | RAW 센서 데이터 (16비트) |
| 1 | 전역 노출 리프트 (`exposure_gamma` LUT, v10 추가) | 조명별(illuminant-specific) 3x3 컬러 매트릭스 - 최소 4종 중 WB 설정에 따라 선택 |
| 2 | CLAHE (지각보상 대비, 사진 모드만 - 비디오는 생략) | 그 매트릭스와 짝지어진 chroma LUT (해당 광원에 맞춘 hue/채도 보정) |
| 3 | `film_curve` LUT (toe/mid/shoulder 톤커브) | Hasselblad Film Curve (하이라이트 롤오프 + 섀도우 전환) |
| 화이트밸런스 변경 시 | 영향 없음 (JPEG 입력이라 WB는 이미 반영된 상태) | 2단계부터 전체 재실행 (매트릭스+LUT가 조명에 종속) |
| hue/채도 조작 | 없음 (원칙 그대로 무조작) | 있음 - 다만 **프리셋 간에는** 없음(아래 참고) |

**단순화의 핵심**: `apply_hncs()`가 근거로 삼은 "스킨톤 hue/채도 무조작"
원칙은 프리셋(Standard/Nature/Portrait/Product/Square Crop) 비교에서는
맞다 - `.phos` 사이드카 직접 비교 결과 Brightness/Contrast/Saturation이
5개 프리셋 전부 0/0/0으로 동일했다. 하지만 그건 "프리셋끼리 색과학을
안 바꾼다"는 뜻이지 "파이프라인 전체에 채도 보정이 없다"는 뜻이
아니었다 - 2단계(조명별 chroma LUT)는 프리셋과 무관하게 항상 존재하는
별도 단계다.

## 실험: 구조를 더 정확히 따라가면 ΔE가 좋아지는가

`hybrid_engine/research/hncs_structural.py`가 위 4단계를 미러링한다
(RAW 기반, WB 적용 -> 클러스터별 3x3 매트릭스 -> 클러스터별 chroma LUT
-> 공유 필름커브). 표본(13쌍의 raw+jpeg 페어,
`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`)이 "최소 4개 조명"을
뒷받침하지 못해 `AsShotNeutral`의 R/B 비율 기반 2-클러스터
(`cluster_a`/`cluster_b`, 임계값 0.9)로 축소했다 - 10 대 3의 뚜렷한
분리가 있어 시도할 근거는 있지만, 소수 클러스터가 3쌍뿐이라 통계적으로
얇다.

leave-one-out 교차검증(13회, 매회 1쌍을 held-out으로 빼고 나머지로
피팅)으로 이 실험 모듈과 `apply_hncs()`(같은 raw 기반 baseline에
적용, 공정 비교) 양쪽의 ΔE(CIEDE2000)를 같은 13쌍에 대해 재측정했다.

**결과**: 구조 실험(`apply_hncs_structural`)이 평균 ΔE 10.191로
`apply_hncs()`의 10.629보다 4.1% 낮았다(13쌍 중 8쌍에서 우세, 5쌍에서
열세) - 실재하지만 근소한 효과다.

| 방법 | 평균 ΔE (CIEDE2000) |
|---|---|
| `apply_hncs()` (raw 기반 baseline에 적용, 이 실험 안에서 재측정) | 10.629 |
| 구조 실험 (`apply_hncs_structural`, 클러스터별 매트릭스+chroma LUT+공유 필름커브) | 10.191 |

자세한 방법론과 한계는 hybrid_engine/EVALUATION.md의 "HNCS 구조 실험" 절 참고.

## 한계

- **Phocus의 실제 매트릭스/LUT 값과 다르다** - 우리가 가진 13쌍짜리
  raw+jpeg 페어로 새로 피팅한 근사치. Hasselblad의 비공개 자산을
  재현한 게 아니다.
- **조사 출처가 비공식이다** - 위 "출처" 절 참고. 확실성 등급이 다른
  정보가 섞여 있다.
- **2-클러스터는 실제 구조(4개 이상)의 축소판** - 표본 부족으로 인한
  타협이지 "2개가 맞다"는 주장이 아니다.
- **표본 13쌍, 클러스터당 3~10쌍(소수 클러스터 3쌍)** - 통계적으로
  매우 얇음. 교차검증 결과가 양수든 음수든 표본이 늘어나면 재확인이
  필요하다.
- **`apply_hncs()`를 대체하지 않는다** - 이 실험이 이겨도 이 스펙
  범위에서는 Stable로 승격하지 않는다(별도 논의).
