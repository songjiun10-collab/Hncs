"""RAW -> Log 컬러스페이스 탭 - tools.raw_pipeline을 그대로 subprocess로
실행한다."""
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import cv2

from core.log_pipeline import LOG_SPACES
from gui.widgets.image_view import ImageView, quick_raw_preview

LOG_SPACE_CHOICES = sorted(LOG_SPACES)
AUTO_EXPOSE_MODES = ["없음", "average", "highlight_safe", "matrix"]


def build_raw_pipeline_command(input_path, output_path, log_space, exposure=0.0,
                                auto_expose_mode="없음", python_exe=None):
    python_exe = python_exe or sys.executable
    cmd = [python_exe, "-m", "tools.raw_pipeline", input_path, output_path,
           "--log-space", log_space]
    if exposure:
        cmd += ["--exposure", str(exposure)]
    if auto_expose_mode and auto_expose_mode != "없음":
        cmd += ["--auto-expose-mode", auto_expose_mode]
    return cmd


class RawPipelineTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._input_path = None

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=4, pady=4)
        ttk.Button(controls, text="RAW 파일 선택", command=self._choose_file).pack(side="left")

        self._log_space = tk.StringVar(value=LOG_SPACE_CHOICES[0])
        ttk.Combobox(controls, textvariable=self._log_space, state="readonly",
                     values=LOG_SPACE_CHOICES).pack(side="left", padx=4)

        self._auto_expose = tk.StringVar(value="없음")
        ttk.Combobox(controls, textvariable=self._auto_expose, state="readonly",
                     values=AUTO_EXPOSE_MODES).pack(side="left", padx=4)

        self._exposure = tk.DoubleVar(value=0.0)
        ttk.Scale(controls, from_=-3.0, to=3.0, variable=self._exposure).pack(side="left", padx=4)

        self._run_button = ttk.Button(controls, text="변환", command=self._run)
        self._run_button.pack(side="left")

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._log = tk.Text(self, height=6)
        self._log.pack(fill="x", padx=4)
        self._view = ImageView(self)
        self._view.pack(fill="both", expand=True)

    def _choose_file(self):
        path = filedialog.askopenfilename()
        if path:
            self._input_path = path
            self._log.insert("end", f"입력: {path}\n")

    def _run(self):
        if not self._input_path:
            self._log.insert("end", "RAW 파일을 먼저 선택하세요\n")
            return
        self._run_button.configure(state="disabled")
        self._progress.pack(fill="x", padx=4)
        self._progress.start()
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self):
        out_dir = tempfile.mkdtemp(prefix="hncs_gui_")
        output_path = os.path.join(out_dir, "output.tiff")
        cmd = build_raw_pipeline_command(
            self._input_path, output_path, self._log_space.get(),
            exposure=self._exposure.get(), auto_expose_mode=self._auto_expose.get())
        proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
        self.after(0, self._on_done, proc, output_path)

    def _on_done(self, proc, output_path):
        self._progress.stop()
        self._progress.pack_forget()
        self._run_button.configure(state="normal")
        self._log.insert("end", proc.stdout)
        if proc.returncode != 0:
            self._log.insert("end", f"에러 (exit {proc.returncode}):\n{proc.stderr}\n")
            return
        after = cv2.imread(output_path, cv2.IMREAD_UNCHANGED)
        if after is None:
            self._log.insert("end", f"결과 파일을 못 읽음: {output_path}\n")
            return
        try:
            before = quick_raw_preview(self._input_path)
        except Exception as exc:
            self._log.insert("end", f"프리뷰 디코드 실패: {exc}\n")
            before = after
        self._view.show(before, after)


def build_tab(master):
    return RawPipelineTab(master)
