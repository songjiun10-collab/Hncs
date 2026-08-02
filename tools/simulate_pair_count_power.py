"""표본 크기 확대 시뮬레이션 - "60쌍이 있었다면 결과가 어땠을까"를
**실제 새 데이터 없이** 부트스트랩으로 투영한다.

  python3 -m tools.simulate_pair_count_power

**이건 실제 실험이 아니다.** 지금 가진 13쌍의 실측 페어드 차이
(13개 값)의 경험분포에서 복원추출로 n_target개(기본 60개)를 뽑아
그 표본의 유의성 검정 결과를 낸다 - 13개에 없는 새 정보를 만들어내지
않는다. "잡음 수준이 지금과 똑같이 유지된 채 표본만 커지면 신뢰구간이
얼마나 좁아지는가"를 보여주는 통계적 투영이지, "실제로 60쌍을 모으면
이런 결과가 나온다"는 예측이 아니다 - 진짜 60쌍은 잡음 수준 자체가
다를 수 있다(예: 조명 분포가 더 다양해지거나, 카메라 세대가 섞이거나).

세 비교 각각에 대해 실행: (1) HNCS 구조 실험 vs apply_hncs(), (2) 조명
블렌딩(R/B) vs 하드클러스터, (3) 조명 블렌딩(CCT) vs 하드클러스터.
페어드 차이 원자료는 hybrid_engine/EVALUATION.md에 이미 기록된 값을
그대로 하드코딩했다(재실행 없이 검증 가능하도록) - 각주에 출처 명시.
"""
import math

import numpy as np

# hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절 "폴드별 상세" 표.
# diff = apply_hncs - structural (양수 = apply_hncs가 그 폴드에서 더 나쁨)
_STRUCTURAL_VS_APPLY_HNCS_DIFFS = [
    9.961 - 10.787, 13.449 - 5.249, 9.128 - 14.223, 18.334 - 18.412,
    9.395 - 13.194, 9.246 - 8.342, 8.245 - 4.729, 14.976 - 10.126,
    11.645 - 11.055, 5.478 - 6.452, 8.610 - 11.726, 9.636 - 13.074,
    10.073 - 5.115,
]

# hybrid_engine/EVALUATION.md "HNCS 조명 블렌딩 실험" 절, RB 표.
# diff = hard_cluster - blend (양수 = 블렌딩이 그 폴드에서 더 나음)
_RB_BLEND_VS_HARD_DIFFS = [
    10.787 - 10.871, 5.249 - 8.750, 14.223 - 13.882, 18.412 - 18.424,
    13.194 - 12.614, 8.342 - 9.324, 4.729 - 4.641, 10.126 - 10.002,
    11.055 - 10.552, 6.452 - 7.007, 11.726 - 10.423, 13.074 - 12.505,
    5.115 - 5.572,
]

# 같은 절, CCT 표.
_CCT_BLEND_VS_HARD_DIFFS = [
    10.787 - 10.668, 5.249 - 8.889, 14.223 - 13.981, 18.412 - 18.502,
    13.194 - 12.371, 8.342 - 9.421, 4.729 - 4.663, 10.126 - 10.023,
    11.055 - 10.585, 6.452 - 6.943, 11.726 - 10.269, 13.074 - 12.307,
    5.115 - 5.698,
]

COMPARISONS = {
    "HNCS 구조 실험 vs apply_hncs()": _STRUCTURAL_VS_APPLY_HNCS_DIFFS,
    "조명 블렌딩(RB) vs 하드클러스터": _RB_BLEND_VS_HARD_DIFFS,
    "조명 블렌딩(CCT) vs 하드클러스터": _CCT_BLEND_VS_HARD_DIFFS,
}


def _sign_test_p(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def bootstrap_power_at_n(observed_diffs, n_target, n_bootstrap=20000, seed=0):
    """observed_diffs(길이 13)의 경험분포에서 복원추출로 n_target개씩
    n_bootstrap번 뽑아, 각 표본의 부호검정 p<0.05 비율과 정규근사 95%
    CI가 0을 배제하는 비율을 낸다. 둘 다 "0이 아닌 방향으로 유의미한
    결과가 나올 확률"의 서로 다른 추정치 - 부호검정은 분포 모양에
    민감하지 않고, CI 쪽은 표준오차 기반이라 더 통상적인 보고 형식이다."""
    observed = np.asarray(observed_diffs, dtype=np.float64)
    rng = np.random.default_rng(seed)
    sign_sig, ci_excludes_zero = 0, 0
    for _ in range(n_bootstrap):
        sample = rng.choice(observed, size=n_target, replace=True)
        wins = int((sample > 0).sum())
        losses = int((sample < 0).sum())
        if _sign_test_p(wins, losses) < 0.05:
            sign_sig += 1
        mean = sample.mean()
        sd = sample.std(ddof=1)
        se = sd / math.sqrt(n_target)
        ci_lo, ci_hi = mean - 1.96 * se, mean + 1.96 * se
        if ci_lo > 0.0 or ci_hi < 0.0:
            ci_excludes_zero += 1
    return {
        "n_target": n_target,
        "observed_mean": float(observed.mean()),
        "observed_sd": float(observed.std(ddof=1)),
        "sign_test_significant_rate": sign_sig / n_bootstrap,
        "ci_excludes_zero_rate": ci_excludes_zero / n_bootstrap,
    }


def main(n_target=60):
    print(f"부트스트랩 표본 확대 시뮬레이션 (목표 n={n_target}, 실제 새 데이터 없음)")
    print("=" * 70)
    for label, diffs in COMPARISONS.items():
        r = bootstrap_power_at_n(diffs, n_target)
        print(f"\n[{label}] (실측 n=13: 평균 {r['observed_mean']:+.3f}, sd {r['observed_sd']:.3f})")
        print(f"  n={n_target}로 복원추출 시뮬레이션 시:")
        print(f"    부호검정 p<0.05 나올 확률: {r['sign_test_significant_rate']:.1%}")
        print(f"    95% CI가 0을 배제할 확률: {r['ci_excludes_zero_rate']:.1%}")


if __name__ == "__main__":
    main()
