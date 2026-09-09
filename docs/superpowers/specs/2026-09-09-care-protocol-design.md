# CARE: Counterfactual Appearance Response Evaluation

[English](2026-09-09-care-protocol-design.en.md)

상태: HNCS용 신규 연구 방법론 제안. 아직 runner 구현 및 실험 결과 없음.
이름과 계약은 이 프로젝트의 제안이며 기존 학술 표준이라는 주장이 아니다.

## 질문과 역할

같은 입력 장면에 통제된 변화를 주었을 때 appearance 구현이 어떻게 반응하고,
어디에서 불연속·정보 손실·과도한 민감도를 보이는지 측정한다.
NARE가 제조사 target 재현을 검증하는 동안 CARE는 구현의 반응 특성을 진단한다.
ColorChecker 색도학 정확도나 NARE appearance 일치도를 대체하지 않는다.

SOOC 없는 로컬 RAW도 입력으로 사용할 수 있다. 공통 입력에 12개 브랜드 함수를
적용하면 12개 구현을 시험할 수 있지만, 이를 12개 제조사 센서/카메라 실측이라고
부르지 않는다. 입력 카메라와 출력 look은 별도 축이며 미관측 카메라는 미관측으로 남긴다.

## 실험 단위

원본 RAW의 hash로 capture를 식별하고 장면 그룹을 검토한다. 원본과 모든 파생본은
같은 split에 둔다. 파생본 100개는 독립 표본 100개가 아니다. scene 미검토 상태에서는
capture별 기술통계만 보고하고 CI와 일반화 주장은 보류한다.

고정 decoder에서 auto exposure/WB를 해제하고 선형 RGB float 입력 X를 만든다.
white balance, demosaic, 색공간, black/white level 및 orientation 계약을 기록한다.
노출 조작은 demosaic 이후 선형 RGB에서 수행하므로 실제 카메라 노출 변화나 센서
노이즈 변화를 재현한다는 주장을 하지 않는다. 음수/초과 범위 및 clipping 처리 정책을
고정한다. look이 uint8 입력만 받으면 최종 변환 위치와 양자화 영향을 기록한다.

## 사전 고정한 조작

첫 버전의 필수 실험은 노출과 white-balance gain이다. 공간 조작은 두 번째 단계다.

| 조작 | 제안 기본값 | 측정 목적 |
|---|---|---|
| 노출 | -2,-1,-0.5,0,+0.5,+1,+2 EV | tone 반응, 역전, clipping 변화 |
| WB gain | R/B 각각 0.9,1.0,1.1; G=1 | 채널 gain 민감도; Kelvin 변화로 해석 금지 |
| 미세 노출 | 기준 EV 주변 ±0.01 EV | 국소 점프 후보 검출 |
| 재실행 | 동일 입력/설정 3회 | 결정성 및 환경 변동 |
| 공간 조작(후속) | 50% downsample, 중앙 75% crop | scale/crop에 따른 공간 처리 의존성 |

격자는 실행 전에 고정한다. 결과를 보고 유리한 범위만 골라 요약하지 않는다.
조작은 먼저 한 축씩 수행하고 상호작용 검증으로 EV {-1,0,+1} × R/B gain
{0.9,1.0,1.1} 조합을 별도 실행한다. 조합별 원본·mask·clipping 분모를 보존한다.

## 핵심 비교

f는 명시적으로 선택한 look, B는 동일 입력 변환/양자화 경로를 쓰는 identity control이다.
T는 선형 공간의 조작, P는 실제 look 입력까지의 고정 변환이다.

Y0 = f(P(X)), Yt = f(P(T(X))).

각 조작에서 ΔE00(Yt,Y0)의 평균·중앙값·p90을 **response magnitude**로 기록한다.
이 값이 작다고 좋은 것은 아니다. 정상적인 노출/WB 변화도 출력 변화를 만들어야 한다.
공통 색공간/Lab 계약을 적용하고 chroma가 거의 없는 영역의 hue는 미정의로 취급한다.

identity control의 ΔE00(B(P(T(X))),B(P(X)))도 함께 보고한다. 두 ΔE00의 차이나
비율은 민감도 요약일 뿐 제조사 정확도·지각적 품질 점수가 아니다. control 변화가
0에 가까우면 비율은 null로 기록해 분모 발산을 막는다.

노출별 luminance, ΔL*, ΔC*, clipping fraction, 원본에서 고정한 shadow/midtone/
highlight 영역의 반응 곡선을 출력한다. 마스크를 결과 이미지마다 다시 선택하지 않는다.
입력 clipping 영향 제외 분석에는 조작 간 공통 비포화 mask를 쓰고, 전체 유효 영역
분석과 함께 보고한다. 포화가 늘어나는 조작의 결과를 조용히 누락하지 않는다.

미세 EV 반응은 양쪽 차분과 더 촘촘한 grid에서 재검사한다. uint8 identity control에서도
발생하는 양자화 계단을 look 결함으로 선언하지 않는다. luminance 역전이나 jump도
의도된 tone/local 처리 가능성이 있으므로 재현 가능한 진단 후보이며 자동 실패가 아니다.

공간 조작에서는 f(P(S(X)))와 S(f(P(X)))를 같은 좌표/해상도에서 비교한다.
비가환 잔차는 scale/crop 의존성 진단이다. 비선형 look은 원래 resampling과 교환되지
않을 수 있으므로 잔차 0을 합격 기준으로 쓰지 않는다. identity 및 고정 global-curve
control을 같이 기록한다.

## SOOC가 있는 입력과 없는 입력

SOOC가 없는 경우 반응 곡선·결정성·clipping·실행 계약만 보고한다. 원본 target J가
있는 경우에도 NARE의 원본 오차 ΔE00(f(P(X)),J)는 별도 표에 둔다. T(X)의 실제 SOOC
target이 없으면 ΔE00(f(P(T(X))),J)를 조작 후 제조사 재현 오차로 사용하지 않는다.
J에 같은 수학적 조작을 적용해 만든 이미지는 synthetic control로만 표시한다.

## 실패, 통계, 반증

각 실행은 decode failure, unsupported candidate/input, 비유한 출력, shape/channel/
dtype 계약 위반, metadata 부족 및 계산 실패를 분리한다. 흑백 look은 지원 계약을
별도 선언하고 색상 look과 같은 hue/chroma 지표로 평가하지 않는다.

scene 검토 후에만 scene별 반응 요약을 동일 가중치로 집계하고 20,000회 scene
bootstrap(seed=0)을 쓴다. session 의존성이 있으면 session cluster 분석을 추가한다.
주요 조작/지표를 사전 선택하고 나머지는 탐색 분석으로 표시한다. 여러 조작의 극값을
발견한 뒤 같은 데이터의 CI로 확인된 결함이라고 주장하지 않는다. 발견용/확인용
scene을 분리한다. 목표 반응의 외부 근거가 없으면 수치상 우승자나 종합 점수를 만들지 않는다.

실험 장치의 검증에는 identity, 고정 global curve, 상수 출력, 의도된 threshold jump,
비유한 출력, 반복 실행 변동 control을 쓴다. 상수 출력은 낮은 response ΔE00를 얻더라도
정보를 잃었음을 드러내야 한다. 낮은 민감도를 무조건 좋은 것으로 평가하는 시스템은
이 양성 대조에서 탈락한다.

## 완료 조건과 산출물

12개 look registry와 입력 카메라 분포를 각각 표시한다. 각 look마다 실행 수/실패 수,
노출·WB response curve, clipping, control 결과 및 지원하지 않는 조합을 남긴다.
원본/파생본 hash, manifest, decoder/look commit/config, perturbation 정의, 환경,
per-capture/per-scene metrics, failure log, 재실행 명령을 영속 run bundle로 보존한다.

첫 구현 수락 테스트: (1) EV=0/gain=1 control 동일성, (2) 선형 노출 배율,
(3) 파생본 split 누출 차단, (4) 상수 출력 감지, (5) threshold jump 재현,
(6) uint8 control의 양자화 분리, (7) zero denominator null,
(8) 조작별 target 부재 시 fidelity 주장 거부, (9) 미검토 scene CI 금지,
(10) input/look 카메라 coverage 구분, (11) 비유한 출력 실패 처리,
(12) 반복 실행 결과 보존. CARE 통과만으로 NARE Supported/Verified 또는 ship을 허용하지 않는다.
