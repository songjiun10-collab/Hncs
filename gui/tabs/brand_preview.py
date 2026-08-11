"""브랜드 Look 미리보기 탭 - brands/*.py의 apply_*()를 이미지 하나에
직접 적용해서 Before/After로 보여준다."""
import ast
import glob
import importlib
import os
import tkinter as tk
from tkinter import filedialog, ttk

import cv2

from gui.widgets.image_view import (
    RAW_EXTS, ImageView, image_and_raw_filetypes, quick_raw_preview,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def list_shipped_looks():
    """brands/*.py에서 apply_*() 함수 목록을 ast로 스캔한다(video_frame
    변형 제외) - .claude/skills/run-hncs/driver.py의 shipped_looks()와
    같은 방식, 별도 레지스트리를 새로 두지 않는다."""
    out = []
    for path in sorted(glob.glob(os.path.join(_ROOT, "brands", "*.py"))):
        module = "brands." + os.path.basename(path)[:-3]
        if module.endswith("__init__"):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in tree.body:
            if (isinstance(node, ast.FunctionDef) and node.name.startswith("apply_")
                    and "video_frame" not in node.name):
                out.append((module, node.name))
    return out


def load_image(path):
    """RAW 확장자(RAW_EXTS)면 quick_raw_preview()로, 아니면 cv2.imread로
    읽는다 - hybrid_convert/raw_pipeline_tab의 RAW 분기와 동일한
    RAW_EXTS를 재사용."""
    if os.path.splitext(path)[1].lower() in RAW_EXTS:
        return quick_raw_preview(path)
    return cv2.imread(path)


def run_brand_preview(module_name, func_name, img):
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    return func(img)


class BrandPreviewTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._looks = list_shipped_looks()
        self._path = None

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=4, pady=4)
        ttk.Button(controls, text="이미지 선택", command=self._choose_file).pack(side="left")

        initial = f"{self._looks[0][0]}.{self._looks[0][1]}" if self._looks else ""
        self._choice = tk.StringVar(value=initial)
        self._combo = ttk.Combobox(
            controls, textvariable=self._choice, state="readonly",
            values=[f"{m}.{f}" for m, f in self._looks])
        self._combo.pack(side="left", padx=4)
        ttk.Button(controls, text="적용", command=self._apply).pack(side="left")

        self._status = ttk.Label(self, text="")
        self._status.pack(fill="x", padx=4)
        self._view = ImageView(self)
        self._view.pack(fill="both", expand=True)

    def _choose_file(self):
        path = filedialog.askopenfilename(filetypes=image_and_raw_filetypes())
        if path:
            self._path = path
            self._status.configure(text=path)

    def _apply(self):
        if not self._path:
            self._status.configure(text="이미지를 먼저 선택하세요")
            return
        module_name, func_name = self._choice.get().rsplit(".", 1)
        try:
            img = load_image(self._path)
        except Exception as exc:
            self._status.configure(text=f"이미지를 못 읽음: {exc}")
            return
        if img is None:
            self._status.configure(text=f"이미지를 못 읽음: {self._path}")
            return
        try:
            result = run_brand_preview(module_name, func_name, img)
        except Exception as exc:
            self._status.configure(text=f"에러: {exc}")
            return
        self._view.show(img, result)
        self._status.configure(text=f"{self._path} -> {self._choice.get()}")


def build_tab(master):
    return BrandPreviewTab(master)
