"""HNCS GUI 메인 윈도우 - ttk.Notebook에 tabs/ 각 모듈의 build_tab()을 등록한다."""
import tkinter as tk
from tkinter import ttk

from gui.tabs import brand_preview, hybrid_convert, lens_correction_tab, raw_pipeline_tab
from gui.theme import apply_dark_theme

TABS = [
    ("브랜드 Look", brand_preview.build_tab),
    ("hybrid_engine 변환", hybrid_convert.build_tab),
    ("RAW→Log", raw_pipeline_tab.build_tab),
    ("렌즈 보정", lens_correction_tab.build_tab),
]


def build_app(root):
    apply_dark_theme(root)
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)
    for label, build_tab in TABS:
        frame = build_tab(notebook)
        notebook.add(frame, text=label)
    return notebook


def main():
    root = tk.Tk()
    root.title("HNCS GUI")
    root.geometry("1000x700")
    build_app(root)
    root.mainloop()
