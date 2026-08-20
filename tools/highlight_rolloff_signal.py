"""
population-fit 브랜드들이 전부 검증 없이 차용 중인 shoulder_start/
clahe_clip을 브랜드별로 다르게 추정할 수 있는지 탐색한 1회성 분석
스크립트. datasets/<brand>/joint_distribution.npz의 population 풀링
L 히스토그램에서 "하이라이트가 얼마나 완만하게 rolloff되는지"를 재는
지표(90th~99.5th percentile L값 폭, 250~255 구간 클리핑 비율)를 계산해서
브랜드별로 비교한다.

결론(2026-07): 브랜드 간 지표 값 자체는 꽤 벌어짐(rolloff_width 35~64)
- 하지만 이 값이 실제 shoulder_start 차이를 반영하는지, 아니면 브랜드마다
따로 스크레이핑한 20~25장의 촬영자별 장면 선택/노출 편향인지 구분할 근거가
없다. 검증 가능한 "진짜 정답값"이 핫셀블라드(shoulder_start=0.78, raw+jpeg
그리드서치로 확정) 하나뿐이라 지표->shoulder_start 매핑 함수를 만들
표본이 안 됨(점 하나로 회귀선을 그릴 수 없음). 그래서 이 지표로 각
브랜드의 shoulder_start/clahe_clip 기본값을 바꾸는 액션은 취하지 않았다 -
population 풀링 히스토그램만으로는 카메라의 실제 하이라이트 렌더링
곡선을 raw 기준선 없이 분리해낼 수 없다는 게 이번 탐색의 결론(raw+jpeg
페어 소스 부재 문제와 같은 근본 한계로 귀결).

  python3 -m tools.highlight_rolloff_signal
"""
import numpy as np

BRANDS = ["hasselblad", "leica", "phaseone", "pentax", "ricoh_gr",
          "canon", "sony", "nikon", "panasonic", "olympus"]


def rolloff_stats(brand):
    d = np.load(f"datasets/{brand}/joint_distribution.npz")
    l_hist = d["l_hist"].astype(np.float64)
    l_hist /= l_hist.sum()
    cdf = np.cumsum(l_hist)
    p90 = int(np.searchsorted(cdf, 0.90))
    p995 = int(np.searchsorted(cdf, 0.995))
    return dict(p90=p90, p995=p995, rolloff_width=p995 - p90,
                clip_frac=float(l_hist[250:].sum()))


def run():
    print(f"{'브랜드':12s} {'p90':>5s} {'p99.5':>6s} {'rolloff_width':>14s} {'clip_frac(250-255)':>20s}")
    for b in BRANDS:
        try:
            st = rolloff_stats(b)
        except FileNotFoundError:
            print(f"{b:12s} 데이터 없음")
            continue
        print(f"{b:12s} {st['p90']:5d} {st['p995']:6d} {st['rolloff_width']:14d} {st['clip_frac']*100:19.2f}%")
    print("\n핫셀블라드(shoulder_start=0.78, 실측 확정값)의 rolloff_width/clip_frac을 "
          "다른 브랜드와 비교는 할 수 있지만, 정답값이 하나뿐이라 지표->shoulder_start "
          "매핑은 만들 수 없음 - 이 브랜드들의 shoulder_start/clahe_clip 기본값은 "
          "바꾸지 않는다(모듈 docstring 참고).")


if __name__ == "__main__":
    run()
