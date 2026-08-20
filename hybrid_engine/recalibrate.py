"""
전체 재보정 파이프라인 - raw+jpeg 페어 디렉토리 하나로 Phase 0(3x3
raw_baseline_matrix)부터 Phase 1(tone_core)/Phase 2(color_core)까지
전부 다시 학습하고, nested 교차검증으로 현재 배포된 hasselblad.json보다
실제로 나은지 확인한 뒤에만(게이트 통과) 프로필을 갱신한다.

`calibrate_profile.py --mode raw_baseline_pipeline`이 이미 이 학습+비교
로직(run_raw_baseline_pipeline_mode)을 갖고 있지만 결과를 출력만 하고
파일에 쓰지는 않는다 - v1.2를 배포할 때 그 출력을 보고 사람이 손으로
hasselblad.json을 고쳤다(EVALUATION.md 후속 실측 6). 이 스크립트는 그
수작업을 "실행 -> 검증 -> (개선되면) 자동 반영"으로 한 번에 묶은
것이다. 이슈 #4의 X2D 실사진 페어처럼 표본이 늘어난 새 데이터셋이
생겼을 때 재보정을 반복 가능하게 만드는 게 목적.

안전장치: 교차검증 개선폭이 MIN_CV_IMPROVEMENT_PCT(기본 5%) 미만이면
--write를 줘도 파일을 안 건드린다 - 후속 실측 11~14에서 확인된 대로
이 표본 크기(raw_calib_cache 기준 13쌍)에서 나오는 몇 % 안팎의 in-sample
"개선"은 대부분 노이즈라, 명확한 개선이 아니면 조용히 프로필을 흔들지
않는 편이 안전하다.

  python3 -m hybrid_engine.recalibrate                    # dry-run, 숫자만 확인
  python3 -m hybrid_engine.recalibrate --write             # 개선되면 실제 반영
  python3 -m hybrid_engine.recalibrate --cache-dir <dir> --write   # 다른 데이터셋으로
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hybrid_engine.calibrate_profile as cp

PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "profiles", "hasselblad.json")
MIN_CV_IMPROVEMENT_PCT = 5.0


def decide_and_maybe_write(dataset, source_label, n_folds=4, n_passes=1,
                            min_improvement_pct=MIN_CV_IMPROVEMENT_PCT,
                            write=False, profile_path=PROFILE_PATH):
    """재보정 실행 + 게이트 판정 + (조건 만족 & write=True면) 저장까지
    하나로 묶은 핵심 로직 - CLI(main())와 분리해서 합성 데이터로 단위
    테스트할 수 있게 했다. 반환: 판정 결과 dict(적어도 old_loss/cv_loss/
    improvement_pct/gate_passed/written 키 포함)."""
    old_loss, in_sample_loss, cv_loss, new_params = cp.run_raw_baseline_pipeline_mode(
        dataset, n_folds=n_folds, n_passes=n_passes)

    result = {
        "old_loss": old_loss,
        "in_sample_loss": in_sample_loss,
        "cv_loss": cv_loss,
        "new_params": new_params,
        "gate_passed": False,
        "written": False,
    }
    if cv_loss is None:
        print(f"\n페어가 {n_folds}개 미만이라 교차검증을 못 함 - 안전하게 갱신 안 함")
        return result

    improvement_pct = (old_loss - cv_loss) / old_loss * 100
    result["improvement_pct"] = improvement_pct
    print(f"\n=== 게이트 판정 (기준: 교차검증 {min_improvement_pct:.1f}% 이상 개선) ===")
    print(f"기존 ΔE: {old_loss:.3f}  ->  신규 ΔE(교차검증): {cv_loss:.3f} ({improvement_pct:+.1f}%)")

    if improvement_pct < min_improvement_pct:
        print("개선폭이 기준 미달 - 프로필 갱신 안 함(후속 실측 11-14와 같은 원칙: "
              "이 표본 크기에서 작은 in-sample/CV 변동은 대부분 노이즈).")
        return result

    result["gate_passed"] = True
    print("개선폭이 기준을 넘었다.")
    if not write:
        print("(--write 없이 실행돼서 실제 저장은 안 함 - dry-run)")
        return result

    output = {
        "_comment": (
            f"{date.today().isoformat()} - python3 -m hybrid_engine.recalibrate --write로 "
            f"자동 재보정({source_label}, {len(dataset)}쌍). 교차검증({n_folds}-fold) "
            f"ΔE(CIEDE2000): 기존 {old_loss:.2f} -> 신규 {cv_loss:.2f} "
            f"({improvement_pct:+.1f}%). 재현: 이 스크립트를 같은 데이터셋으로 --write 재실행."
        ),
        **new_params,
    }
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    result["written"] = True
    print(f"저장: {profile_path}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="hybrid_engine 전체 재보정(매트릭스+톤/채도) - 교차검증 게이트를 통과해야만 프로필 갱신")
    parser.add_argument("--cache-dir", default=cp.CACHE_DIR,
                         help="raw+jpeg 페어 디렉토리 (기본: raw_calib_cache/, "
                              "<name>.jpg.3FR(또는 .fff) + <name>.jpg.target.jpg 명명규칙)")
    parser.add_argument("--write", action="store_true",
                         help="교차검증에서 기준 이상 개선되면 hasselblad.json을 실제로 덮어쓴다 "
                              "(생략 시 dry-run - 숫자만 출력, 파일 안 건드림)")
    parser.add_argument("--n-folds", type=int, default=4)
    parser.add_argument("--n-passes", type=int, default=1)
    parser.add_argument("--min-improvement-pct", type=float, default=MIN_CV_IMPROVEMENT_PCT)
    args = parser.parse_args()

    cp.CACHE_DIR = args.cache_dir  # _find_pairs()/_load_calib_set()이 이 모듈 전역을 참조

    print(f"재보정 데이터셋 로드 중... ({args.cache_dir})")
    dataset = cp._load_calib_set()
    print(f"총 {len(dataset)}쌍 로드 완료")
    if not dataset:
        print(f"페어를 못 찾음 - {args.cache_dir} 확인 필요")
        sys.exit(1)

    result = decide_and_maybe_write(
        dataset, args.cache_dir, n_folds=args.n_folds, n_passes=args.n_passes,
        min_improvement_pct=args.min_improvement_pct, write=args.write)
    sys.exit(0 if result["cv_loss"] is not None else 1)


if __name__ == "__main__":
    main()
