# gui/CLAUDE.md

Tkinter 데스크톱 앱 - `brands/`/`hybrid_engine/`/`tools/`/`core/`의 기존
CLI·함수를 감싸기만 한다. 로직을 여기서 새로 구현하지 않는다: 브랜드
Look은 `apply_*()`를 직접 호출하고, 나머지 4탭은 기존 CLI를
subprocess로 그대로 실행한다(`tools/CLAUDE.md`: tools/의 코드는 shipped
code가 import하지 않는다 - 여기서도 지킨다).

각 `tabs/*.py`는 Tk에 의존하지 않는 순수 함수(명령 조립, 입력 검증)와
그 함수를 쓰는 위젯 클래스를 분리한다 - 순수 함수만 유닛테스트 대상.
`app.py`/`widgets/image_view.py`의 위젯 조립 코드는 실제 Tk 인스턴스가
필요해 CI(헤드리스)에서 테스트하지 않는다.
