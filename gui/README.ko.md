# gui/ - 데스크톱 앱

*[English README](README.md)*

`tools/`와 `hybrid_engine/`의 CLI들을 4개 탭(브랜드 룩 미리보기,
hybrid_engine 변환, RAW->Log 파이프라인, 렌즈 보정)으로 감싼 Tkinter
데스크톱 앱. 순수 래퍼다 - 새 색채과학 로직 없이, `tools/README.md`와
`hybrid_engine/README.md`에 문서화된 동일한 명령을 클릭 몇 번으로
쓸 수 있게 할 뿐이다.

```
pip install -r requirements.txt   # Tk에서 이미지를 보여주는 데 필요한 Pillow 포함
python3 -m gui
```

`core`/`brands`/`tools`/`hybrid_engine` import 경로가 제대로 풀리도록
저장소 루트에서 실행할 것.

Tkinter 자체는 Python 표준 라이브러리에 포함돼있지만, 일부 배포판(예:
macOS의 Homebrew Python)은 이를 별도 시스템 패키지(`python-tk`)로
분리해놓았다 - `python3 -m gui`가 Tkinter import 오류로 실패하면
이걸 설치할 것.

렌즈 보정 탭의 유용성은 전적으로 번들된 lensfun 카메라/렌즈
데이터베이스의 커버리지에 달려있다 - 예를 들어 핫셀블라드 카메라는
오래된 항목 4개만 있고 렌즈 데이터가 하나도 없어서, 핫셀블라드 RAW
샘플마다 `lens_not_found`로 실패한다.
