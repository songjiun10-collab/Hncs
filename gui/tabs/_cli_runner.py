"""hybrid_convert/raw_pipeline_tab/lens_correction_tab 3개 subprocess 탭이
공유하는 실행 로직. 탭 각각에서 반복되던 결함 3개를 여기 한 곳에서 고친다:
백그라운드 스레드 시작 전 Tk 변수는 호출자가 이미 메인 스레드에서 읽어
넘겨야 하고(work 콜러블은 CliRunner가 아니라 탭이 조립), work() 안에서
발생한 예외는 on_error로 회수되어 탭이 항상 복구되며(진행바 정지, 버튼
재활성화), 출력용 임시 디렉토리는 탭 위젯 하나당 하나만 만들어 실행마다
비우고 재생성한다(디스크에 최대 한 실행분만 남음)."""
import os
import shutil
import tempfile
import threading


class CliRunner:
    """탭 위젯 하나당 인스턴스 하나 생성. 실행 버튼/파일선택 버튼/진행바
    상태 전환과 임시 출력 디렉토리 수명을 관리한다. 커맨드 조립, subprocess
    실행, 결과 이미지 로드처럼 탭마다 다른 부분은 start()에 넘기는 work
    콜러블 안에서 한다."""

    def __init__(self, widget, run_button, choose_button, progress):
        self._widget = widget  # self.after()로 메인 스레드에 결과를 넘길 위젯
        self._run_button = run_button
        self._choose_button = choose_button
        self._progress = progress
        self.out_dir = tempfile.mkdtemp(prefix="hncs_gui_")

    def start(self, work, on_done, on_error):
        """work()를 백그라운드 스레드에서 실행한다. 정상 반환값은
        on_done(result)로, work() 안에서 발생한 예외는 on_error(exc)로
        메인 스레드에서 호출된다(self._widget.after(0, ...) 경유) - 어느
        쪽이든 끝나면 진행바를 멈추고 버튼을 다시 눌러지게 만든다. 시작
        전 out_dir을 비우고 재생성해서 이전 실행 결과물이 남지 않게 한다.
        반환값(Thread)은 실사용에서는 무시해도 되고, 테스트에서 join()해
        완료를 기다리는 데 쓴다."""
        shutil.rmtree(self.out_dir, ignore_errors=True)
        os.makedirs(self.out_dir, exist_ok=True)
        self._run_button.configure(state="disabled")
        self._choose_button.configure(state="disabled")
        self._progress.pack(fill="x", padx=4)
        self._progress.start()

        def worker():
            try:
                result = work()
            except Exception as exc:
                self._widget.after(0, self._finish, on_error, exc)
            else:
                self._widget.after(0, self._finish, on_done, result)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    def _finish(self, callback, arg):
        self._progress.stop()
        self._progress.pack_forget()
        self._run_button.configure(state="normal")
        self._choose_button.configure(state="normal")
        callback(arg)
