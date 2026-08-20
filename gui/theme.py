"""전체 앱 다크(블랙) 테마. ttk 위젯은 apply_dark_theme()가 ttk.Style로
한 곳에서 처리한다 - classic tk 위젯(Text 등)은 ttk.Style이 안 먹어서
탭들이 이 모듈의 색상 상수를 직접 가져다 쓴다."""
from tkinter import ttk

BG = "#1a1a1a"
BG_ALT = "#242424"
FG = "#e6e6e6"
ACCENT = "#3b82f6"
LOG_BG = "#111111"
LOG_FG = "#d0d0d0"


def apply_dark_theme(root):
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_ALT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TButton", background=BG_ALT, foreground=FG)
    style.map("TButton", background=[("active", ACCENT)], foreground=[("active", "#ffffff")])
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.configure("TCombobox", fieldbackground=BG_ALT, background=BG_ALT, foreground=FG)
    style.configure("TEntry", fieldbackground=BG_ALT, foreground=FG)
    style.configure("TScale", background=BG)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_ALT, foreground=FG, padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=BG_ALT)


def apply_log_colors(text_widget):
    """tk.Text 로그창 하나에 다크 팔레트 적용 - ttk.Style이 안 닿는
    classic tk 위젯이라 탭마다 직접 호출해야 한다."""
    text_widget.configure(bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG,
                           relief="flat", highlightthickness=0)
