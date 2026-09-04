# tools/

*[English README](README.md)*

CLI와 리서치 스크립트 모음. 배포되는 코드가 이 안의 어떤 것도 import하지
않는다 - 컨벤션은 이 디렉토리의 `CLAUDE.md` 참고. 아래 전부 `core`/
`brands`/`tools` import 경로가 풀리도록 저장소 루트에서 실행할 것.

## RAW -> Log 색공간 파이프라인 (전문가용)

`brands/`의 브랜드별 `apply_*` 엔진과는 목적이 완전히 다른 별도
모듈이다. "이 카메라가 실제로 만드는 JPEG"을 근사하는 대신, RAW
파일을 **카메라 종류와 무관하게** 공통 중간 색공간(ProPhoto RGB
Linear)으로 표준화한 뒤, 원하는 비디오 카메라의 Log 커브/색역(F-Log2,
S-Log3, V-Log, ARRI LogC3/4 등)으로 인코딩한다 - 그러면 그 카메라용
크리에이티브 `.cube` LUT를 색 왜곡 없이 RAW 사진에 적용할 수 있다
([raw-alchemy](https://github.com/shenmintao/raw-alchemy)에서 영감을
받아 `colour-science` 위에 재구현).

```
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3
python3 -m tools.raw_pipeline photo.CR3 photo.exr --log-space S-Log3   # 32비트 float OpenEXR, scene-referred
python3 -m tools.raw_pipeline photo.ARW photo.tiff --log-space V-Log --lut looks/my_look.cube
python3 -m tools.raw_pipeline photo.NEF photo.tiff --log-space F-Log2 --exposure 1.0
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode highlight_safe
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space V-Log --auto-expose-mode matrix
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3 --auto-wb-mode white_patch
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3 --auto-wb-mode shades_of_gray
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --hdr-space HLG
python3 -m tools.raw_pipeline photo.CR3 photo.exr --hdr-space PQ --hdr-peak-nits 4000
python3 -m tools.raw_pipeline photo.RAF photo.tiff --log-space F-Log2 --lens-correct
```

`--log-space`와 `--hdr-space`(BT.2020 PQ/HLG, 미검증 - 실제
HDR10/HLG 디스플레이로 확인된 적 없음)는 상호 배타적이고, `--lut`는
`--log-space`에서만 쓸 수 있다.

자동 추정 옵션 두 개는 기본이 꺼짐(기본값은 카메라 WB / 수동 노출):
`--auto-expose-mode`(`average`/`highlight_safe`/`matrix` - 아래
설명)와 `--auto-wb-mode`(`white_patch`/`shades_of_gray`, Finlayson&Trezzi
2004 - 핫셀블라드 13쌍 캘리브레이션 세트로 검증한 결과 카메라 실제
화이트밸런스 대비 ΔE00 14-16, 즉 명백히 다른 색이라 실사용은
권장하지 않고 조명을 모를 때의 크리에이티브 실험용으로만 남겨둠).

`--lens-correct`는 아래 `lens_correction.py`와 같은 EXIF/lensfun
지오메트릭 왜곡보정을 실행한다(`resolve_lens_params()` 공유) - RAW
디코드 직후, auto-WB/노출/Log/HDR/LUT보다 먼저 linear ProPhoto RGB
이미지에 적용된다. 픽셀 위치만 재배치하고 색은 건드리지 않으므로
이후 모든 단계가 동일하게 보정된 지오메트리를 보게 된다. 기본은
꺼짐이며, 켜면 lensfun 매칭 실패 시 실행이 중단된다(`--make`/
`--model`/`--lens`/`--focal-length`/`--aperture`/`--lens-distance`로
EXIF 오버라이드, `lens_correction.py`와 동일).

![RAW -> Log 색공간 데모 - sRGB 디코드 vs V-Log 인코딩](../docs/images/raw_pipeline_demo.jpg)

*같은 RAW(후지필름 X-T1)를 표준 sRGB로 디코드한 것(왼쪽)과
`raw_pipeline --log-space V-Log`로 인코드한 것(오른쪽). 오른쪽의
평탄하고 저대비/저채도인 룩은 의도된 결과다 - 그레이딩 전
Log 상태 그대로다.*

출력 포맷은 확장자로 결정된다 - `.tif`/`.tiff`는 16비트 정수
파일(가장 넓은 뷰어 호환성), `.exr`는 32비트 float OpenEXR(Log/그레이딩
워크플로우의 실제 업계 표준 scene-referred 포맷 - DaVinci Resolve,
Nuke 등이 직접 읽으며, float라 정수 포맷처럼 클리핑 헤드룸이
날아가지 않는다).

자동 노출 측광 모드 3가지(`--auto-expose-mode`): `average`(프레임
전체 평균을 미드그레이로 - 원래의 가장 단순한 모드), `highlight_safe`(고
백분위, 기본 99.5퍼센타일을 클리핑 아래 목표치, 기본 0.9로 고정 -
섀도우 디테일을 희생해 하이라이트를 보호, 고대비 장면에 유용),
`matrix`(중앙가중 존 평균, 카메라의 멀티존 평가측광을 흉내냄 -
단순 평균보다 프레임 가장자리의 극단적 밝기에 덜 흔들림). 모듈
독스트링에 처음부터 명시돼있던 공백을 메운 기능들이다.

지원 Log 공간: `../core/log_pipeline.py`의 `LOG_SPACES` 참고
(F-Log/F-Log2/V-Log/N-Log/Canon Log 2·3/S-Log3/S-Log3.Cine/Arri
LogC3·4/Log3G10/D-Log). 커브-색역 짝은 `colour-science`의 정의를
그대로 쓴다 - 각 제조사의 공식 스펙과 전수 대조되지는 않았고, 이
프로젝트의 다른 "미검증" 표시 항목들과 같은 종류의 유보다.

## 렌즈 왜곡 보정

위의 색 렌더링 엔진들과 독립적인 순수 지오메트릭 도구다 -
[lensfun](https://lensfun.github.io/)에 번들된 카메라+렌즈 프로필
데이터베이스(`lensfunpy`를 통해, 카메라 948개/렌즈 1304개, `pip
install -r requirements.txt` 외 추가 시스템 패키지 불필요)로
배럴/핀쿠션 왜곡을 되돌린다. EXIF(`exiftool`)에서 Make/Model/
LensModel/FocalLength/FNumber를 읽어 맞는 프로필을 자동으로
찾으며, RAW와 이미 렌더링된 JPEG/TIFF/PNG 입력을 모두 받는다.

```
python3 -m tools.lens_correction photo.RAF corrected.jpg
python3 -m tools.lens_correction photo.jpg corrected.jpg --lens "XF10-24mmF4 R OIS" --focal-length 10 --aperture 8
```

카메라나 렌즈가 데이터베이스에 없거나, 매칭된 렌즈 프로필에 왜곡
캘리브레이션 데이터가 없으면 이 도구는 보정 없이 조용히 통과시키지
않고 명시적으로 실패한다(`camera_not_found` / `lens_not_found` /
`no_distortion_data`) - `../core/lens_correction.py`의
`correct_from_exif()` 참고. 비네팅/색수차 보정은 현재 범위 밖이다
(`ModifyFlags.DISTORTION`만 적용).

이 파일의 `resolve_lens_params()`(EXIF 읽기 + 오버라이드 병합,
`--make`/`--model`/`--lens`/`--focal-length`/`--aperture`)는 위
`raw_pipeline.py`의 `--lens-correct`와 공유돼, 두 CLI가 누락되거나
잘못된 EXIF를 동일한 방식으로 처리한다.

## 포토샵 / DaVinci Resolve 프리셋 내보내기 (.cube LUT)

`../hybrid_engine/core/preset_inverse.py`의 `TARGET_FUNCS` 레지스트리에
이미 등록된 `apply_*` 브랜드/필름시뮬레이션 함수 중 아무거나 표준
Adobe `.cube` 3D LUT 파일로 굽는다(`../core/lut_export.py`). 파라메트릭
ACR/`.xmp` 프리셋과 달리 `.cube` 파일은 "입력 색 -> 출력 색"만
저장한다 - 원본 함수 내부가 HSV 회전이든 Lab 커브든 CLAHE든 상관없이
브랜드의 룩을 그대로 옮길 수 있다. 포토샵의 Color Lookup 조정 레이어가
`.cube`를 직접 읽고, DaVinci Resolve/Premiere/After Effects도 마찬가지다.

```
python3 -m tools.export_lut --list                            # 사용 가능한 프리셋 전체 목록
python3 -m tools.export_lut hasselblad hasselblad.cube
python3 -m tools.export_lut fuji_astia fuji_astia.cube --size 33   # 33은 Adobe 표준 그리드 크기
python3 -m tools.export_lut hasselblad hasselblad.cube --install-lightroom  # Lightroom/ACR의 LUT Profiles 폴더에도 복사
```

**알려진 한계**: CLAHE(적응형 로컬 대비, 예: `fuji.apply_pro_neg_hi`)
기반 함수는 입력 색뿐 아니라 주변 픽셀 분포에도 결과가 좌우된다 -
3D LUT는 정의상 문맥 없는 픽셀별 매핑(같은 입력 색은 항상 같은
출력 색)이라 이 로컬 적응성을 정확히 표현할 수 없다.
`bake_lut_from_function()`은 identity 그리드 전체를 하나의 합성
이미지로 한 번에 통과시켜, 적어도 의미 없는 점별 결과 대신 안정적이고
그리드 구조에 의존하는 결과를 만든다 - 그래도 실제 사진에 같은
함수를 적용한 것과 정확히 일치하지는 않는다. `.cube` 포맷 자체의
구조적 한계이지 버그가 아니며, `../core/lut_export.py` 모듈
독스트링에 이 프로젝트의 "미검증/근사" 표시 컨벤션대로 남겨져있다.

**Lightroom Classic / Adobe Camera Raw**: 별도 내보내기 경로가 필요
없다 - ACR 12.3 / Lightroom Classic 9.3부터 Adobe가 고정된 "LUT
Profiles" 폴더(macOS는 `~/Library/Application Support/Adobe/CameraRaw/LUT
Profiles`, Windows는 `%APPDATA%\Adobe\CameraRaw\LUT Profiles`)에서
raw `.cube` 파일을 직접 읽어 Develop 모듈의 Profile Browser에 Profile로
띄운다 - 수동 Color Lookup 조정 레이어가 필요한 포토샵과 다르다.
`--install-lightroom`이 방금 구운 `.cube`를 거기 복사해준다(`--group`으로
Profile Browser 서브폴더 지정, 기본값 `Hncs`) - Adobe 앱이 Linux용을
내놓지 않으므로 macOS/Windows 전용.

## DCP 카메라 프로필 (색채측정 보정, X2D II 전용)

위의 `.cube` 경로가 이미 렌더링된 이미지에 얹는 룩이라면, 이건 **RAW
디모자이크 직후 색변환 단계**로 들어간다. 기여받은 X2D II
ColorChecker 프레임 10장을 카메라 네이티브 RGB 공간(`decode_raw_native()`
사용 - libraw의 색매트릭스와 화이트밸런스를 둘 다 우회)에서 XYZ(D50)
참조값에 최소자승 피팅한 뒤, Adobe `.dcp` 프로필(`../core/dcp_export.py`)로
내보낸다 - Lightroom Classic/Camera Raw가 이를 읽는다.

```
python3 -m tools.analyze_camera_native_matrix   # 피팅 + libraw 내장 매트릭스와 교차검증 비교
```

`../hybrid_engine/EVALUATION.md`("후속 실측 21")에서 검증한 측정값
(XYZ D50 기준 patch-mean ΔE00): libraw 내장 매트릭스 7.81 -> 차트-피팅
매트릭스 **2.83**(leave-one-image-out 교차검증), libraw 대비 63.8%
개선.

**알려진 한계**: (1) 촬영 당시 장면 조명은 이 데이터로부터 복원
불가능하다 - 기여받은 `manifest.csv`의 `illuminant` 컬럼이 비어있고,
차트 참조값이 피팅 전에 D50으로 색순응되므로 결과 매트릭스는 구조상
D50 기준이다 - 그래서 `CalibrationIlluminant1`을 측정되거나 가정된
장면 조명이 아니라 참조 공간에 맞춰 **23(D50)**으로 설정했다;
(2) 10프레임 전부 한 번의 버스트에서 나온 것이라 조명 조건이 하나뿐이고
dual-illuminant 보간이 불가능하다; (3) Lightroom이 실제로 의도대로
이 파일을 렌더링하는지는 오랫동안 미검증이었다(이 프로젝트 개발
환경에 Adobe 소프트웨어가 없어 exiftool을 통한 TIFF 구조 유효성과
수치 왕복 검사만 했음) - 2026-08-31부로 최소한 파일 로딩 단계는
확인됨: 실사용자 테스트(Chris Schmauch)에서 파일이 Lightroom에
로드되지 않는 것을 발견, 잘못된 헤더 매직넘버와 잘못된
`UniqueCameraModel` 값이 원인임을 밝혀 수정, 수정 후 정상 로드
확인 - 전체 경위는 `../core/dcp_export.py` 모듈 독스트링 참고;
(4) X2D II 100C 전용(`UniqueCameraModel`로 선언).

## 브랜드 시그니처 변별력 검증 (리서치)

`classify_brand.py`는 이 프로젝트의 다른 도구들과 반대 방향으로
동작한다 - 새 기능을 만드는 대신, 이미 계산된 10개 브랜드의
population 시그니처(`datasets/<brand>/*_signature.json`, 총
852장)가 실제로 브랜드를 구별할 만한 신호를 갖고 있는지 leave-one-out
nearest-centroid 분류로 검증한다. 거리는 표준화(z-score)되고,
매 폴드마다 held-out 사진은 자기 브랜드의 centroid 계산에서 완전히
제외된다(누수 없음). `npix`/`is_portrait`/`quality`/`subsampling`(이미지
크기, JPEG 인코더 설정)은 의도적으로 제외했다 - 포함하면 분류기가
실제 색 렌더링 차이 대신 "어느 브랜드가 어떤 해상도/JPEG 설정을
업로드하는가"를 학습해버린다. `ricoh_gr`은 분류기에서 완전히
제외된다 - 이 브랜드의 `color_signature.json`은 다른 10개 브랜드처럼
`hue_mean`이 아니라 `hue_median`을 저장해서(같은 통계량이 아니라
비교 불가) 근사하지 않고 그냥 뺐다 - CLI가 실행할 때마다 찍는
안내문 참고. LOO 리서치 검증 자체에는 predict 모드가 없다 - 설계
근거는 `../docs/superpowers/specs/2026-07-24-brand-classifier-design.md`.
(별도의 "재미용" 예측기 - `../core/brand_classifier.py`의
`rank_brands_by_distance()` / `classify_brand.py predict` - 는
몇 문단 아래와
`../docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`에
설명돼있다.)

```
python3 -m tools.classify_brand                # Set A: tone+color+gamut (15차원)
python3 -m tools.classify_brand --features all  # Set B: + texture (21차원)
```

실행 결과 - Set A(텍스처 제외) - 전체 정확도: `0.196`, macro 정확도:
`0.232`(다수결 베이스라인 `0.146`, 균등 베이스라인 `0.100`(1/10)) /
Set B(텍스처 포함) - 전체 정확도: `0.498`, macro 정확도: `0.490`.

텍스처의 sharpening/micro_contrast는 브랜드마다 다른 공식을
쓴다(`../docs/project_structure.en.md`에 문서화 - 캐논/소니와
니콘/라이카/펜탁스/리코 GR이 서로 다른 스케일), 그래서 Set B가
Set A보다 점수가 높아도 이 결과만으로는 "진짜 색 차이"와 "어떤
공식이 쓰였는가"를 구분할 수 없다. `leica`(45)/`pentax`(40)/
`phaseone`(16)은 표본이 얇아 해당 브랜드들의 recall 수치는 특히
노이즈가 크다.

**그리고 재미로**: 같은 검증된 도구 위에 만든 `predict` 서브커맨드 -
아무 사진이나 넣으면 거리 기준으로 10개 브랜드 centroid 중 어디에
가장 가까운지 순위를 매긴다. 텍스처는 제외된다(Set A만, tone+color+gamut) -
새 사진에 대해서는 브랜드별 텍스처 공식을 재구성할 수 없다는 위와
같은 이유. 측정 정확도가 19.6%밖에 안 되므로(위 실행 결과 참고) 가짜
신뢰도 숫자는 절대 보여주지 않고("소니 87%" 같은 것 없음) 거리
순위만, 그 정확도 수치를 콘솔·HTML 출력 양쪽에 항상 같이 찍어서
보여준다.

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html  # 사진을 base64로 내장한 독립 실행 정적 HTML
```

## 비디오 엔진 (프레임 단위, 엔지니어링 재사용 - 새 측정 아님)

`video_engine.py`는 이미 측정된 브랜드 룩을 실제 비디오 파일(mp4)에
프레임 단위로 적용한다 - 새로운 색채측정을 추가하지 않는다. 21개
브랜드를 지원한다: population-fit 10개 브랜드의 측정된 톤커브
파라미터(캐논/라이카/니콘/올림푸스/파나소닉/펜탁스/페이즈원/
리코 GR/시그마/소니)에 후지필름 필름 시뮬레이션 프리셋 10종과
핫셀블라드의 `apply_hncs`를 더한 것(`fuji_astia`/`fuji_pro_neg_std`/
`fuji_pro_neg_hi`/`fuji_eterna_cinema`/`fuji_eterna_bleach_bypass`/
`fuji_nostalgic_neg`/`fuji_reala_ace`/`fuji_classic_negative`/
`fuji_acros`/`fuji_monochrome`/`hasselblad`) - 어떤 프리셋이 CLAHE
없는 변형이 필요했고 어떤 건 아니었는지는
[docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md](../docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md)
참고.

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
```

**알려진 한계**: (1) 오디오는 무손실 remux 단계로 기본 보존된다
(`imageio-ffmpeg`에 번들된 정적 ffmpeg 바이너리, `-c:v copy -c:a
copy` - 재인코딩 없음, 첫 번째 오디오 트랙만, 끄는 옵션 없음) - remux가
실패하면 무음 비디오로 폴백하지 않고 전체 실행이 중단된다;
(2) population-fit 10개 브랜드에 `fuji_pro_neg_hi`와 `hasselblad`를
더한, 사진 모드 `apply_*`가 실제로 CLAHE를 쓰는 21개 중 12개
브랜드만 - 비디오 경로는 프레임간 깜빡임을 피하려고 CLAHE(프레임별
적응형 로컬 대비 보정)를 생략하므로 사진 모드 룩과 완전히 동일하지
않다; 나머지 후지 필름시뮬레이션 프리셋 9종은 애초에 CLAHE를 쓴
적이 없어 사진 모드 그대로 비디오 모드에 적용된다(유일한 차이는
손실 비디오 코덱 압축); (3) 이건 비디오 전용 색채측정이 아니다 -
카메라 브랜드가 실제로 스틸 JPEG과 다르게 비디오를 렌더링하는지(다른
톤커브, 샤프닝 등)는 미검증; (4) 이 환경에서는 합성 테스트 비디오로만
검증됐다 - 스모크 테스트용 실제 카메라 mp4/mov 샘플이 없었다.

## 측정값 재현/재검증

```
python3 -m tools.analyze hasselblad       # 핫셀블라드 공식 샘플 전체 population 통계
python3 -m tools.analyze portrait         # 인물 서브셋 + 피부톤 색상각 불변성 검증
python3 -m tools.analyze leica            # 라이카 imaging-resource.com population
python3 -m tools.analyze phaseone         # 페이즈원, 동일
python3 -m tools.analyze pentax           # 펜탁스, 동일
python3 -m tools.analyze ricoh_gr         # 리코 GR, 동일
python3 -m tools.analyze fuji_film_modes  # 후지 필름 모드별 population + 프리셋 방향 검증

python3 -m tools.download fuji-links      # 후지 RAW/JPEG 구글드라이브 링크 수집
python3 -m tools.download fuji-pairs      # 그 링크에서 RAW+JPEG 페어 다운로드(gdown 필요)

python3 -m tools.calibrate grid_search    # 핫셀블라드 raw에서 진짜 전/후 그리드서치(rawpy 필요, 대용량 다운로드)
python3 -m tools.calibrate learn_curve    # raw+jpeg 픽셀 대응에서 직접 톤커브 학습(rawpy 필요)
python3 -m tools.calibrate regularize     # 학습된 LUT 정규화 + leave-one-out 교차검증
```

`evaluate_darktable_vs_rawpy.py`(리서치 전용 RAW 디코더 비교
실험)를 재현하려면 시스템에 `darktable-cli`가 설치돼있어야 한다
(`apt-get install darktable` 또는 배포판에 맞는 명령 - Python
`requirements.txt`에 안 들어가는 별도 시스템 패키지). 여기 있는
다른 도구는 darktable을 요구하지 않는다.
