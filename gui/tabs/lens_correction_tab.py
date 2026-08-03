"""렌즈 왜곡 보정 탭 - tools.lens_correction을 subprocess로 실행한다.
EXIF는 미리 읽어서 화면에 보여주고, 없는 값만 수동 입력을 받는다."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import cv2

from gui.widgets.image_view import RAW_EXTS, ImageView, quick_raw_preview

_EXIF_TAGS = ["Make", "Model", "LensModel", "LensID", "LensInfo",
              "FocalLength", "FNumber", "ApertureValue"]


def read_exif_fields(path):
    """tools/lens_correction.py의 _read_exif()와 동일한 exiftool 호출 -
    make/model/lens/focal_length/aperture가 EXIF에 있으면 채워서 반환,
    없으면 해당 키를 생략한다."""
    out = subprocess.run(
        ["exiftool", "-json"] + [f"-{t}" for t in _EXIF_TAGS] + [path],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or not out.stdout.strip():
        return {}
    exif = json.loads(out.stdout)[0]
    fields = {}
    if exif.get("Make"):
        fields["make"] = exif["Make"]
    if exif.get("Model"):
        fields["model"] = exif["Model"]
    lens = exif.get("LensModel") or exif.get("LensID") or exif.get("LensInfo")
    if lens:
        fields["lens"] = lens
    if "FocalLength" in exif:
        fields["focal_length"] = str(exif["FocalLength"]).split()[0]
    if "FNumber" in exif or "ApertureValue" in exif:
        fields["aperture"] = str(exif.get("FNumber", exif.get("ApertureValue")))
    return fields


def build_lens_correction_command(input_path, output_path, make=None, model=None, lens=None,
                                   focal_length=None, aperture=None, python_exe=None):
    python_exe = python_exe or sys.executable
    cmd = [python_exe, "-m", "tools.lens_correction", input_path, output_path]
    if make:
        cmd += ["--make", make]
    if model:
        cmd += ["--model", model]
    if lens:
        cmd += ["--lens", lens]
    if focal_length:
        cmd += ["--focal-length", str(focal_length)]
    if aperture:
        cmd += ["--aperture", str(aperture)]
    return cmd


class LensCorrectionTab(ttk.Frame):
    _FIELDS = ["make", "model", "lens", "focal_length", "aperture"]

    def __init__(self, master):
        super().__init__(master)
        self._input_path = None
        self._vars = {name: tk.StringVar() for name in self._FIELDS}

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=4, pady=4)
        ttk.Button(controls, text="이미지 선택", command=self._choose_file).pack(side="left")

        fields = ttk.Frame(self)
        fields.pack(fill="x", padx=4)
        for name in self._FIELDS:
            row = ttk.Frame(fields)
            row.pack(side="left", padx=4)
            ttk.Label(row, text=name).pack()
            ttk.Entry(row, textvariable=self._vars[name]).pack()

        self._run_button = ttk.Button(controls, text="보정", command=self._run)
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
        detected = read_exif_fields(path)
        for name in self._FIELDS:
            self._vars[name].set(detected.get(name, ""))
        self._log.insert("end", f"입력: {path} (EXIF 인식: {detected})\n")

    def _run(self):
        if not self._input_path:
            self._log.insert("end", "이미지를 먼저 선택하세요\n")
            return
        self._run_button.configure(state="disabled")
        self._progress.pack(fill="x", padx=4)
        self._progress.start()
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self):
        out_dir = tempfile.mkdtemp(prefix="hncs_gui_")
        output_path = os.path.join(out_dir, "output.jpg")
        values = {name: (self._vars[name].get() or None) for name in self._FIELDS}
        cmd = build_lens_correction_command(self._input_path, output_path, **values)
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
        ext = os.path.splitext(self._input_path)[1].lower()
        before = quick_raw_preview(self._input_path) if ext in RAW_EXTS else cv2.imread(
            self._input_path)
        self._view.show(before, after)


def build_tab(master):
    return LensCorrectionTab(master)
