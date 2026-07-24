# 프로젝트 구조 상세

*[English](project_structure.en.md)*

[메인 README](../README.md)로 돌아가기.

```
brands/       브랜드별 색감 근사 함수 (apply_*)
core/         브랜드 전체가 공유하는 톤커브/LUT/통계/검증 헬퍼
datasets/     커밋된 참조 CSV (공식 샘플 메타데이터, 스크레이핑한 갤러리 링크)
tools/        분석(analyze)/다운로드(download)/캘리브레이션(calibrate) 스크립트
models/       얼굴 검출 등에 쓰는 사전학습 모델
docs/         상세 문서 (이 디렉토리)
```

| 파일 | 역할 |
|---|---|
| `brands/hasselblad.py` | ⭐ 공식 Stable - `apply_hncs`(X 시스템 통합 HNCS 파라메트릭 근사) |
| `brands/hasselblad_learned.py` | Experimental - `apply_hncs_learned` (raw+jpeg 페어에서 직접 학습한 LUT, RMSE는 더 낮지만 표본 10장) |
| `brands/hasselblad_day.py` / `brands/hasselblad_night.py` | Legacy - `apply_hasselblad_day`/`apply_hasselblad_night` (day/night 타깃이 apply_hncs 전체 population 타깃에 수렴 중이라 유지 근거 약해지는 중) |
| `brands/fuji.py` | 후지필름 스타일 필름 시뮬레이션 프리셋 10종 (Astia, PRO Neg, Eterna, Acros, Classic Negative 등) - Astia/Pro Neg Std/Eterna Bleach Bypass/Classic Negative는 population 실측 검증됨, Pro Neg Hi/Eterna Cinema/Nostalgic Neg는 동일장면 비교차트로 추가 검증·재보정(표본 n=1~3, 저신뢰) |
| `brands/leica.py` | 라이카 색감 근사 - `apply_leica_look()` (population-fit 1차 버전) |
| `brands/phaseone.py` | Phase One(Capture One 기본 렌더링) 색감 근사 - `apply_phaseone_look()` |
| `brands/pentax.py` | Pentax 색감 근사 - `apply_pentax_look()` |
| `brands/ricoh_gr.py` | Ricoh GR 색감 근사 - `apply_ricoh_gr_look()` |
| `brands/canon.py` | Canon 색감 근사(EOS R5/R6/R8/R3/R 5바디 population) - `apply_canon_look()` |
| `brands/nikon.py` | Nikon 색감 근사(Z6/Z6 II/D780 3바디 population - Z9/D850 갤러리는 EXIF 빠진 자리표시자 이미지뿐이라 제외) - `apply_nikon_look()` |
| `brands/sony.py` | Sony 색감 근사(A7/A7R/A7S/A7 III/A7 IV 5바디 population, 바디당 23장) - `apply_sony_look()` |
| `brands/panasonic.py` | Panasonic(Lumix) 색감 근사(GH5/GH6/G9 MFT + S5/S1 풀프레임 5바디 population, n=120) - `apply_panasonic_look()` |
| `brands/olympus.py` | Olympus(현 OM System) 색감 근사(OM-1/OM-5/E-M1 Mark III/E-M1X/PEN-F 5바디 population, n=122) - `apply_olympus_look()` |
| `brands/sigma.py` | Sigma 색감 근사(Bayer fp/fp L + Foveon sd Quattro/dp2 Quattro/SD1 Merrill 5바디 population, n=83) - `apply_sigma_look()` |
| `core/curve.py` | 톤커브 수학 (`film_curve`/`s_curve`/`apply_highlight_rolloff`/`shadow_lift`) - 여러 브랜드 모듈이 공유 |
| `core/lut.py` | LUT 적용 헬퍼 |
| `core/engine.py` | population-fit 브랜드(leica/phaseone/pentax/ricoh_gr 및 이후 추가된 나머지 population-fit 브랜드 전부) 공용 엔진 - raw 기준선 없이 population 타깃을 `film_curve`에 직접 대입하는 동일 구조라 하나로 합침 |
| `core/stats.py` | population 통계 계산 (`image_stats`: 블랙p2/화이트p99.5/채도/그림자비율) |
| `core/validation.py` | "진짜 미가공 SOOC인가" EXIF 검증, "실제로 온전히 디코드되는가" 무결성 검증(`is_image_usable`), hue 측정 헬퍼 |
| `core/denoise.py` | 노이즈 제거 (`denoise()`: nlm/bilateral) - 고ISO 샘플을 브랜드 룩 적용 전에 정리할 때 씀 |
| `core/log_pipeline.py` | 브랜드 엔진과 별개인 RAW -> Log 색공간 파이프라인 - RAW를 ProPhoto RGB Linear로 통일한 뒤 F-Log2/S-Log3/V-Log 등 영상 카메라 Log 커브/색역으로 인코딩, 선택적으로 `.cube` LUT 적용 ([raw-alchemy](https://github.com/shenmintao/raw-alchemy) 아이디어 참고, `colour-science` 기반) |
| `core/lut_export.py` | "포토샵/라이트룸 프리셋" 내보내기 - `brands/*.py`의 임의 `apply_*` 함수를 identity 격자 전체에 한 번에 통과시켜 표준 Adobe `.cube` 3D LUT으로 굽는다(`build_identity_grid`/`bake_lut_from_function`/`write_cube_file`), `install_lightroom_profile()`로 Lightroom Classic/Camera Raw의 LUT Profiles 폴더에 바로 설치도 가능. CLAHE 기반 함수는 지역 적응성을 LUT이 구조적으로 담을 수 없다는 한계가 모듈 docstring에 명시돼 있음 |
| `core/brand_classifier.py` | "연구용" 브랜드 시그니처 판별력 검증 - 10개 브랜드(`ricoh_gr`은 `hue_median`/`hue_mean` 통계 불일치로 제외)의 `datasets/*/*_signature.json`을 filename으로 조인해서 leave-one-out nearest-centroid 분류(`load_signatures`/`extract_features`/`standardize`/`nearest_centroid_loo`/`confusion_matrix`/`classification_report`). numpy만 사용, 새 사진 예측 기능은 없음 |
| `datasets/hasselblad/hasselblad_sample_images.csv` | 핫셀블라드 공식 샘플 메타데이터 (카메라/렌즈/작가/jpeg_url/raw_url) |
| `datasets/hasselblad/texture_signature_recomputed.json` | 기존 `texture_signature.json`은 파일명이 `orig_N.jpg`뿐이라 CSV 행 매칭이 불확실(순번 추정, 78개 검증 중 3개 불일치) - CSV의 jpeg_url로 원본을 처음부터 다시 받아 파일명이 정확히 일치하는 새 세트로 재구축(n=123, noise off-by-one 수정 반영). 기존 파일은 원본 기록 보존 목적으로 그대로 둠 |
| `datasets/fuji/fuji_sample_pages.csv` | mirrorlesscomparison.com 후지 갤러리의 RAW/JPEG Google Drive 링크 |
| `datasets/fuji/fuji_imaging_resource_filmmodes.json` | imaging-resource.com X100V/X-T5/X-T4 리뷰 갤러리에서 모은 269장, exiftool FilmMode 태그 포함(Velvia/Provia/Classic Negative/Bleach Bypass/Classic Chrome) - Eterna Bleach Bypass 재보정과 Classic Negative 신규 프리셋의 근거 데이터 |
| `datasets/fuji/chart_comparisons/manifest.json` + `chart_comparison_stats.json` | 사용자가 직접 찾아 공유한 "동일 장면 다중 필름모드 비교차트" 8장의 크롭박스(manifest)와 실측 delta/프리셋 delta 비교 결과(stats) - population 방식과 달리 장면/노출이 고정된 페어 비교라 증거력이 더 강함. 원본 차트 이미지 자체는 제3자 저작물이라 커밋 안 함(`downloaded_samples_fuji_charts/`, gitignore) |
| `datasets/<brand>/{tone,color,texture,gamut}_signature.json` + `joint_distribution.npz` | 픽셀 단위 5종 시그니처 분석(hasselblad/leica/pentax/ricoh_gr/phaseone/canon/sony/nikon/panasonic/olympus/sigma 전부 있음) - 톤/채도-hue/샤프닝-미세대비-노이즈-에지헤일로/Lab 색역, 사진 단위 동일가중 평균 방법론(픽셀 그대로 풀링하면 해상도 편차로 왜곡됨 - `tone_signature.json`의 methodology 필드 참고). **주의**: texture의 sharpening/micro_contrast는 브랜드별로 원본 계산 스크립트가 커밋에 안 남아있어 에이전트마다 공식을 다시 추정하면서 스케일이 갈렸음 - Sony의 sharpening은 최초 계산이 15~20배 커서 Canon 공식(/15)에 맞춰 재계산했고, Canon/Sony의 micro_contrast(DoG sigma 1,2)는 Nikon/Leica/Pentax/Ricoh GR(sigma 1,4 추정, 8~12대)과 자릿수가 달라 서로 직접 비교하면 안 됨(각 브랜드 `.py` docstring과 `texture_signature.json`의 methodology 필드에 상세 기록). Panasonic/Olympus/Sigma부터는 사고 재발 방지를 위해 Canon 공식을 그대로 재사용하도록 에이전트에 명시 지시했고 실제로 sharpening/micro_contrast가 Canon과 근접하게 나와 일관성이 확인됨 |
| `tools/analyze.py` | population 통계/검증 CLI - `hasselblad`/`leica`/`phaseone`/`pentax`/`ricoh_gr`/`fuji_film_modes`/`portrait` 모드 |
| `tools/download.py` | imaging-resource.com 갤러리 공용 스크레이퍼 + 후지 Google Drive RAW/JPEG 페어 다운로더 |
| `tools/calibrate.py` | 핫셀블라드 raw+jpeg 페어 캘리브레이션 CLI - `grid_search`/`learn_curve`/`regularize` 모드 |
| `tools/fuji_chart_calibrate.py` | 후지 "동일 장면 비교차트" 검증 CLI - `python3 -m tools.fuji_chart_calibrate report` (manifest.json의 크롭박스로 스트립 추출 -> 실측 delta vs 프리셋 delta 테이블 출력) |
| `tools/denoise.py` | 노이즈 제거 CLI - `python3 -m tools.denoise input.jpg output.jpg [--strength N] [--method nlm\|bilateral]` |
| `tools/raw_pipeline.py` | RAW -> Log 색공간 CLI - `python3 -m tools.raw_pipeline input.raw output.tiff\|.exr --log-space F-Log2 [--lut looks/x.cube] [--exposure EV] [--auto-expose-mode average\|highlight_safe\|matrix]` |
| `tools/export_lut.py` | 포토샵/DaVinci Resolve/Lightroom용 `.cube` 3D LUT 내보내기 CLI - `python3 -m tools.export_lut --list` / `python3 -m tools.export_lut hasselblad out.cube [--size 33] [--install-lightroom [--group NAME]]` (`hybrid_engine.core.preset_inverse.TARGET_FUNCS` 레지스트리 재사용) |
| `tools/classify_brand.py` | 브랜드 시그니처 판별기 CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]` |
| `tools/verify_contributed_pairs.py` | 기여 데이터셋 자동 검증 CLI(manifest-EXIF 대조, raw/jpeg 동시촬영 확인, 편집 오염 검사) - 규격은 `datasets/hasselblad/contributed/README.md` |
| `tools/highlight_rolloff_signal.py` | 브랜드별 shoulder_start/clahe_clip 추정 가능성 탐색(결론: 근거 부족, 기본값 유지 - `core/engine.py` docstring 참고) |
| `models/yunet.onnx` | 얼굴 검출 모델 (OpenCV Zoo, YuNet 2023mar) - `tools/analyze.py portrait`가 사용 |
