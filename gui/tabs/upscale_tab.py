"""AI 업스케일(Real-ESRGAN) 탭 - tools.upscale을 subprocess로 실행한다."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk

import cv2

from core.upscale import UPSCALE_ENGINES, UPSCALE_SCALES
from gui.tabs._cli_runner import CliRunner
from gui.theme import apply_log_colors
from gui.widgets.image_view import ImageView, image_filetypes

SCALE_CHOICES = [str(s) for s in UPSCALE_SCALES]
ENGINE_CHOICES = list(UPSCALE_ENGINES)


def build_upscale_command(input_path, output_path, scale, engine, python_exe=None):
    python_exe = python_exe or sys.executable
    return [python_exe, "-m", "tools.upscale", input_path, output_path,
            "--scale", str(scale), "--engine", engine]


class UpscaleTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._input_path = None

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=4, pady=4)
        self._choose_button = ttk.Button(controls, text="이미지 선택",
                                          command=self._choose_file)
        self._choose_button.pack(side="left")

        self._scale = tk.StringVar(value=SCALE_CHOICES[-1])
        ttk.Combobox(controls, textvariable=self._scale, state="readonly",
                     values=SCALE_CHOICES, width=4).pack(side="left", padx=4)

        self._engine = tk.StringVar(value="onnx")
        ttk.Combobox(controls, textvariable=self._engine, state="readonly",
                     values=ENGINE_CHOICES, width=8).pack(side="left", padx=4)

        self._run_button = ttk.Button(controls, text="업스케일", command=self._run)
        self._run_button.pack(side="left")

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._log = tk.Text(self, height=6)
        apply_log_colors(self._log)
        self._log.insert(
            "end", "첫 실행은 공식 가중치 다운로드(+onnx 엔진은 최초 1회 변환)로 "
                   "시간이 걸릴 수 있습니다.\n")
        self._log.pack(fill="x", padx=4)
        self._view = ImageView(self)
        self._view.pack(fill="both", expand=True)

        self._runner = CliRunner(self, self._run_button, self._choose_button, self._progress)

    def _choose_file(self):
        path = filedialog.askopenfilename(filetypes=image_filetypes())
        if path:
            self._input_path = path
            self._log.insert("end", f"입력: {path}\n")

    def _run(self):
        if not self._input_path:
            self._log.insert("end", "이미지를 먼저 선택하세요\n")
            return
        scale = self._scale.get()
        engine = self._engine.get()
        self._runner.start(lambda: self._build_and_run(scale, engine),
                            self._on_success, self._on_error)

    def _build_and_run(self, scale, engine):
        output_path = os.path.join(self._runner.out_dir, "output.png")
        cmd = build_upscale_command(self._input_path, output_path, scale, engine)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
        return proc, output_path

    def _on_success(self, result):
        proc, output_path = result
        self._log.insert("end", proc.stdout)
        if proc.returncode != 0:
            self._log.insert("end", f"에러 (exit {proc.returncode}):\n{proc.stderr}\n")
            return
        after = cv2.imread(output_path)
        if after is None:
            self._log.insert("end", f"결과 파일을 못 읽음: {output_path}\n")
            return
        before = cv2.imread(self._input_path)
        if before is None:
            self._log.insert("end", f"원본 이미지를 못 읽음: {self._input_path}\n")
            return
        self._view.show(before, after)

    def _on_error(self, exc):
        self._log.insert("end", f"실행 실패: {exc}\n")


def build_tab(master):
    return UpscaleTab(master)
