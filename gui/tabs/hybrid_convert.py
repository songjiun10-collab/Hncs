"""hybrid_engine 변환 탭 - JPEG면 hybrid_engine.convert, RAW면
hybrid_engine.main을 그대로 subprocess로 실행한다(로직 재구현 없음)."""
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import cv2

from gui.widgets.image_view import RAW_EXTS, ImageView, quick_raw_preview

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROFILES_DIR = os.path.join(_ROOT, "hybrid_engine", "assets", "profiles")

AUTO_LABEL = "자동인식 (EXIF)"


def is_raw_input(path):
    return os.path.splitext(path)[1].lower() in RAW_EXTS


def list_jpeg_targets():
    from hybrid_engine.core.preset_inverse import TARGET_FUNCS
    return sorted(TARGET_FUNCS)


def list_jpeg_sources():
    from hybrid_engine.core.preset_inverse import BRAND_FUNCS
    return sorted(BRAND_FUNCS)


def list_raw_profiles():
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(_PROFILES_DIR)
        if name.endswith(".json"))


def build_hybrid_convert_command(input_path, output_path, target, source_override=None,
                                  python_exe=None):
    python_exe = python_exe or sys.executable
    if is_raw_input(input_path):
        cmd = [python_exe, "-m", "hybrid_engine.main", input_path, output_path]
        if target and target != AUTO_LABEL:
            cmd += ["--profile", target]
        return cmd
    cmd = [python_exe, "-m", "hybrid_engine.convert", input_path, output_path,
           "--target", target]
    if source_override and source_override != AUTO_LABEL:
        cmd += ["--source", source_override]
    return cmd


class HybridConvertTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._input_path = None

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=4, pady=4)
        ttk.Button(controls, text="입력 파일 선택", command=self._choose_file).pack(side="left")

        self._target = tk.StringVar()
        self._target_combo = ttk.Combobox(controls, textvariable=self._target, state="readonly")
        self._target_combo.pack(side="left", padx=4)

        self._source = tk.StringVar(value=AUTO_LABEL)
        self._source_combo = ttk.Combobox(controls, textvariable=self._source, state="readonly")
        self._source_combo.pack(side="left", padx=4)

        self._run_button = ttk.Button(controls, text="변환", command=self._run)
        self._run_button.pack(side="left")

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._log = tk.Text(self, height=6)
        self._log.pack(fill="x", padx=4)
        self._view = ImageView(self)
        self._view.pack(fill="both", expand=True)

    def _choose_file(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        self._input_path = path
        if is_raw_input(path):
            self._target_combo.configure(values=[AUTO_LABEL] + list_raw_profiles())
            self._source_combo.configure(values=[AUTO_LABEL], state="disabled")
            self._source.set(AUTO_LABEL)
        else:
            self._target_combo.configure(values=list_jpeg_targets())
            self._source_combo.configure(values=[AUTO_LABEL] + list_jpeg_sources(),
                                          state="readonly")
        self._log.insert("end", f"입력: {path}\n")

    def _run(self):
        if not self._input_path:
            self._log.insert("end", "입력 파일을 먼저 선택하세요\n")
            return
        target = self._target.get()
        source = self._source.get()
        self._run_button.configure(state="disabled")
        self._progress.pack(fill="x", padx=4)
        self._progress.start()
        threading.Thread(target=self._run_worker, args=(target, source), daemon=True).start()

    def _run_worker(self, target, source):
        out_dir = tempfile.mkdtemp(prefix="hncs_gui_")
        output_path = os.path.join(out_dir, "output.jpg")
        cmd = build_hybrid_convert_command(self._input_path, output_path, target, source)
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
        after = cv2.imread(output_path)
        if after is None:
            self._log.insert("end", f"결과 파일을 못 읽음: {output_path}\n")
            return
        if is_raw_input(self._input_path):
            before = quick_raw_preview(self._input_path)
        else:
            before = cv2.imread(self._input_path)
        self._view.show(before, after)


def build_tab(master):
    return HybridConvertTab(master)
