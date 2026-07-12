"""
인물(portrait) 서브셋 추출 + 피부톤 hue 불변성 검증 + 인물 타깃 재계산

1. downloaded_samples/ 전체에서 얼굴 검출(YuNet DNN)로 인물 사진만 골라냄
2. 얼굴 영역 중앙 패치를 피부 샘플로 사용해 apply_hncs 적용 전/후 hue 비교
3. 인물 서브셋만으로 블랙p2/화이트p99.5 타깃 재계산 (analyze_all_samples.py의 전체 타깃과 대조용)
"""
import csv
import os
import cv2
import numpy as np

from hasselblad_hncs import apply_hncs

CACHE_DIR = "downloaded_samples"
MODEL_PATH = "face_detection_yunet.onnx"


def stats(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    p = np.percentile
    dark = (gray < 40).sum() / gray.size * 100
    return dict(
        b2=p(gray, 2), w995=p(gray, 99.5), med=np.median(gray),
        sat=s[s > 20].mean() if (s > 20).any() else 0, dark_pct=dark,
    )


def skin_hue(img_bgr, face_box):
    """얼굴 bbox 중앙 40% 영역(이마/뺨 위주, 눈/입 제외)의 평균 hue"""
    x, y, w, h = face_box
    cx0, cy0 = x + int(w * 0.3), y + int(h * 0.25)
    cx1, cy1 = x + int(w * 0.7), y + int(h * 0.55)
    patch = img_bgr[cy0:cy1, cx0:cx1]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return float(np.median(hsv[:, :, 0]))


def main():
    detector = cv2.FaceDetectorYN_create(MODEL_PATH, "", (320, 320),
                                          score_threshold=0.7)

    files = sorted(f for f in os.listdir(CACHE_DIR) if f.lower().endswith(('.jpg', '.jpeg')))

    portraits = []
    hue_deltas = []
    for fname in files:
        path = os.path.join(CACHE_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            continue

        # faces: [x, y, w, h, ...landmarks..., score] per row
        best = max(faces, key=lambda f: f[-1])
        face = tuple(int(v) for v in best[:4])
        st = stats(img)
        hue_before = skin_hue(img, face)

        graded = apply_hncs(img)
        hue_after = skin_hue(graded, face)

        portraits.append(dict(filename=fname, n_faces=len(faces), **st))
        if hue_before is not None and hue_after is not None:
            hue_deltas.append(dict(filename=fname, hue_before=hue_before, hue_after=hue_after,
                                    delta=hue_after - hue_before))

    print(f"=== 인물(얼굴 검출) 서브셋: {len(portraits)}/{len(files)}장 ===\n")

    if portraits:
        shadow_valid = [p for p in portraits if p['dark_pct'] > 5]
        b2_target = np.mean([p['b2'] for p in shadow_valid]) if shadow_valid else float('nan')
        w995_target = np.mean([p['w995'] for p in portraits])
        print(f"인물 블랙p2 타깃: {b2_target:.1f} (그림자유효 {len(shadow_valid)}장, std={np.std([p['b2'] for p in shadow_valid]) if shadow_valid else 0:.1f})")
        print(f"인물 화이트p99.5 타깃: {w995_target:.1f} (std={np.std([p['w995'] for p in portraits]):.1f})")

    print(f"\n=== 피부톤 hue 불변성 검증 (apply_hncs 적용 전/후, {len(hue_deltas)}장) ===")
    for h in hue_deltas:
        print(f"  {h['filename']:40s} hue {h['hue_before']:5.1f} -> {h['hue_after']:5.1f}  (delta={h['delta']:+.1f})")
    if hue_deltas:
        deltas = [abs(h['delta']) for h in hue_deltas]
        print(f"\n  평균 |delta|={np.mean(deltas):.2f}, 최대={np.max(deltas):.2f}")

    with open("portrait_stats_result.csv", "w", newline='', encoding='utf-8-sig') as f:
        if portraits:
            writer = csv.DictWriter(f, fieldnames=list(portraits[0].keys()))
            writer.writeheader()
            writer.writerows(portraits)

    with open("skin_hue_result.csv", "w", newline='', encoding='utf-8-sig') as f:
        if hue_deltas:
            writer = csv.DictWriter(f, fieldnames=list(hue_deltas[0].keys()))
            writer.writeheader()
            writer.writerows(hue_deltas)


if __name__ == "__main__":
    main()
