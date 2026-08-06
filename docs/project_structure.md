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
| `brands/hasselblad_x2dii.py` | Experimental - `apply_hncs_x2dii` (X2D II 100C 전용, exposure_gamma만 0.8->0.7 - 호출부가 모델 판별해서 골라 써야 함, 표본 41장이라 shoulder_start 등 나머지 파라미터는 안 건드림) |
| `brands/fuji.py` | 후지필름 스타일 필름 시뮬레이션 프리셋 10종 (Astia, PRO Neg, Eterna, Acros, Classic Negative 등) - Astia/Pro Neg Std/Eterna Bleach Bypass/Classic Negative는 population 실측 검증됨, Pro Neg Hi/Eterna Cinema/Nostalgic Neg는 동일장면 비교차트로 추가 검증·재보정(표본 n=1~3, 저신뢰) |
| `brands/leica.py` | 라이카 색감 근사 - `apply_leica_look()` (population-fit 1차 버전) |
| `brands/leica_raw.py` | Experimental - `apply_leica_raw_look` (SL3-P/Q3 43 전용, raw+jpeg 85쌍 기반, ΔE00 직접 그리드서치로 두 바디 모두 개선) |
| `brands/phaseone.py` | Phase One(Capture One 기본 렌더링) 색감 근사 - `apply_phaseone_look()` |
| `brands/pentax.py` | Pentax 색감 근사 - `apply_pentax_look()` |
| `brands/ricoh_gr.py` | Ricoh GR 색감 근사 - `apply_ricoh_gr_look()` |
| `brands/canon.py` | Canon 색감 근사(EOS R5/R6/R8/R3/R 5바디 population) - `apply_canon_look()` |
| `brands/nikon.py` | Nikon 색감 근사(Z6/Z6 II/D780 3바디 population - Z9/D850 갤러리는 EXIF 빠진 자리표시자 이미지뿐이라 제외) - `apply_nikon_look()` |
| `brands/sony.py` | Sony 색감 근사(A7/A7R/A7S/A7 III/A7 IV 5바디 population, 바디당 23장) - `apply_sony_look()` |
| `brands/sony_a7v.py` | Experimental - `apply_sony_a7v_look` (Sony a7 V 전용, raw+jpeg 58쌍 기반 첫 raw 캘리브레이션, ΔE00 직접 그리드서치로 +0.53% 개선) |
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
| `core/engine.py`의 `apply_population_fit_look_video_frame()` | population-fit 브랜드 엔진의 비디오 전용 변형 - CLAHE(프레임별 적응형 로컬 대비 보정)를 생략해 프레임 간 깜빡임을 피한다. `tools/video_engine.py`가 사용 |
| `core/lut_export.py` | "포토샵/라이트룸 프리셋" 내보내기 - `brands/*.py`의 임의 `apply_*` 함수를 identity 격자 전체에 한 번에 통과시켜 표준 Adobe `.cube` 3D LUT으로 굽는다(`build_identity_grid`/`bake_lut_from_function`/`write_cube_file`), `install_lightroom_profile()`로 Lightroom Classic/Camera Raw의 LUT Profiles 폴더에 바로 설치도 가능. CLAHE 기반 함수는 지역 적응성을 LUT이 구조적으로 담을 수 없다는 한계가 모듈 docstring에 명시돼 있음 |
| `core/brand_classifier.py` | "연구용" 브랜드 시그니처 판별력 검증 - 10개 브랜드(`ricoh_gr`은 `hue_median`/`hue_mean` 통계 불일치로 제외)의 `datasets/*/*_signature.json`을 filename으로 조인해서 leave-one-out nearest-centroid 분류(`load_signatures`/`extract_features`/`standardize`/`nearest_centroid_loo`/`confusion_matrix`/`classification_report`/`rank_brands_by_distance`). numpy만 사용, LOO 검증 자체는 예측 모드가 아님(새 사진 1장 예측은 `rank_brands_by_distance`가 담당하는 별도의 "재미용" 경로) |
| `core/photo_signature.py` | "재미용" 예측기의 입력 전처리 - 임의의 새 사진에서 tone/color/gamut 시그니처 필드를 계산(`compute_signature`). texture는 브랜드별 계산 공식 유실로 제외. 원본 계산 스크립트를 복원한 게 아니라 methodology 필드 기반 근사 재구현(설계 근거: `docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`) |
| `core/lens_correction.py` | 렌즈 왜곡 보정 - lensfunpy(lensfun DB, pip 설치만으로 카메라 948종/렌즈 1304종 번들) 기반. EXIF의 Make/Model/LensModel/FocalLength/FNumber로 프로파일을 찾아 지오메트릭 왜곡만 보정한다(비네팅/색수차는 범위 밖 - `ModifyFlags.DISTORTION`). 순수 기하 연산이라 색 파이프라인(`core/curve.py` 등)과 독립 |
| `core/dcp_export.py` | Adobe DCP(카메라 프로필) 쓰기 - 카메라 네이티브 색매트릭스를 Lightroom Classic/Camera Raw가 읽는 `.dcp`로 내보낸다(`write_dcp`/`read_dcp`). DCP는 TIFF 구조라 표준 `struct`로 직접 쓴다(새 의존성 0). `.cube`(룩)와 달리 RAW 디모자이크 직후 색변환 단계용 색채측정 보정. Lightroom 실제 렌더링은 미검증(구조·수치 검증만) |
| `core/upscale.py` | Real-ESRGAN(RRDBNet) AI 업스케일, PyTorch/ONNX Runtime 둘 다 지원(`upscale()`) - `realesrgan`/`basicsr` 공식 pip 패키지는 의존 안 함(`basicsr` 1.4.2가 최신 torchvision과 깨짐, 2026-08 실측 확인), RRDBNet 아키텍처만 그 소스에서 직접 옮겨왔다. 가중치는 xinntao 공식 GitHub Release 1차 소스(`models/upscale/`, git 추적 안 함, 최초 호출 시 자동 다운로드); ONNX 엔진은 그 가중치를 `torch.onnx.export()`로 최초 1회만 변환해서 캐시. 100MP급 원본 대응을 위한 타일 단위 추론 포함 |
| `core/sdcard_undelete.py` | SD카드(FAT32/exFAT) 이미지에서 파일시스템 메타데이터로 삭제 파일을 복구(`recover_fat32`/`recover_exfat`) - 디렉토리 엔트리와 클러스터 체인이 살아있으면 카빙보다 정확하다. FAT32는 삭제 시 짧은 이름 첫 글자가 유실(`_`로 치환), exFAT은 삭제가 엔트리 타입 바이트의 InUse 비트만 지우는 논리적 삭제라 원본 파일명이 대개 그대로 남는다. 클러스터 체인이 FAT 초기화 등으로 끊겼으면 "카메라 파일은 대개 연속 할당"이라는 경험칙으로 폴백(exFAT은 NoFatChain 플래그가 서 있으면 FAT 없이도 복구됨) |
| `core/sdcard_carve.py` | 시그니처 기반 파일 카빙(PhotoRec류, `carve()`) - 포맷되거나 파일시스템이 손상돼 undelete가 실패한 파일의 폴백. JPEG는 세그먼트를 걸으며 SOS 이후 진짜 EOI를 찾아 EXIF 임베디드 썸네일의 EOI에서 끊기는 흔한 카빙 버그를 피하고, TIFF 기반 RAW(CR2/NEF/ARW/ORF/RW2/PEF/DNG/3FR/IIQ 등 대부분)는 IFD/SubIFD 체인의 StripOffsets+StripByteCounts 최댓값으로 끝을 추정하며 Make 태그로 확장자를 정한다. RAF(Fuji)는 헤더에 박힌 CFA 오프셋+길이로, CR3(Canon)는 ISO BMFF 박스 크기 누적으로 정확히 계산하고, X3F(Sigma)는 디렉토리가 파일 끝에 있어 근사치(`approx=True`)만 가능 - 모든 포맷 공통으로 다음 파일 시작 시그니처가 추정 끝보다 앞이면 거기서 자르는 안전망 적용 |
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
| `tools/video_engine.py` | 비디오 파일(mp4)에 브랜드 룩 프레임 단위 적용 CLI - 21개 브랜드: population-fit 10개(canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony) + Fuji 프리셋 10종 + Hasselblad(apply_hncs만) - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (오디오 기본 보존 - imageio-ffmpeg 무손실 remux, CLAHE 생략 - 사진 모드와 동일 출력 아님) |
| `tools/evaluate_hncs_structural.py` | 연구용 - HNCS 실제 4단계 구조(조명별 매트릭스 -> 조명별 chroma LUT -> 공유 필름커브)를 미러링한 실험 모듈(`hybrid_engine/research/hncs_structural.py`)이 Stable `apply_hncs()`의 3단계 단순화보다 ΔE를 개선하는지 핫셀블라드 13쌍 leave-one-out 교차검증으로 확인 - 결과: 판정 보류(통계적으로 노이즈와 구분 안 됨, 초판의 "4.1% 개선"은 재검증 후 정정됨). `apply_hncs()`는 건드리지 않음(연구 전용). 결과 기록: `hybrid_engine/EVALUATION.md` |
| `tools/evaluate_fuji_demosaic.py` | 연구용 - Fuji X-Trans에서 rawpy 기본 데모자이크 vs DHT 알고리즘 비교(실제 raw+jpeg 3쌍) - 결과: LibRaw가 X-Trans에서 quality>2 알고리즘(AHD/DHT/AAHD)을 전부 이미 기본값과 같은 Markesteijn 경로로 합쳐서 rawpy 안에서는 비교 자체가 불가능함을 발견(초판은 "작지만 실재하는 차이"로 오기록, 재검증 후 정정). 결과 기록: `hybrid_engine/EVALUATION.md` |
| `tools/evaluate_darktable_vs_rawpy.py` | 연구용 - RAW 디코드 프로그램 자체(rawpy/LibRaw vs darktable-cli, `hybrid_engine/utils/io.py`의 `decode_raw_darktable()`) 비교(핫셀블라드 13쌍 + Fuji 3쌍) - 결과: 거의 대등(rawpy 평균 ΔE 11.460 vs darktable 11.970, 부호검정 p=0.021로 통계적으로는 유의하나 근소, 초판의 "rawpy 16/16 결정적 승리"는 darktable-cli 서브프로세스가 OMP_NUM_THREADS 상속으로 프레임 75% 잘려 렌더링된 버그였음이 최종 리뷰로 밝혀져 정정). 결과 기록: `hybrid_engine/EVALUATION.md` |
| `tools/export_lut.py` | 포토샵/DaVinci Resolve/Lightroom용 `.cube` 3D LUT 내보내기 CLI - `python3 -m tools.export_lut --list` / `python3 -m tools.export_lut hasselblad out.cube [--size 33] [--install-lightroom [--group NAME]]` (`hybrid_engine.core.preset_inverse.TARGET_FUNCS` 레지스트리 재사용) |
| `tools/classify_brand.py` | 브랜드 시그니처 판별기 CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]`(기본, LOO 리포트) / `python3 -m tools.classify_brand predict photo.jpg [--html out.html]`(재미용, 새 사진 브랜드 순위) |
| `tools/analyze_camera_native_matrix.py` | 카메라 네이티브 공간 색매트릭스 피팅 실험 CLI - `python3 -m tools.analyze_camera_native_matrix` (차트 10장을 `decode_raw_native()`로 디코드 -> XYZ(D50) 참조값에 피팅 -> libraw 내장 매트릭스와 leave-one-image-out 교차검증 비교, 리포트 JSON 저장) |
| `tools/verify_contributed_pairs.py` | 기여 데이터셋 자동 검증 CLI(manifest-EXIF 대조, raw/jpeg 동시촬영 확인, 편집 오염 검사) - 규격은 `datasets/hasselblad/contributed/README.md`. `--make` 인자로 브랜드 무관(2026-08부터 Leica 등도 지원, 기본값 Hasselblad) |
| `tools/highlight_rolloff_signal.py` | 브랜드별 shoulder_start/clahe_clip 추정 가능성 탐색(결론: 근거 부족, 기본값 유지 - `core/engine.py` docstring 참고) |
| `tools/lens_correction.py` | 렌즈 왜곡 보정 CLI - EXIF(Make/Model/LensModel/FocalLength/FNumber)로 lensfun DB를 매치해 지오메트릭 왜곡만 보정, RAW/일반 이미지 둘 다 입력 - `python3 -m tools.lens_correction input.RAF output.jpg [--lens NAME --focal-length N --aperture N]` |
| `tools/upscale.py` | AI 업스케일 CLI(`core/upscale.py`) - `python3 -m tools.upscale input.jpg output.png [--scale 2\|4] [--engine onnx\|pytorch] [--tile-size N] [--tile-pad N]` |
| `gui/tabs/upscale_tab.py` | GUI "AI 업스케일" 탭 - `tools.upscale`을 subprocess로 실행(다른 subprocess 탭과 동일하게 `_cli_runner.CliRunner` 공유) |
| `tools/recover_sdcard.py` | SD카드 삭제/포맷 사진 복구 CLI(`core/sdcard_undelete.py` + `core/sdcard_carve.py`) - `python3 -m tools.recover_sdcard card.img out_dir [--mode undelete\|carve\|both]`. 라이브 블록 디바이스는 거부(`stat.S_ISBLK`/`S_ISCHR`)하고 dd 등으로 미리 뜬 이미지 파일만 다룬다(안전을 위한 설계 선택) - undelete 결과는 `out_dir/undeleted/`, carve 결과는 `out_dir/carved/`에 따로 쓰며 둘 다 돌리면 같은 파일이 양쪽에 중복될 수 있다(의도된 동작) |
| `tools/iso_noise.py` | 핫셀블라드 공식 샘플의 ISO별 노이즈 수준 분석 - 캐시본은 다운로드 단계 리사이즈에서 EXIF가 날아간 상태라 ISO를 CSV/파일명으로 역추적한다 |
| `tools/analyze_pixel_errors.py` | hybrid_engine v1.2가 "어느 픽셀에서" 틀리는지 진단 - 13쌍의 픽셀별 ΔE00을 L(밝기)/hue(색상각) 구간별로 pooling(`evaluation/fidelity.py`의 페어 단위 요약 뒤를 파고드는 용도) |
| `tools/analyze_colorchecker_matrix.py` | [GitHub 이슈 #4 지적 4번] 기여받은 X2D II ColorChecker 차트 10장으로 raw 베이스라인의 실제 색채측정 오차를 재고 차트 최소자승 매트릭스의 개선폭을 확인(ΔE00 7.58 -> 2.78, leave-one-image-out 교차검증) |
| `tools/build_local_manifest.py` | 로컬 사진 라이브러리에서 EXIF DateTimeOriginal로 raw+jpeg 페어를 찾아 기여 `manifest.csv`를 만드는 CLI - `tools.verify_contributed_pairs`의 `verify_row`로 즉시 재검증해 FAIL 행(편집본/셔터 비동기)을 자동 제거하므로 PASS 행만 남는다. RAW 확장자 `.3fr`/`.fff`/`.dng`(Leica) 인식, `--make`로 브랜드 지정(기본 Hasselblad) |
| `tools/evaluate_chromatic_aberration.py` | 연구용 - rawpy `chromatic_aberration`(R/B 채널 스케일링) 9x9 격자 그리드서치 + leave-one-out 교차검증(13쌍으로 처음 확인 후 2026-08에 83쌍(공식 13 + 로컬 기여 61 + owner-x2dii 9)으로 재검증, 결과 동일) - 결과: 폴드 전부가 "보정 없음"`(1.0, 1.0)`을 최적으로 선택한 완전 무신호(포지티브 컨트롤로 파라미터 자체는 정상 동작 확인). (pair, red_scale, blue_scale) ΔE를 폴드 진입 전에 한 번씩만 계산해 표로 캐싱하고 프로세스 풀로 병렬화. 결과 기록: `hybrid_engine/EVALUATION.md` |
| `tools/evaluate_hncs_blend.py` | 연구용 - 조명 하드분류 대신 연속 블렌딩(R/B 선형 / CCT mired 두 가중치 공식)이 나은지 가중 최소자승 피팅 + LOO로 비교 - 13쌍 초판은 판정 보류였으나 `local-mixed-2026-07` 기여분으로 74쌍 재실행 후 두 공식 다 하드클러스터 대비 통계적으로 유의미하게 개선(각 +1.8%, 유의성 경계에 근접 - RB 부호검정 p=0.047, CCT 부트스트랩 CI 하한 +0.017). RB와 CCT 사이 우열은 74쌍에서도 판정 보류. 결과 기록: `hybrid_engine/EVALUATION.md` |
| `tools/simulate_pair_count_power.py` | 부트스트랩 표본 확대 시뮬레이션 - 이미 기록된 13개 페어드 차이를 복원추출해 "n=60이면 유의해지는가"를 투영한다(**실제 새 데이터가 아니라 통계적 투영**). 결과: 세 비교 다 n=60에서도 안정적으로 유의해지지 않는다 |
| `tools/regen_preset_demo_title.py` | `docs/images/preset_demo.jpg` 상단 타이틀 바만 다시 그리는 CLI - 브랜드가 추가돼 apply_* 개수가 바뀔 때마다 사진 그리드 전체를 재렌더링하지 않고 숫자만 맞춘다(`python3 -m tools.regen_preset_demo_title`, 타이틀 아래 타일 부분은 픽셀 그대로 유지) |
| `models/yunet.onnx` | 얼굴 검출 모델 (OpenCV Zoo, YuNet 2023mar) - `tools/analyze.py portrait`가 사용 |
