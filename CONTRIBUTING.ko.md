# HNCS 기여 가이드

*[English](CONTRIBUTING.md)*

관심 가져줘서 고맙다. 이 프로젝트는 카메라 제조사의 공식 샘플 이미지를
측정해서 각 브랜드의 색과학을 코드로 근사하는 프로젝트다 - 전체 그림은
[README.ko.md](README.ko.md) 참고. **코드**와 **데이터** 두 종류의
기여를 똑같이 환영한다.

## 시작하기 전에

- 해당 영역의 `CLAUDE.md`를 먼저 읽는다: [`brands/CLAUDE.md`](brands/CLAUDE.md),
  [`tools/CLAUDE.md`](tools/CLAUDE.md), [`hybrid_engine/CLAUDE.md`](hybrid_engine/CLAUDE.md),
  [`docs/CLAUDE.md`](docs/CLAUDE.md), [`gui/CLAUDE.md`](gui/CLAUDE.md),
  [`tests/CLAUDE.md`](tests/CLAUDE.md), [`datasets/CLAUDE.md`](datasets/CLAUDE.md).
  각 디렉토리를 실제로 지배하는 관례 - 파일 구조, 통계 규칙, 뭐가
  배포용이고 뭐가 연구 전용인지 - 가 여기 있다.
- 작은 수정이 아니면 먼저 이슈를 열어서 뭘 왜 바꾸려는지 설명한다.
  양쪽 다 PR을 다시 쓰는 수고를 던다.
- PR은 `main`이 아니라 `develop`을 대상으로 한다 - `main`은 주기적으로
  `develop`에서 동기화되는 쪽이고 직접 작업하는 브랜치가 아니다.

## 코드 기여

### 준비

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
```

저장소 루트에서 실행한다. `.venv`가 이미 있으면 재사용하고, 새로 추가된
의존성을 반영하도록 설치 단계부터 실행한다. 설치와 테스트는 같은
인터프리터로 실행한다. macOS에서는 `python3`만 쓰면 프로젝트 가상환경
대신 시스템 Python이 선택될 수 있다.

`hybrid_engine.*` 모듈은 Python>=3.11이 필요할 뿐, 3.12가 따로 필요한 건
아니다 - `requirements.txt`가 고정한 `colour-science==0.4.7`이
Python>=3.11을 요구한다(3.9 기본 `python3`로는 colour-science 0.4.4까지만
설치되는데, 여기엔 `hybrid_engine`이 모듈 로드 시점에 바로 import하는
함수가 빠져있다). `hybrid_engine/CLAUDE.md`가 3.12 venv를 쓰는 건 그
머신의 기본 `python3`가 3.9였을 때 마침 3.12를 쓸 수 있어서였지 3.12가
요구사항이라서가 아니다 - 3.11 이상이면 어느 인터프리터든 된다. 이
디렉토리를 건드린다면 `hybrid_engine/CLAUDE.md` 참고. 나머지도 3.11+에서
동작한다(CI는 3.11 사용).

CI(`.github/workflows/tests.yml`)가 모든 push/PR에서 전체 테스트
스위트를 돌린다 - 리뷰 전에 반드시 green이어야 한다.

### 관례

- **문제를 푸는 최소한의 코드.** 한 번만 쓰는 코드에 추상화 넣지 않기,
  미리 설정 가능하게 만들지 않기, 일어날 수 없는 케이스에 에러 처리
  넣지 않기. 200줄이 50줄이 될 수 있으면 50줄로 만든다.
- **수술적인 diff.** 바뀐 줄 하나하나가 그 PR의 목적과 직접 연결돼야
  한다. 같은 PR 안에서 주변 코드 포맷팅/리팩토링을 같이 하지 않는다 -
  그건 별도 이슈/PR로.
- **배포된 `apply_*` 함수**(`brands/*/look.py` 등)나
  `hybrid_engine/assets/profiles/`(`.json`/`.dcp`) 아래는 이슈에서 먼저
  논의하지 않고는 절대 수정하지 않는다. 이건 실제로 배포된 캘리브레이션
  산출물이다 - 바꾸는 건 의도적이고 리뷰를 거친 결정이어야지, 지나가다
  손대는 게 아니다. (메인테이너 쪽에서 pre-commit 훅으로 기계적으로
  막혀 있다 - 궁금하면 `.claude/hooks/README.md` 참고.)
- 실제 결과를 낸 일회성 분석 스크립트는 gist나 개인 fork에 남기지 말고
  `tools/`에 평범하고 안 추상화된 파일로 넣는다. 다음 사람이 새 카메라/
  브랜드에서 거의 똑같은 스크립트를 또 필요로 할 가능성이 높다.

### 캘리브레이션 관련 주장을 담은 변경이라면

색과학 결과에 대한 "이게 더 낫다" 류의 주장은 이 프로젝트의 통계
기준(`hybrid_engine/CLAUDE.md`, 협상 불가)을 통과해야 한다:

- 평균 차이만으로 승자를 선언하지 않는다 - 부트스트랩 95% CI를 같이
  낸다(또는 페어드 t-검정 + 부호 검정까지 같이 돌려주는 프로젝트의
  `summarize()` 헬퍼 사용).
- CI가 0을 걸치면 **판정 보류**다 - 평균이 아무리 좋아 보여도 승리로
  올림하지 않는다.
- 결과는 이기든 지든 판정 보류든 `hybrid_engine/EVALUATION.md`에
  기록한다 - 패배·보류 결과도 승리만큼 가치 있다, 다음 사람이 같은
  막다른 길을 또 안 가게 막아준다. 기대하는 형식(페어별 표, 실행
  로그의 정확한 숫자, 반올림 없음)은 그 파일의 기존 항목들 참고.

## 데이터 기여

코드보다 더 값진 경우가 많다 - 이 프로젝트는 구현보다 실제 공식
샘플 이미지, 통제된 RAW+JPEG 페어 쪽에서 훨씬 더 병목이 걸려 있다.
[이슈 #4](https://github.com/songjiun10-collab/Hncs/issues/4)가
바로 이런 종류의 기여의 실제 사례다(Hasselblad X2D II ColorChecker +
RAW/JPEG 페어).

### 뭐가 유용한가

- 프로젝트가 데이터가 얇은 카메라/세대의 동시 촬영 RAW+JPEG 페어,
  가능하면 몇 가지 다른 조명 조건(주광/흐림/텅스텐-혼합/저조도)에
  걸쳐서.
- **측정된** 광원 아래에서 찍은 ColorChecker/컬러 타겟 프레임. 이게
  있으면 `libraw`의 일반 매트릭스 대신 실제 camera-to-XYZ 매트릭스를
  피팅할 수 있다.
- 제조사 앱 렌더(예: Hasselblad Phocus TIFF 익스포트)와 같은 RAW를
  페어로 - JPEG 엔진 vs. RAW 처리 앱 vs. 사진가 보정을 구분할 수
  있게 해준다.

### 형식

정확한 수용 규격은 `datasets/hasselblad/contributed/README.md` 참고
(현재 가장 정리가 잘 된 것, 다른 브랜드도 같은 형태를 따른다). 요약:
필수 컬럼(카메라, 렌즈, ISO, WB 설정, 장면 종류, `download_url` 등
출처 명시)이 있는 `manifest.csv`, 이미지는 커밋하지 않고 외부
호스팅(git-ignore 대상 - manifest와 파생 분석 결과만 추적됨), 그리고
`python3 -m tools.data.verify_contributed_pairs <디렉토리>`(필수
컬럼/파일 존재, manifest와 EXIF Make/Model 대조, RAW/JPEG 촬영시각
2초 이내, JPEG EXIF Software에 Photoshop/Lightroom 흔적 없음을 검사)를
통과해야 분석에 편입된다.

**출처가 핵심이다.** 아무리 좋아 보여도 출처를 밝힐 수 없는 데이터는
쓰지 않는다 - 이 프로젝트의 가치는 정확히 그걸 안 하는 데 있다.

## 라이선스

MIT([LICENSE](LICENSE) 참고). 기여하면 같은 라이선스로 제공하는
것에 동의하는 것으로 본다.
