"""
노이즈 제거 헬퍼. 두 방식 제공:
  nlm        - Non-local Means (cv2.fastNlMeansDenoisingColored). 품질은
               제일 좋지만 느림 - 고ISO 야간샷처럼 디테일을 최대한
               지키면서 노이즈만 빼고 싶을 때
  bilateral  - Bilateral filter. 훨씬 빠르지만 엣지 보존이 nlm보다 약함 -
               빠른 미리보기나 대량 처리용

brands/*.py의 apply_*() 톤/색 함수들과 체이닝해서 쓰는 걸 염두에 뒀음
(예: 고ISO로 찍힌 야경 샘플을 denoise 후 apply_hasselblad_night 적용).
"""
import cv2


def denoise(img_bgr, strength=10, method="nlm"):
    if method == "nlm":
        return cv2.fastNlMeansDenoisingColored(
            img_bgr, None, h=strength, hColor=strength,
            templateWindowSize=7, searchWindowSize=21,
        )
    if method == "bilateral":
        # strength를 sigmaColor/sigmaSpace로 환산 (경험적 스케일)
        sigma = strength * 7
        return cv2.bilateralFilter(img_bgr, d=9, sigmaColor=sigma, sigmaSpace=sigma)
    raise ValueError(f"알 수 없는 method: {method} (nlm 또는 bilateral)")
