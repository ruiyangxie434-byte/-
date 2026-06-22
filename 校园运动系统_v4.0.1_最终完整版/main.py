"""校园运动健康数据中台 v4.0。

SQLite 持久化、登录会话和角色权限均已接入主程序。GPS/手环入口仍为本地
演示模拟，界面会明确标注，避免把预留能力描述成已经上线的真实服务。
"""
from __future__ import annotations

import random
import sys
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
# ttkbootstrap 的 LabelFrame 名称指向经典 Tk 控件；改用支持主题与 padding 的 ttk 版本。
ttk.LabelFrame = ttk.Labelframe

from analytics import (
    CHECKIN_CATEGORIES,
    CHECKIN_METHODS,
    FATIGUE_LEVELS,
    GOALS,
    LOCATIONS,
    ROLES,
    SPORT_TYPES,
    bmi_level,
    calc_bmi,
    calculate_physical_test_score,
    class_statistics,
    diet_advice,
    estimate_calories,
    evaluate_physical_test,
    filter_records,
    leaderboard,
    personal_plan,
    predict_test_score,
    risk_warnings,
    summarize,
    summarize_by_sport,
    test_suggestion,
)
from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord, normalize_date, to_float, to_int
from auth_ui import LoginDialog, PasswordChangeDialog, VerificationDialog
from charts import ChartFrame, render_duration_bar, render_weight_line
from config import APP_TITLE, APP_VERSION, REPORT_DIR
from database import SettingsDAO, close_conn, init_db, migrate_from_csv, table_count
from export import export_health_report_txt, export_sport_excel
from importer import import_file
from repositories import (
    HealthLogRepository,
    PhysicalTestRepository,
    ProfileRepository,
    SportRepository,
    backup_database,
)
from services import AdminSettingsService, AuthService, SportService

COLORS = {
    "bg": "#F4F7FC",
    "panel": "#F7F9FC",
    "card": "#FFFFFF",
    "primary": "#165DFF",
    "primary_dark": "#0E42D2",
    "primary_soft": "#E8F3FF",
    "accent": "#00B8A9",
    "accent_soft": "#E8FFFB",
    "warning": "#FF7D00",
    "warning_soft": "#FFF7E8",
    "danger": "#F53F3F",
    "danger_soft": "#FFECE8",
    "success": "#00B42A",
    "success_soft": "#E8FFEA",
    "text": "#17233D",
    "text_secondary": "#4E5969",
    "muted": "#86909C",
    "border": "#D8E2F2",
    "table_alt": "#F7FAFF",
    "sidebar": "#0F1F3D",
    "sidebar_hover": "#18345F",
}

FONT = "Microsoft YaHei UI"


class ScrollFrame(ttk.Frame):
    """可滚动容器，解决功能多时窗口放不下的问题。"""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class SportApp:
    def __init__(self, root: tk.Tk, current_user: dict):
        self.root = root
        self.current_user = current_user
        self.current_role = str(current_user["role"])
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 720)
        self.root.configure(bg=COLORS["bg"])

        self.profile_store = ProfileRepository(current_user)
        self.sport_store = SportRepository(current_user)
        self.health_store = HealthLogRepository(current_user)
        self.test_store = PhysicalTestRepository(current_user)
        self.settings_store = SettingsDAO()
        self.auth_service = AuthService(current_user)
        self.sport_service = SportService(current_user)
        self.admin_settings_service = AdminSettingsService(current_user)
        self.switch_requested = False

        self.profile = self.profile_store.load()
        self.all_records: list[SportRecord] = []
        self.visible_records: list[SportRecord] = []
        self.health_logs: list[HealthLog] = []
        self.tests: list[PhysicalTestRecord] = []
        self.card_vars: dict[str, tk.StringVar] = {}
        self.sport_page = 1
        self.sport_page_size = 40
        self.sport_total = 0
        self._chart_signature: tuple | None = None
        self.config_points = self.settings_store.get("locations", LOCATIONS.copy())
        self.blacklist: set[str] = set(self.settings_store.get("blacklist", []))

        self._setup_style()
        self._build_ui()
        self._apply_role_permissions()
        self.refresh_all()
        self.root.protocol("WM_DELETE_WINDOW", self._close_app)

    # ------------------------------------------------------------------
    # 基础样式和布局
    # ------------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("flatly")
        except tk.TclError:
            pass

        default_font = (FONT, 11)
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Card.TFrame", background=COLORS["card"], relief="flat", borderwidth=0)
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text_secondary"], font=default_font)
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text_secondary"], font=default_font)
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT, 10))
        style.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=(FONT, 11, "bold"))
        style.configure("CardValue.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=(FONT, 22, "bold"))
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=(FONT, 25, "bold"))
        style.configure("SubTitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT, 11))
        style.configure("TLabelframe", background=COLORS["card"], borderwidth=0, relief="flat")
        style.configure("TLabelframe.Label", background=COLORS["card"], foreground=COLORS["text"], font=(FONT, 12, "bold"))
        style.configure("TEntry", padding=9, fieldbackground="white", bordercolor=COLORS["border"], font=default_font)
        style.configure("TCombobox", padding=9, fieldbackground="white", bordercolor=COLORS["border"], font=default_font)
        style.map("TEntry", bordercolor=[("focus", COLORS["primary"]), ("!focus", COLORS["border"])])
        style.map("TCombobox", bordercolor=[("focus", COLORS["primary"]), ("!focus", COLORS["border"])])
        style.configure("TButton", font=(FONT, 10), padding=(14, 8), borderwidth=0)
        style.configure("Primary.TButton", font=(FONT, 10, "bold"), padding=(16, 9), foreground="white", background=COLORS["primary"])
        style.map("Primary.TButton", background=[("active", COLORS["primary_dark"]), ("pressed", COLORS["primary_dark"])])
        style.configure("Success.TButton", font=(FONT, 10, "bold"), padding=(16, 9), foreground="white", background=COLORS["success"])
        style.map("Success.TButton", background=[("active", "#009A29")])
        style.configure("Danger.TButton", font=(FONT, 10, "bold"), padding=(16, 9), foreground="white", background=COLORS["danger"])
        style.map("Danger.TButton", background=[("active", "#D82C2C")])
        style.configure("Outline.TButton", font=(FONT, 10), padding=(14, 8), foreground=COLORS["primary"], background="white", bordercolor=COLORS["primary"], borderwidth=1)
        style.map("Outline.TButton", background=[("active", COLORS["primary_soft"])])
        style.configure("Treeview", font=(FONT, 10), rowheight=38, background="white", fieldbackground="white", borderwidth=0)
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"), background=COLORS["primary"], foreground="white", padding=10, relief="flat")
        style.map("Treeview", background=[("selected", "#D6E4FF")], foreground=[("selected", COLORS["text"])])
        style.configure("Hidden.TNotebook", background=COLORS["bg"], borderwidth=0)
        style.layout("Hidden.TNotebook.Tab", [])
        style.configure("Horizontal.TProgressbar", background=COLORS["accent"], troughcolor="#E5EAF2", borderwidth=0)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=0)
        container.pack(fill="both", expand=True)
        self._build_header(container)

        body = ttk.Frame(container)
        body.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(body, bg=COLORS["sidebar"], width=220)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="◈  CAMPUS FIT", bg=COLORS["sidebar"], fg="white",
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=22, pady=(24, 6))
        tk.Label(self.sidebar, text="校园运动健康数据中台", bg=COLORS["sidebar"], fg="#8FA7C9",
                 font=(FONT, 9)).pack(anchor="w", padx=22, pady=(0, 22))
        self.nav_container = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        self.nav_container.pack(fill="x")
        tk.Label(self.sidebar, text=f"SECURE · SQLite  /  v{APP_VERSION}",
                 bg=COLORS["sidebar"], fg="#6680A8", font=("Consolas", 8)).pack(
                     side="bottom", anchor="w", padx=22, pady=18
                 )

        content_shell = tk.Frame(body, bg=COLORS["bg"])
        content_shell.pack(side="right", fill="both", expand=True)
        self.notebook = ttk.Notebook(content_shell, style="Hidden.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=14, pady=12)

        self.tabs: dict[str, ttk.Frame] = {}
        self.tab_frames: dict[str, ttk.Frame] = {}
        self.tab_scrolls: dict[str, ScrollFrame] = {}
        for key, title in [
            ("dashboard", "数据首页"),
            ("student", "学生端打卡"),
            ("profile", "健康档案"),
            ("health", "健康自测"),
            ("analysis", "智能分析"),
            ("teacher", "教师端"),
            ("admin", "管理员端"),
            ("social", "社交激励/体测"),
        ]:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=title)
            scroll = ScrollFrame(tab)
            scroll.pack(fill="both", expand=True)
            content = scroll.inner
            content.configure(padding=14)
            self.tab_frames[key] = tab
            self.tab_scrolls[key] = scroll
            self.tabs[key] = content

        self._build_dashboard_tab(self.tabs["dashboard"])
        self._build_student_tab(self.tabs["student"])
        self._build_profile_tab(self.tabs["profile"])
        self._build_health_tab(self.tabs["health"])
        self._build_analysis_tab(self.tabs["analysis"])
        self._build_teacher_tab(self.tabs["teacher"])
        self._build_admin_tab(self.tabs["admin"])
        self._build_social_tab(self.tabs["social"])

    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Canvas(parent, height=96, bg=COLORS["primary"], highlightthickness=0)
        header.pack(fill="x")
        header.create_text(28, 32, text="校园运动健康数据中台", anchor="w", fill="white",
                           font=(FONT, 22, "bold"), tags=("content",))
        header.create_text(30, 66, text="DATA · HEALTH · SPORTS · GOVERNANCE", anchor="w",
                           fill="#DDE8FF", font=("Consolas", 9), tags=("content",))
        self.role_var = tk.StringVar(value=self.profile.role)
        right = tk.Frame(header, bg="#2B6BEE", padx=10, pady=8)
        tk.Label(right, text=f"●  {self.profile.name}", bg="#2B6BEE", fg="white",
                 font=(FONT, 10, "bold")).pack(side="left", padx=(2, 10))
        tk.Label(right, text=self.profile.role, bg="#2B6BEE", fg="#DDE8FF",
                 font=(FONT, 9)).pack(side="left", padx=(0, 12))
        button_kw = dict(bg="#2B6BEE", fg="white", activebackground="#0E42D2",
                         activeforeground="white", relief="flat", cursor="hand2",
                         font=(FONT, 9), padx=8, pady=5)
        self.backup_button = tk.Button(right, text="⟳ 备份", command=self.backup_data, **button_kw)
        self.backup_button.pack(side="left", padx=2)
        tk.Button(right, text="⇩ 导出", command=self.export_report, **button_kw).pack(side="left", padx=2)
        tk.Button(right, text="🔐 改密", command=self.change_password, **button_kw).pack(side="left", padx=2)
        tk.Button(right, text="⇄ 切换账号", command=self.switch_account, **button_kw).pack(side="left", padx=2)
        self._header_right_window = header.create_window(0, 48, window=right, anchor="e", tags=("content",))
        header.bind("<Configure>", self._draw_header_gradient)

    def _draw_header_gradient(self, event: tk.Event) -> None:
        canvas = event.widget
        canvas.delete("gradient")
        start = (22, 93, 255)
        end = (36, 184, 169)
        width = max(1, event.width)
        for x in range(0, width, 4):
            ratio = x / width
            color = "#%02x%02x%02x" % tuple(
                int(start[i] + (end[i] - start[i]) * ratio) for i in range(3)
            )
            canvas.create_rectangle(x, 0, x + 4, 96, fill=color, outline=color, tags=("gradient",))
        canvas.tag_lower("gradient")
        canvas.coords(self._header_right_window, width - 22, 48)

    def _apply_role_permissions(self) -> None:
        allowed = {
            "student": ["dashboard", "student", "profile", "health", "analysis", "social"],
            "teacher": ["dashboard", "analysis", "teacher", "social"],
            "admin": ["dashboard", "teacher", "admin", "social"],
        }.get(self.current_role, ["dashboard"])
        for key, tab in self.tab_frames.items():
            if key not in allowed:
                self.notebook.hide(tab)
        labels = {
            "dashboard": ("▦", "数据总览"), "student": ("✚", "运动打卡"),
            "profile": ("♙", "健康档案"), "health": ("♥", "健康自测"),
            "analysis": ("⌁", "规则分析"), "teacher": ("✓", "教师审核"),
            "admin": ("⚙", "系统管理"), "social": ("★", "排行与体测"),
        }
        self.nav_items: dict[str, tuple[tk.Frame, tk.Frame, tk.Button]] = {}
        for key in allowed:
            row = tk.Frame(self.nav_container, bg=COLORS["sidebar"], height=48)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)
            indicator = tk.Frame(row, bg=COLORS["sidebar"], width=4)
            indicator.pack(side="left", fill="y")
            icon, title = labels[key]
            button = tk.Button(row, text=f"  {icon}    {title}", anchor="w",
                               bg=COLORS["sidebar"], fg="#B8C8E1", activebackground=COLORS["sidebar_hover"],
                               activeforeground="white", relief="flat", bd=0, cursor="hand2",
                               font=(FONT, 10, "bold"), command=lambda k=key: self._show_page(k))
            button.pack(side="left", fill="both", expand=True)
            button.bind("<Enter>", lambda _e, k=key: self._nav_hover(k, True))
            button.bind("<Leave>", lambda _e, k=key: self._nav_hover(k, False))
            self.nav_items[key] = (row, indicator, button)
        if self.current_role != "admin":
            self.backup_button.pack_forget()
        self._show_page(allowed[0])

    def _show_page(self, key: str) -> None:
        self.active_page = key
        self.notebook.select(self.tab_frames[key])
        for item_key, (row, indicator, button) in self.nav_items.items():
            active = item_key == key
            color = COLORS["sidebar_hover"] if active else COLORS["sidebar"]
            row.configure(bg=color)
            indicator.configure(bg=COLORS["primary"] if active else COLORS["sidebar"])
            button.configure(bg=color, fg="white" if active else "#B8C8E1")

    def _nav_hover(self, key: str, entered: bool) -> None:
        if key == getattr(self, "active_page", None):
            return
        row, _indicator, button = self.nav_items[key]
        color = COLORS["sidebar_hover"] if entered else COLORS["sidebar"]
        row.configure(bg=color)
        button.configure(bg=color)

    def _require_role(self, *roles: str) -> bool:
        if self.current_role in roles:
            return True
        messagebox.showerror("权限不足", "当前账号没有执行此操作的权限。")
        return False

    def _close_app(self) -> None:
        close_conn()
        self.root.destroy()

    def _card(self, parent: ttk.Frame, key: str, title: str, value: str, col: int) -> None:
        shadow = tk.Frame(parent, bg="#DCE5F3")
        shadow.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 12, 0), pady=(0, 12))
        parent.columnconfigure(col, weight=1)
        palettes = [
            ("#165DFF", "#6F9EFF", "✓"), ("#00A6A6", "#5DD9CA", "◷"),
            ("#6B4EFF", "#A58BFF", "◆"), ("#FF7D00", "#FFB55C", "↟"),
            ("#14A46D", "#67D4A3", "♥"), ("#F53F3F", "#FF8585", "!"),
        ]
        start, end, icon = palettes[col % len(palettes)]
        canvas = tk.Canvas(shadow, height=112, bg=start, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        var = tk.StringVar(value=value)
        self.card_vars[key] = var
        canvas.create_text(18, 25, text=title, anchor="w", fill="#EAF1FF",
                           font=(FONT, 10, "bold"), tags=("card_content",))
        value_item = canvas.create_text(18, 73, text=value, anchor="w", fill="white",
                                        font=(FONT, 21, "bold"), tags=("card_content",))
        canvas.create_text(0, 55, text=icon, anchor="center", fill="#FFFFFF",
                           font=(FONT, 28, "bold"), tags=("card_icon",))
        var.trace_add("write", lambda *_args, item=value_item, target=canvas, v=var: target.itemconfigure(item, text=v.get()))

        def redraw(event: tk.Event, target=canvas, c1=start, c2=end) -> None:
            target.delete("card_gradient")
            a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
            b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
            for x in range(0, max(1, event.width), 3):
                ratio = x / max(1, event.width)
                color = "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
                target.create_rectangle(x, 0, x + 3, event.height, fill=color, outline=color,
                                        tags=("card_gradient",))
            target.tag_lower("card_gradient")
            target.coords("card_icon", event.width - 34, 55)

        canvas.bind("<Configure>", redraw)

    def _make_tree(self, parent: ttk.Frame, columns: tuple[str, ...], widths: dict[str, int], height: int = 8) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 120), anchor="center")
        tree.tag_configure("even", background="white")
        tree.tag_configure("odd", background=COLORS["table_alt"])
        tree.tag_configure("approved", foreground="#008F2D")
        tree.tag_configure("pending", foreground="#D86B00")
        tree.tag_configure("rejected", foreground="#D82C2C")
        tree.tag_configure("hover", background="#E8F3FF")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        hover_state = {"item": ""}

        def on_motion(event: tk.Event) -> None:
            item = tree.identify_row(event.y)
            previous = hover_state["item"]
            if previous and tree.exists(previous):
                tree.item(previous, tags=tuple(tag for tag in tree.item(previous, "tags") if tag != "hover"))
            if item and tree.exists(item):
                tree.item(item, tags=(*tree.item(item, "tags"), "hover"))
            hover_state["item"] = item

        tree.bind("<Motion>", on_motion)
        return tree

    def _form_field(self, parent: ttk.Frame, label: str, var: tk.StringVar, row: int, col: int, values: list[str] | None = None, width: int = 16):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=8, pady=(8, 4))
        error_var = tk.StringVar()
        tk.Label(parent, textvariable=error_var, bg=COLORS["card"], fg=COLORS["danger"],
                 font=(FONT, 8)).grid(row=row, column=col, sticky="e", padx=8, pady=(8, 4))
        if values is None:
            widget = ttk.Entry(parent, textvariable=var, width=width)
        else:
            widget = ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly")
        widget.grid(row=row + 1, column=col, sticky="ew", padx=8, pady=(0, 6))
        parent.columnconfigure(col, weight=1)
        numeric_fields = {
            "时长(分钟)", "距离(km)", "步数", "心率", "体重(kg)", "身高(cm)",
            "体脂率(%)", "肺活量", "周运动目标", "每日步数目标", "晨起体重",
            "睡眠时长", "当日心率", "年份", "跑步单项分", "立定跳远(cm)",
            "坐位体前屈(cm)", "总分", "最短有效时长",
            "基础积分", "每积分分钟数", "单次奖励阈值", "单次奖励积分",
            "满额时长阈值", "满额奖励积分",
        }
        if values is None and label in numeric_fields:
            def allow_number(candidate: str) -> bool:
                if candidate in {"", "-", ".", "-."}:
                    return True
                try:
                    float(candidate)
                    return True
                except ValueError:
                    return False
            widget.configure(validate="key", validatecommand=(self.root.register(allow_number), "%P"))

        def validate_inline(_event=None) -> None:
            value = var.get().strip()
            error = ""
            try:
                if label in numeric_fields and value:
                    number = float(value)
                    if label in {"心率", "当日心率"} and number != 0 and not 30 <= number <= 240:
                        error = "范围 30-240"
                    elif label in {"体重(kg)", "晨起体重"} and not 20 <= number <= 300:
                        error = "范围 20-300"
                    elif label == "身高(cm)" and not 100 <= number <= 250:
                        error = "范围 100-250"
                    elif label == "总分" and not 0 <= number <= 100:
                        error = "范围 0-100"
                if label in {"日期", "开始日期", "结束日期", "有效期"} and value:
                    normalize_date(value)
            except ValueError:
                error = "格式不正确"
            error_var.set(error)

        widget.bind("<FocusOut>", validate_inline, add="+")
        return widget

    # ------------------------------------------------------------------
    # 数据首页
    # ------------------------------------------------------------------
    def _build_dashboard_tab(self, parent: ttk.Frame) -> None:
        cards = ttk.Frame(parent)
        cards.pack(fill="x")
        for i, item in enumerate([
            ("count", "有效打卡", "0 次"),
            ("duration", "累计时长", "0 分钟"),
            ("calories", "累计消耗", "0 kcal"),
            ("steps", "累计步数", "0 步"),
            ("bmi", "BMI 状态", "暂无"),
            ("pending", "待审批", "0 条"),
        ]):
            self._card(cards, item[0], item[1], item[2], i)

        middle = ttk.Frame(parent)
        middle.pack(fill="both", expand=True, pady=(8, 0))
        left = ttk.LabelFrame(middle, text="  综合统计与目标进度  ", padding=14)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.dashboard_summary = tk.StringVar(value="暂无统计")
        ttk.Label(left, textvariable=self.dashboard_summary, justify="left", font=(FONT, 12)).pack(anchor="w")
        self.progress_var = tk.IntVar(value=0)
        ttk.Progressbar(left, variable=self.progress_var, maximum=100).pack(fill="x", pady=(14, 4))
        self.progress_text = tk.StringVar(value="目标进度：0%")
        ttk.Label(left, textvariable=self.progress_text, style="Muted.TLabel").pack(anchor="w")

        chart_box = ttk.LabelFrame(middle, text="  最近 7 天运动时长趋势  ", padding=14)
        chart_box.pack(side="right", fill="both", expand=True, padx=(10, 0))
        self.sport_chart = ChartFrame(chart_box, figsize=(5.6, 2.5))
        self.sport_chart.pack(fill="both", expand=True)

        table_box = ttk.LabelFrame(parent, text="  最新打卡记录  ", padding=12)
        table_box.pack(fill="both", expand=True, pady=(14, 0))
        columns = ("序号", "姓名", "班级", "日期", "类型", "分类", "方式", "地点", "时长", "状态")
        widths = {"序号": 60, "姓名": 100, "班级": 210, "日期": 120, "类型": 90, "分类": 110, "方式": 120, "地点": 120, "时长": 90, "状态": 90}
        self.latest_tree = self._make_tree(table_box, columns, widths, height=7)

    # ------------------------------------------------------------------
    # 学生端
    # ------------------------------------------------------------------
    def _build_student_tab(self, parent: ttk.Frame) -> None:
        form = ttk.LabelFrame(parent, text="  运动打卡录入：支持 GPS 实景 / 手动录入 / 设备同步 / 补卡申请  ", padding=14)
        form.pack(fill="x", pady=(0, 12))
        self.sport_vars = {
            "学号": tk.StringVar(value=self.profile.student_id),
            "姓名": tk.StringVar(value=self.profile.name),
            "班级": tk.StringVar(value=self.profile.class_name),
            "日期": tk.StringVar(value=str(date.today())),
            "运动类型": tk.StringVar(value="足球"),
            "打卡分类": tk.StringVar(value="球类"),
            "打卡方式": tk.StringVar(value="手动录入"),
            "地点": tk.StringVar(value="校园操场"),
            "时长(分钟)": tk.StringVar(),
            "距离(km)": tk.StringVar(value="0"),
            "步数": tk.StringVar(value="0"),
            "心率": tk.StringVar(value="0"),
            "体重(kg)": tk.StringVar(value=str(self.profile.weight)),
            "备注/凭证": tk.StringVar(),
        }
        fields = [
            ("学号", None), ("姓名", None), ("班级", None), ("日期", None),
            ("运动类型", SPORT_TYPES), ("打卡分类", CHECKIN_CATEGORIES), ("打卡方式", CHECKIN_METHODS), ("地点", self.config_points),
            ("时长(分钟)", None), ("距离(km)", None), ("步数", None), ("心率", None),
            ("体重(kg)", None), ("备注/凭证", None),
        ]
        for idx, (label, values) in enumerate(fields):
            widget = self._form_field(form, label, self.sport_vars[label], (idx // 4) * 2, idx % 4, values, width=19)
            if label in {"学号", "姓名", "班级", "体重(kg)"}:
                widget.configure(state="readonly")
        btns = ttk.Frame(form)
        btns.grid(row=8, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="保存正式打卡", style="Primary.TButton", command=self.add_sport_record).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="提交补卡申请", command=self.add_makeup_record).pack(side="left", padx=8)
        ttk.Button(btns, text="模拟手环/APP同步", command=self.sync_device_demo).pack(side="left", padx=8)
        ttk.Button(btns, text="今天日期", command=lambda: self.sport_vars["日期"].set(str(date.today()))).pack(side="left", padx=8)
        ttk.Button(btns, text="清空输入", command=self.clear_sport_form).pack(side="left", padx=8)

        filter_box = ttk.LabelFrame(parent, text="  打卡数据筛选  ", padding=12)
        filter_box.pack(fill="x", pady=(0, 12))
        self.filter_keyword = tk.StringVar()
        self.filter_sport = tk.StringVar(value="全部")
        self.filter_category = tk.StringVar(value="全部")
        self.filter_status = tk.StringVar(value="全部")
        self.filter_start = tk.StringVar()
        self.filter_end = tk.StringVar()
        filter_fields = [
            ("关键词", self.filter_keyword, None),
            ("运动类型", self.filter_sport, ["全部", *SPORT_TYPES]),
            ("打卡分类", self.filter_category, ["全部", *CHECKIN_CATEGORIES]),
            ("审核状态", self.filter_status, ["全部", "已通过", "待审批", "已驳回"]),
            ("开始日期", self.filter_start, None),
            ("结束日期", self.filter_end, None),
        ]
        for idx, (label, var, values) in enumerate(filter_fields):
            self._form_field(filter_box, label, var, 0, idx, values, width=14)
        ttk.Button(filter_box, text="应用筛选", style="Primary.TButton", command=self.apply_filters).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="重置筛选", command=self.reset_filters).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="删除选中", style="Danger.TButton", command=self.delete_selected).grid(row=2, column=2, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="导出当前 Excel", command=self.export_current_csv).grid(row=2, column=3, padx=8, pady=8, sticky="w")

        table_box = ttk.LabelFrame(parent, text="  打卡记录明细  ", padding=12)
        table_box.pack(fill="both", expand=True)
        columns = ("序号", "学号", "姓名", "班级", "日期", "类型", "分类", "方式", "地点", "时长", "距离", "步数", "心率", "热量", "状态")
        widths = {"序号": 60, "学号": 105, "姓名": 100, "班级": 210, "日期": 120, "类型": 90, "分类": 110, "方式": 120, "地点": 110, "时长": 90, "距离": 90, "步数": 90, "心率": 80, "热量": 100, "状态": 90}
        self.sport_tree = self._make_tree(table_box, columns, widths, height=10)
        page_bar = ttk.Frame(table_box, style="Card.TFrame")
        page_bar.pack(fill="x", pady=(8, 0))
        self.page_text = tk.StringVar(value="第 1 / 1 页 · 共 0 条")
        ttk.Button(page_bar, text="‹ 上一页", style="Outline.TButton", command=self.previous_page).pack(side="left")
        ttk.Label(page_bar, textvariable=self.page_text, style="CardTitle.TLabel").pack(side="left", padx=14)
        ttk.Button(page_bar, text="下一页 ›", style="Outline.TButton", command=self.next_page).pack(side="left")

    # ------------------------------------------------------------------
    # 健康档案
    # ------------------------------------------------------------------
    def _build_profile_tab(self, parent: ttk.Frame) -> None:
        info = ttk.LabelFrame(parent, text="  账号与个人健康档案：支持角色区分、体检数据存档、目标自定义  ", padding=16)
        info.pack(fill="x", pady=(0, 12))
        self.profile_vars = {
            "学号": tk.StringVar(value=self.profile.student_id),
            "姓名": tk.StringVar(value=self.profile.name),
            "角色": tk.StringVar(value=self.profile.role),
            "班级": tk.StringVar(value=self.profile.class_name),
            "性别": tk.StringVar(value=self.profile.gender),
            "身高(cm)": tk.StringVar(value=str(self.profile.height)),
            "体重(kg)": tk.StringVar(value=str(self.profile.weight)),
            "体脂率(%)": tk.StringVar(value=str(self.profile.body_fat)),
            "血压": tk.StringVar(value=self.profile.blood_pressure),
            "肺活量": tk.StringVar(value=str(self.profile.lung_capacity)),
            "既往伤病": tk.StringVar(value=self.profile.injuries),
            "过敏史": tk.StringVar(value=self.profile.allergies),
            "体检备注": tk.StringVar(value=self.profile.medical_note),
            "周运动目标": tk.StringVar(value=str(self.profile.weekly_target)),
            "每日步数目标": tk.StringVar(value=str(self.profile.step_goal)),
            "健身目标": tk.StringVar(value=self.profile.fitness_goal),
        }
        fields = [
            ("学号", None), ("姓名", None), ("角色", ROLES), ("班级", None),
            ("性别", ["男", "女"]), ("身高(cm)", None), ("体重(kg)", None), ("体脂率(%)", None),
            ("血压", None), ("肺活量", None), ("既往伤病", None), ("过敏史", None),
            ("体检备注", None), ("周运动目标", None), ("每日步数目标", None), ("健身目标", GOALS),
        ]
        for idx, (label, values) in enumerate(fields):
            widget = self._form_field(info, label, self.profile_vars[label], (idx // 4) * 2, idx % 4, values, width=20)
            if label in {"学号", "姓名", "角色"}:
                widget.configure(state="disabled" if label == "角色" else "readonly")
        ttk.Button(info, text="保存个人档案与目标", style="Primary.TButton", command=self.save_profile).grid(row=8, column=0, padx=8, pady=14, sticky="w")
        ttk.Button(info, text="同步到打卡表单", command=self.sync_profile_to_forms).grid(row=8, column=1, padx=8, pady=14, sticky="w")

        preview = ttk.LabelFrame(parent, text="  档案摘要  ", padding=16)
        preview.pack(fill="both", expand=True)
        self.profile_preview = tk.StringVar(value="暂无档案")
        ttk.Label(preview, textvariable=self.profile_preview, justify="left", font=(FONT, 13)).pack(anchor="nw")

    # ------------------------------------------------------------------
    # 健康自测
    # ------------------------------------------------------------------
    def _build_health_tab(self, parent: ttk.Frame) -> None:
        form = ttk.LabelFrame(parent, text="  日常健康自测：体重、睡眠、饮食、心率、疲劳、伤病、生理期备注  ", padding=16)
        form.pack(fill="x", pady=(0, 12))
        self.health_vars = {
            "学号": tk.StringVar(value=self.profile.student_id),
            "姓名": tk.StringVar(value=self.profile.name),
            "日期": tk.StringVar(value=str(date.today())),
            "晨起体重": tk.StringVar(value=str(self.profile.weight)),
            "睡眠时长": tk.StringVar(value="7"),
            "三餐饮食": tk.StringVar(value="正常三餐，蛋白质充足"),
            "当日心率": tk.StringVar(value="72"),
            "疲劳程度": tk.StringVar(value="正常"),
            "伤病记录": tk.StringVar(value="无"),
            "生理期备注": tk.StringVar(value=""),
        }
        fields = [
            ("学号", None), ("姓名", None), ("日期", None), ("晨起体重", None),
            ("睡眠时长", None), ("三餐饮食", None), ("当日心率", None), ("疲劳程度", FATIGUE_LEVELS),
            ("伤病记录", None), ("生理期备注", None),
        ]
        for idx, (label, values) in enumerate(fields):
            widget = self._form_field(form, label, self.health_vars[label], (idx // 4) * 2, idx % 4, values, width=20)
            if label in {"学号", "姓名"}:
                widget.configure(state="readonly")
        ttk.Button(form, text="保存健康自测", style="Primary.TButton", command=self.add_health_log).grid(row=6, column=0, padx=8, pady=12, sticky="w")
        ttk.Button(form, text="今天日期", command=lambda: self.health_vars["日期"].set(str(date.today()))).grid(row=6, column=1, padx=8, pady=12, sticky="w")
        ttk.Button(form, text="删除选中自测", style="Danger.TButton", command=self.delete_health_log).grid(row=6, column=2, padx=8, pady=12, sticky="w")

        table_box = ttk.LabelFrame(parent, text="  健康自测记录  ", padding=12)
        table_box.pack(fill="both", expand=True)
        columns = ("序号", "学号", "姓名", "日期", "体重", "睡眠", "饮食", "心率", "疲劳", "伤病", "生理期")
        widths = {"序号": 60, "学号": 110, "姓名": 100, "日期": 120, "体重": 80, "睡眠": 80, "饮食": 230, "心率": 80, "疲劳": 90, "伤病": 160, "生理期": 160}
        self.health_tree = self._make_tree(table_box, columns, widths, height=11)

    # ------------------------------------------------------------------
    # 智能分析
    # ------------------------------------------------------------------
    def _build_analysis_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="both", expand=True)
        left = ttk.LabelFrame(top, text="  风险预警 & 个性化运动方案 & 饮食建议 & 体测预判  ", padding=16)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.analysis_text = tk.Text(left, height=22, wrap="word", font=(FONT, 13), bg="white", fg=COLORS["text"], relief="solid", bd=1, padx=12, pady=12)
        self.analysis_text.pack(fill="both", expand=True)
        ttk.Button(left, text="刷新智能分析", style="Primary.TButton", command=self.refresh_all).pack(anchor="w", pady=(12, 0))

        right = ttk.LabelFrame(top, text="  BMI / 体重趋势  ", padding=16)
        right.pack(side="right", fill="both", expand=True, padx=(10, 0))
        self.weight_chart = ChartFrame(right, figsize=(5.5, 3.0))
        self.weight_chart.pack(fill="both", expand=True)
        self.analysis_hint = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.analysis_hint, justify="left", style="Muted.TLabel",
                  wraplength=520).pack(anchor="w", pady=(12, 0))

    # ------------------------------------------------------------------
    # 教师端
    # ------------------------------------------------------------------
    def _build_teacher_tab(self, parent: ttk.Frame) -> None:
        action = ttk.LabelFrame(parent, text="  体育教师端：班级管理、任务发布、异常审核、批量导出  ", padding=14)
        action.pack(fill="x", pady=(0, 12))
        self.teacher_task = tk.StringVar(value=self.settings_store.get("teacher_task", "每周 3 次 3km 跑步打卡"))
        self.teacher_deadline = tk.StringVar(value=self.settings_store.get("teacher_deadline", str(date.today())))
        self.teacher_location = tk.StringVar(value=self.settings_store.get("teacher_location", "校园操场"))
        self._form_field(action, "运动作业", self.teacher_task, 0, 0, None, width=26)
        self._form_field(action, "有效期", self.teacher_deadline, 0, 1, None, width=16)
        self._form_field(action, "打卡地点", self.teacher_location, 0, 2, self.config_points, width=16)
        ttk.Button(action, text="发布任务", style="Primary.TButton", command=self.publish_task).grid(row=2, column=0, padx=8, pady=10, sticky="w")
        ttk.Button(action, text="通过选中补卡", style="Success.TButton", command=lambda: self.review_selected("已通过")).grid(row=2, column=1, padx=8, pady=10, sticky="w")
        ttk.Button(action, text="驳回/作弊标记", style="Danger.TButton", command=lambda: self.review_selected("已驳回")).grid(row=2, column=2, padx=8, pady=10, sticky="w")
        ttk.Button(action, text="导出班级报表", command=self.export_class_report).grid(row=2, column=3, padx=8, pady=10, sticky="w")

        middle = ttk.Frame(parent)
        middle.pack(fill="both", expand=True)
        stat_box = ttk.LabelFrame(middle, text="  班级统计  ", padding=12)
        stat_box.pack(fill="both", expand=True, pady=(0, 10))
        columns = ("序号", "姓名", "班级", "有效次数", "总时长", "总热量", "待审批")
        widths = {"序号": 60, "姓名": 100, "班级": 220, "有效次数": 100, "总时长": 100, "总热量": 100, "待审批": 100}
        self.class_tree = self._make_tree(stat_box, columns, widths, height=7)

        pending_box = ttk.LabelFrame(middle, text="  补卡/异常审核  ", padding=12)
        pending_box.pack(fill="both", expand=True)
        columns = ("序号", "学号", "姓名", "日期", "类型", "方式", "地点", "时长", "备注", "状态")
        widths = {"序号": 60, "学号": 105, "姓名": 90, "日期": 115, "类型": 85, "方式": 120, "地点": 100, "时长": 80, "备注": 160, "状态": 90}
        self.pending_tree = self._make_tree(pending_box, columns, widths, height=7)

    # ------------------------------------------------------------------
    # 管理员端
    # ------------------------------------------------------------------
    def _build_admin_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 12))
        point_box = ttk.LabelFrame(top, text="  校园打卡点位设置 / 地标围栏模拟  ", padding=14)
        point_box.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.new_point = tk.StringVar()
        self._form_field(point_box, "新增点位", self.new_point, 0, 0, None, width=22)
        ttk.Button(point_box, text="添加点位", style="Primary.TButton", command=self.add_location_point).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ttk.Button(point_box, text="删除选中点位", style="Danger.TButton", command=self.delete_location_point).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        self.point_list = tk.Listbox(point_box, height=8, font=(FONT, 13), bg="white", selectbackground="#BFDBFE")
        self.point_list.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=8, pady=(8, 0))
        point_box.rowconfigure(3, weight=1)
        point_box.columnconfigure(2, weight=1)

        rule_box = ttk.LabelFrame(top, text="  打卡规则 / 权限 / 黑名单  ", padding=14)
        rule_box.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.min_duration_rule = tk.StringVar(value=str(self.settings_store.get("min_duration", 20)))
        score_rule = self.admin_settings_service.get_score_rule()
        self.score_rule_vars = {
            "base_points": tk.StringVar(value=str(score_rule["base_points"])),
            "minutes_per_point": tk.StringVar(value=str(score_rule["minutes_per_point"])),
            "session_bonus_threshold": tk.StringVar(value=str(score_rule["session_bonus_threshold"])),
            "session_bonus_points": tk.StringVar(value=str(score_rule["session_bonus_points"])),
            "full_bonus_threshold": tk.StringVar(value=str(score_rule["full_bonus_threshold"])),
            "full_bonus_points": tk.StringVar(value=str(score_rule["full_bonus_points"])),
        }
        self.black_id = tk.StringVar()
        self._form_field(rule_box, "最短有效时长", self.min_duration_rule, 0, 0, None, width=16)
        self._form_field(rule_box, "基础积分", self.score_rule_vars["base_points"], 0, 1, None, width=12)
        self._form_field(rule_box, "每积分分钟数", self.score_rule_vars["minutes_per_point"], 0, 2, None, width=12)
        self._form_field(rule_box, "单次奖励阈值", self.score_rule_vars["session_bonus_threshold"], 2, 0, None, width=12)
        self._form_field(rule_box, "单次奖励积分", self.score_rule_vars["session_bonus_points"], 2, 1, None, width=12)
        self._form_field(rule_box, "满额时长阈值", self.score_rule_vars["full_bonus_threshold"], 2, 2, None, width=12)
        self._form_field(rule_box, "满额奖励积分", self.score_rule_vars["full_bonus_points"], 4, 0, None, width=12)
        self._form_field(rule_box, "黑名单学号", self.black_id, 4, 1, None, width=16)
        ttk.Button(rule_box, text="加入黑名单", style="Danger.TButton", command=self.add_blacklist).grid(row=6, column=1, padx=8, pady=8, sticky="w")
        ttk.Button(rule_box, text="保存结构化规则", style="Primary.TButton", command=self.save_admin_rules).grid(row=6, column=0, padx=8, pady=8, sticky="w")

        overview = ttk.LabelFrame(parent, text="  全校大数据总览 / 年度报表摘要  ", padding=16)
        overview.pack(fill="both", expand=True, pady=(0, 12))
        self.admin_text = tk.Text(overview, height=10, wrap="word", font=(FONT, 11), bg="white", fg=COLORS["text_secondary"], relief="flat", padx=12, pady=12)
        self.admin_text.pack(fill="both", expand=True)

        users = ttk.LabelFrame(parent, text="  用户管理：新增 / 编辑 / 重置密码 / 启停账号  ", padding=14)
        users.pack(fill="both", expand=True)
        self.user_vars = {
            "账号": tk.StringVar(), "姓名": tk.StringVar(), "角色": tk.StringVar(value="student"),
            "班级": tk.StringVar(), "临时密码": tk.StringVar(value="123456"),
        }
        user_fields = [
            ("账号", None), ("姓名", None), ("角色", ["student", "teacher", "admin"]),
            ("班级", None), ("临时密码", None),
        ]
        for idx, (label, values) in enumerate(user_fields):
            self._form_field(users, label, self.user_vars[label], 0, idx, values, width=15)
        actions = ttk.Frame(users, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=5, sticky="w", padx=8, pady=8)
        ttk.Button(actions, text="新增用户", style="Primary.TButton", command=self.add_user).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="保存修改", style="Success.TButton", command=self.update_user).pack(side="left", padx=6)
        ttk.Button(actions, text="重置密码", style="Outline.TButton", command=self.reset_user_password).pack(side="left", padx=6)
        ttk.Button(actions, text="启用 / 禁用", style="Danger.TButton", command=self.toggle_user_active).pack(side="left", padx=6)
        self.import_type = tk.StringVar(value="学生名单")
        ttk.Combobox(actions, textvariable=self.import_type,
                     values=["学生名单", "运动记录", "体测成绩"], width=10,
                     state="readonly").pack(side="left", padx=(18, 4))
        ttk.Button(actions, text="批量导入 CSV/XLSX", style="Outline.TButton",
                   command=self.import_batch_data).pack(side="left", padx=4)
        user_columns = ("账号", "姓名", "角色", "班级", "状态", "初始密码")
        user_table = ttk.Frame(users, style="Card.TFrame")
        user_table.grid(row=3, column=0, columnspan=5, sticky="nsew", padx=8, pady=(6, 0))
        self.user_tree = self._make_tree(
            user_table, user_columns,
            {"账号": 120, "姓名": 110, "角色": 90, "班级": 220, "状态": 80, "初始密码": 90},
            height=7,
        )
        self.user_tree.bind("<<TreeviewSelect>>", self._load_selected_user)
        users.rowconfigure(3, weight=1)

    # ------------------------------------------------------------------
    # 社交激励和体测
    # ------------------------------------------------------------------
    def _build_social_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="both", expand=True)
        rank_box = ttk.LabelFrame(top, text="  运动排行榜 / 积分商城  ", padding=12)
        rank_box.pack(fill="both", expand=True, pady=(0, 12))
        columns = ("排名", "姓名", "班级", "总时长", "总热量", "积分")
        widths = {"排名": 70, "姓名": 110, "班级": 230, "总时长": 110, "总热量": 110, "积分": 90}
        self.rank_tree = self._make_tree(rank_box, columns, widths, height=12)
        self.shop_hint = tk.StringVar(value="积分商城示例：50积分=饮用水；100积分=运动小礼品；200积分=体育课平时分加分申请。")
        ttk.Label(rank_box, textvariable=self.shop_hint, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(12, 0))

        test_box = ttk.LabelFrame(top, text="  国家学生体质健康标准：体测录入与自动评级  ", padding=12)
        test_box.pack(fill="both", expand=True)
        self.test_vars = {
            "学号": tk.StringVar(value=self.profile.student_id),
            "姓名": tk.StringVar(value=self.profile.name),
            "性别": tk.StringVar(value=self.profile.gender),
            "年份": tk.StringVar(value=str(date.today().year)),
            "跑步单项分": tk.StringVar(value="75"),
            "立定跳远(cm)": tk.StringVar(value="220"),
            "肺活量": tk.StringVar(value=str(self.profile.lung_capacity)),
            "坐位体前屈(cm)": tk.StringVar(value="12"),
            "总分": tk.StringVar(value="78"),
        }
        test_fields = [
            ("学号", None), ("姓名", None), ("性别", ["男", "女"]),
            ("年份", None), ("跑步单项分", None), ("立定跳远(cm)", None),
            ("肺活量", None), ("坐位体前屈(cm)", None), ("总分", None),
        ]
        for idx, (label, values) in enumerate(test_fields):
            widget = self._form_field(test_box, label, self.test_vars[label], (idx // 3) * 2, idx % 3, values, width=15)
            if label in {"学号", "姓名", "总分"}:
                widget.configure(state="readonly")
        for key in ("性别", "跑步单项分", "立定跳远(cm)", "肺活量", "坐位体前屈(cm)"):
            self.test_vars[key].trace_add("write", lambda *_args: self.update_test_score())
        self.update_test_score()
        ttk.Label(test_box, text="总分由已采集四项按 40/20/20/20 自动估算，并非完整国标成绩单。",
                  style="Muted.TLabel").grid(row=6, column=1, columnspan=2, sticky="w", padx=8)
        ttk.Button(test_box, text="保存体测成绩", style="Primary.TButton", command=self.add_test_record).grid(row=6, column=0, padx=8, pady=10, sticky="w")
        self.test_table_box = ttk.LabelFrame(test_box, text="  体测记录  ", padding=8)
        self.test_table_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        columns = ("序号", "姓名", "年份", "跑步", "跳远", "肺活量", "总分", "评级", "建议")
        widths = {"序号": 60, "姓名": 90, "年份": 80, "跑步": 80, "跳远": 80, "肺活量": 90, "总分": 80, "评级": 90, "建议": 240}
        self.test_tree = self._make_tree(self.test_table_box, columns, widths, height=7)
        test_box.rowconfigure(7, weight=1)

    # ------------------------------------------------------------------
    # 业务逻辑：加载刷新
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        if not self._validate_filter_dates():
            return
        self.profile = self.profile_store.load()
        self.all_records = self.sport_store.load_records()
        self.health_logs = self.health_store.load()
        self.tests = self.test_store.load()
        self.refresh_sport_page()
        self._refresh_dashboard()
        self._refresh_health_table()
        self._refresh_analysis()
        self._refresh_teacher_tables()
        self._refresh_admin_lists()
        self.refresh_admin_overview()
        self._refresh_social_tables()
        self._refresh_profile_preview()

    def refresh_sport_page(self) -> None:
        filters = dict(
            keyword=self.filter_keyword.get() if hasattr(self, "filter_keyword") else "",
            sport_type=self.filter_sport.get() if hasattr(self, "filter_sport") else "全部",
            category=self.filter_category.get() if hasattr(self, "filter_category") else "全部",
            status=self.filter_status.get() if hasattr(self, "filter_status") else "全部",
            start_day=self.filter_start.get() if hasattr(self, "filter_start") else "",
            end_day=self.filter_end.get() if hasattr(self, "filter_end") else "",
        )
        self.visible_records, self.sport_total = self.sport_store.get_page(
            self.sport_page, self.sport_page_size, **filters
        )
        page_count = max(1, (self.sport_total + self.sport_page_size - 1) // self.sport_page_size)
        if self.sport_page > page_count:
            self.sport_page = page_count
            self.visible_records, self.sport_total = self.sport_store.get_page(
                self.sport_page, self.sport_page_size, **filters
            )
        if hasattr(self, "page_text"):
            self.page_text.set(f"第 {self.sport_page} / {page_count} 页 · 共 {self.sport_total} 条")
        self._refresh_sport_table()

    def apply_filters(self) -> None:
        if not self._validate_filter_dates():
            return
        self.sport_page = 1
        self.refresh_sport_page()

    def previous_page(self) -> None:
        if self.sport_page > 1:
            self.sport_page -= 1
            self.refresh_sport_page()

    def next_page(self) -> None:
        page_count = max(1, (self.sport_total + self.sport_page_size - 1) // self.sport_page_size)
        if self.sport_page < page_count:
            self.sport_page += 1
            self.refresh_sport_page()

    def refresh_after_sport_change(self) -> None:
        self.all_records = self.sport_store.load_records()
        self.refresh_sport_page()
        self._refresh_dashboard()
        self._refresh_analysis()
        self._refresh_teacher_tables()
        self.refresh_admin_overview()
        self._refresh_social_tables()

    def refresh_after_health_change(self) -> None:
        self.health_logs = self.health_store.load()
        self._refresh_health_table()
        self._refresh_analysis()

    def refresh_after_test_change(self) -> None:
        self.tests = self.test_store.load()
        self._refresh_social_tables()
        self.refresh_admin_overview()

    def _validate_filter_dates(self) -> bool:
        for label in ["filter_start", "filter_end"]:
            if hasattr(self, label):
                value = getattr(self, label).get().strip()
                if value:
                    try:
                        normalize_date(value)
                    except ValueError:
                        messagebox.showerror("日期错误", "筛选日期格式应为 YYYY-MM-DD")
                        return False
        return True

    # ------------------------------------------------------------------
    # 刷新各区 UI
    # ------------------------------------------------------------------
    def _refresh_dashboard(self) -> None:
        s = summarize(self.all_records, self.profile.weekly_target)
        bmi = calc_bmi(self.profile.height, self.profile.weight)
        self.card_vars["count"].set(f"{s['valid_count']} 次")
        self.card_vars["duration"].set(f"{s['duration']} 分钟")
        self.card_vars["calories"].set(f"{s['calories']} kcal")
        self.card_vars["steps"].set(f"{s['steps']} 步")
        self.card_vars["bmi"].set(f"{bmi}｜{bmi_level(bmi)}")
        self.card_vars["pending"].set(f"{s['pending_count']} 条")
        sport_text = "；".join(f"{sport}{duration}分钟" for sport, _, duration, _ in summarize_by_sport(self.all_records)[:3]) or "暂无"
        self.dashboard_summary.set(
            f"学生：{self.profile.name}｜角色：{self.role_var.get()}｜班级：{self.profile.class_name}\n"
            f"当前目标：{self.profile.fitness_goal}｜周运动目标：{self.profile.weekly_target} 分钟｜每日步数目标：{self.profile.step_goal} 步\n"
            f"有效记录：{s['valid_count']} 条｜活跃 {s['active_days']} 天｜平均每次 {s['average_duration']} 分钟｜偏好运动：{s['favorite']}\n"
            f"运动分布：{sport_text}\n"
            f"目标完成情况：{s['target_status']}"
        )
        self.progress_var.set(int(s["target_percent"]))
        self.progress_text.set(f"每周目标进度：{s['target_percent']}%")
        signature = tuple((r.record_id, r.day, r.duration, r.status) for r in self.all_records)
        if signature != self._chart_signature:
            render_duration_bar(self.sport_chart, self.all_records, 7)
            self._chart_signature = signature
        self._fill_latest_tree()

    def _fill_latest_tree(self) -> None:
        self.latest_tree.delete(*self.latest_tree.get_children())
        for index, record in enumerate(sorted(self.all_records, key=lambda r: r.day, reverse=True)[:20], start=1):
            tag = "odd" if index % 2 else "even"
            status_tag = {"已通过": "approved", "待审批": "pending", "已驳回": "rejected"}.get(record.status, "")
            status_text = {"已通过": "● 已通过", "待审批": "● 待审批", "已驳回": "● 已驳回"}.get(record.status, record.status)
            self.latest_tree.insert("", "end", values=(index, record.name, record.class_name, record.day, record.sport_type, record.category, record.checkin_method, record.location, f"{record.duration}分", status_text), tags=(tag, status_tag))

    def _refresh_sport_table(self) -> None:
        self.sport_tree.delete(*self.sport_tree.get_children())
        for index, r in enumerate(self.visible_records, start=1):
            tag = "odd" if index % 2 else "even"
            status_tag = {"已通过": "approved", "待审批": "pending", "已驳回": "rejected"}.get(r.status, "")
            status_text = {"已通过": "● 已通过", "待审批": "● 待审批", "已驳回": "● 已驳回"}.get(r.status, r.status)
            row_number = (self.sport_page - 1) * self.sport_page_size + index
            self.sport_tree.insert("", "end", iid=str(r.record_id), values=(
                row_number, r.student_id, r.name, r.class_name, r.day, r.sport_type, r.category, r.checkin_method, r.location,
                f"{r.duration}分", f"{r.distance:.2f}", r.steps, r.heart_rate, f"{r.calories:.1f}", status_text,
            ), tags=(tag, status_tag))

    def _refresh_health_table(self) -> None:
        self.health_tree.delete(*self.health_tree.get_children())
        for index, h in enumerate(sorted(self.health_logs, key=lambda x: x.day, reverse=True), start=1):
            tag = "odd" if index % 2 else "even"
            self.health_tree.insert("", "end", iid=str(h.record_id), values=(index, h.student_id, h.name, h.day, f"{h.weight:.1f}", f"{h.sleep_hours:.1f}h", h.meals, h.heart_rate, h.fatigue_level, h.injury_note, h.menstrual_note), tags=(tag,))

    def _refresh_analysis(self) -> None:
        warnings = risk_warnings(self.profile, self.all_records, self.health_logs)
        s = summarize(self.all_records, self.profile.weekly_target)
        bmi = calc_bmi(self.profile.height, self.profile.weight)
        text = [
            "【一、健康状态】",
            f"BMI：{bmi}（{bmi_level(bmi)}）｜体脂率：{self.profile.body_fat}%｜肺活量：{self.profile.lung_capacity}",
            f"本阶段有效运动：{s['valid_count']} 次｜累计 {s['duration']} 分钟｜消耗 {s['calories']} kcal｜步数 {s['steps']} 步",
            "",
            "【二、风险预警】",
            *[f"{i + 1}. {item}" for i, item in enumerate(warnings)],
            "",
            "【三、个性化运动方案】",
            personal_plan(self.profile, self.all_records),
            "",
            "【四、饮食建议】",
            diet_advice(self.profile, float(s["calories"])),
            "",
            "【五、体测预判】",
            predict_test_score(self.all_records, self.tests),
        ]
        self.analysis_text.delete("1.0", "end")
        self.analysis_text.insert("1.0", "\n".join(text))
        render_weight_line(self.weight_chart, self.health_logs, 10)
        self.analysis_hint.set("说明：当前为本地健康规则引擎，数据保存在 SQLite；GPS 与手环入口是演示模拟，未连接第三方平台。")

    def _refresh_teacher_tables(self) -> None:
        self.class_tree.delete(*self.class_tree.get_children())
        for index, row in enumerate(class_statistics(self.all_records), start=1):
            tag = "odd" if index % 2 else "even"
            name, class_name, count, duration, calories, pending = row
            self.class_tree.insert("", "end", values=(index, name, class_name, count, f"{duration}分", f"{calories:.1f}", pending), tags=(tag,))

        self.pending_tree.delete(*self.pending_tree.get_children())
        pending_records = [r for r in self.all_records if r.status == "待审批"]
        for index, r in enumerate(pending_records, start=1):
            tag = "odd" if index % 2 else "even"
            self.pending_tree.insert("", "end", iid=str(r.record_id), values=(index, r.student_id, r.name, r.day, r.sport_type, r.checkin_method, r.location, f"{r.duration}分", r.remark, "● 待审批"), tags=(tag, "pending"))

    def _refresh_admin_lists(self) -> None:
        self.point_list.delete(0, tk.END)
        for point in self.config_points:
            self.point_list.insert(tk.END, point)

    def _refresh_user_table(self) -> None:
        if self.current_role != "admin" or not hasattr(self, "user_tree"):
            return
        self.user_tree.delete(*self.user_tree.get_children())
        for index, user in enumerate(self.auth_service.list_users(), start=1):
            status = "● 已启用" if user["is_active"] else "● 已禁用"
            initial = "是" if user["is_initial_password"] else "否"
            tag = "approved" if user["is_active"] else "rejected"
            self.user_tree.insert(
                "", "end", iid=str(user["student_id"]),
                values=(user["student_id"], user["username"], user["role"],
                        user["class_name"] or "", status, initial),
                tags=(("odd" if index % 2 else "even"), tag),
            )

    def _load_selected_user(self, _event=None) -> None:
        selected = self.user_tree.selection()
        if not selected:
            return
        values = self.user_tree.item(selected[0], "values")
        for key, value in zip(("账号", "姓名", "角色", "班级"), values[:4]):
            self.user_vars[key].set(value)

    def add_user(self) -> None:
        try:
            self.auth_service.add_user(
                self.user_vars["账号"].get(), self.user_vars["姓名"].get(),
                self.user_vars["临时密码"].get(), self.user_vars["角色"].get(),
                self.user_vars["班级"].get(),
            )
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("新增失败", str(exc))
            return
        self._refresh_user_table()
        messagebox.showinfo("新增成功", "用户已创建，首次登录必须修改临时密码。")

    def update_user(self) -> None:
        try:
            self.auth_service.update_user(
                self.user_vars["账号"].get(), self.user_vars["姓名"].get(),
                self.user_vars["角色"].get(), self.user_vars["班级"].get(),
            )
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("修改失败", str(exc))
            return
        self._refresh_user_table()
        messagebox.showinfo("保存成功", "用户角色和班级已更新。")

    def reset_user_password(self) -> None:
        account = self.user_vars["账号"].get().strip()
        password = self.user_vars["临时密码"].get()
        if not account:
            messagebox.showwarning("提示", "请先选择或填写账号。")
            return
        if not messagebox.askyesno("确认重置", f"确定重置账号 {account} 的密码吗？"):
            return
        try:
            self.auth_service.reset_password(account, password)
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("重置失败", str(exc))
            return
        self._refresh_user_table()
        messagebox.showinfo("重置成功", "用户下次登录必须修改临时密码。")

    def toggle_user_active(self) -> None:
        selected = self.user_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在用户表中选择账号。")
            return
        account = str(selected[0])
        values = self.user_tree.item(account, "values")
        active = "已启用" in str(values[4])
        try:
            self.auth_service.set_active(account, not active)
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("操作失败", str(exc))
            return
        self._refresh_user_table()

    def import_batch_data(self) -> None:
        path = filedialog.askopenfilename(
            title=f"导入{self.import_type.get()}",
            filetypes=[("Excel / CSV", "*.xlsx *.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not path:
            return

        def done(result) -> str:
            success, errors = result
            self.refresh_all()
            detail = "\n".join(errors[:12])
            if len(errors) > 12:
                detail += f"\n……另有 {len(errors) - 12} 条错误"
            return f"成功导入 {success} 条，失败 {len(errors)} 条。" + (f"\n\n{detail}" if detail else "")

        self._run_async_io(
            lambda: import_file(path, self.import_type.get()), "批量导入完成", done
        )

    def refresh_admin_overview(self) -> None:
        if not hasattr(self, "admin_text"):
            return
        s = summarize(self.all_records, self.profile.weekly_target)
        class_rows = class_statistics(self.all_records)
        rank_rows = leaderboard(self.all_records)
        pass_tests = len([t for t in self.tests if (t.rating or evaluate_physical_test(t.total_score)) != "不及格"])
        total_tests = len(self.tests)
        overview = [
            "【全校大数据总览】",
            f"总打卡记录：{len(self.all_records)} 条｜有效记录：{s['valid_count']} 条｜待审批：{s['pending_count']} 条｜驳回：{s['rejected_count']} 条",
            f"累计运动时长：{s['duration']} 分钟｜累计热量：{s['calories']} kcal｜累计步数：{s['steps']} 步",
            f"参与学生数：{len(rank_rows)} 人｜班级统计条目：{len(class_rows)} 条｜体测达标率：{(pass_tests / total_tests * 100 if total_tests else 0):.1f}%",
            "",
            "【管理员配置】",
            f"打卡点位：{'、'.join(self.config_points)}",
            f"最短有效时长：{self.min_duration_rule.get() if hasattr(self, 'min_duration_rule') else '20'} 分钟",
            f"计分规则：每 {self.score_rule_vars['minutes_per_point'].get() if hasattr(self, 'score_rule_vars') else 10} 分钟计分，单次/满额奖励结构化生效",
            f"黑名单：{', '.join(sorted(self.blacklist)) or '暂无'}",
            "",
            "【可扩展接口】",
            "1. 教务系统：统一学号登录、角色权限、体育成绩折算。",
            "2. GPS/校园围栏：操场、篮球场、田径场等地标防代刷。",
            "3. 手环/运动 APP：Keep、小米运动步数、心率同步。",
            "4. 医务室联动：频繁伤病学生推送健康回访提醒。",
        ]
        self.admin_text.delete("1.0", "end")
        self.admin_text.insert("1.0", "\n".join(overview))
        self._refresh_user_table()

    def _refresh_social_tables(self) -> None:
        self.rank_tree.delete(*self.rank_tree.get_children())
        for row in leaderboard(self.all_records):
            rank, name, class_name, duration, calories, points = row
            tag = "odd" if rank % 2 else "even"
            self.rank_tree.insert("", "end", values=(rank, name, class_name, f"{duration}分", f"{calories:.1f}", points), tags=(tag,))

        self.test_tree.delete(*self.test_tree.get_children())
        for index, t in enumerate(sorted(self.tests, key=lambda x: x.year, reverse=True), start=1):
            rating = t.rating or evaluate_physical_test(t.total_score)
            tag = "odd" if index % 2 else "even"
            self.test_tree.insert("", "end", values=(index, t.name, t.year, t.run_score, t.long_jump, t.lung_capacity, t.total_score, rating, test_suggestion(t)), tags=(tag,))

    def _refresh_profile_preview(self) -> None:
        if not hasattr(self, "profile_preview"):
            return
        bmi = calc_bmi(self.profile.height, self.profile.weight)
        self.profile_preview.set(
            f"学号：{self.profile.student_id}\n"
            f"姓名：{self.profile.name}\n"
            f"角色：{self.profile.role}\n"
            f"班级：{self.profile.class_name}\n"
            f"性别：{self.profile.gender}\n"
            f"身高/体重：{self.profile.height} cm / {self.profile.weight} kg\n"
            f"BMI：{bmi}（{bmi_level(bmi)}）｜体脂率：{self.profile.body_fat}%\n"
            f"血压：{self.profile.blood_pressure}｜肺活量：{self.profile.lung_capacity}\n"
            f"既往伤病：{self.profile.injuries}\n"
            f"过敏史：{self.profile.allergies}\n"
            f"体检备注：{self.profile.medical_note}\n"
            f"周运动目标：{self.profile.weekly_target} 分钟｜每日步数目标：{self.profile.step_goal} 步｜健身目标：{self.profile.fitness_goal}"
        )

    # ------------------------------------------------------------------
    # 操作方法：打卡、档案、自测、体测
    # ------------------------------------------------------------------
    def _make_sport_record(self, status: str) -> SportRecord:
        sport_type = self.sport_vars["运动类型"].get()
        duration = to_int(self.sport_vars["时长(分钟)"].get())
        weight = to_float(self.sport_vars["体重(kg)"].get(), self.profile.weight)
        calories = estimate_calories(sport_type, duration, weight)
        if self.current_role == "student":
            self.sport_vars["学号"].set(self.profile.student_id)
            self.sport_vars["姓名"].set(self.profile.name)
            self.sport_vars["班级"].set(self.profile.class_name)
        return SportRecord(
            student_id=self.sport_vars["学号"].get(),
            name=self.sport_vars["姓名"].get(),
            class_name=self.sport_vars["班级"].get(),
            day=self.sport_vars["日期"].get(),
            sport_type=sport_type,
            category=self.sport_vars["打卡分类"].get(),
            checkin_method=self.sport_vars["打卡方式"].get(),
            location=self.sport_vars["地点"].get(),
            duration=duration,
            distance=to_float(self.sport_vars["距离(km)"].get()),
            steps=to_int(self.sport_vars["步数"].get()),
            heart_rate=to_int(self.sport_vars["心率"].get()),
            calories=calories,
            status=status,
            remark=self.sport_vars["备注/凭证"].get(),
        )

    def add_sport_record(self) -> None:
        if not self._require_role("student"):
            return
        try:
            student_id = self.sport_vars["学号"].get().strip()
            if student_id in self.blacklist:
                messagebox.showwarning("权限限制", "该学号在黑名单中，暂时限制打卡。")
                return
            record = self._make_sport_record("已通过")
            self.sport_service.submit(record)
            self.clear_sport_form(keep_basic=True)
            self.refresh_after_sport_change()
            messagebox.showinfo("保存成功", f"已保存 {record.name} 的 {record.sport_type} 打卡，估算消耗 {record.calories} kcal。")
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("输入错误", f"请检查输入内容：{exc}")

    def add_makeup_record(self) -> None:
        if not self._require_role("student"):
            return
        try:
            self.sport_vars["打卡方式"].set("补卡申请")
            record = self._make_sport_record("待审批")
            if not record.remark:
                record.remark = "补卡申请：已上传/补充凭证说明"
            self.sport_service.submit(record, makeup=True)
            self.clear_sport_form(keep_basic=True)
            self.refresh_after_sport_change()
            messagebox.showinfo("提交成功", "补卡申请已提交，等待体育老师在线审批。")
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("输入错误", f"请检查输入内容：{exc}")

    def sync_device_demo(self) -> None:
        self.sport_vars["打卡方式"].set("设备同步")
        self.sport_vars["运动类型"].set(random.choice(["跑步", "骑行", "早操"]))
        duration = random.randint(25, 60)
        steps = random.randint(3500, 9500)
        distance = round(steps * 0.0007, 2)
        heart_rate = random.randint(105, 155)
        self.sport_vars["时长(分钟)"].set(str(duration))
        self.sport_vars["步数"].set(str(steps))
        self.sport_vars["距离(km)"].set(str(distance))
        self.sport_vars["心率"].set(str(heart_rate))
        self.sport_vars["备注/凭证"].set("模拟 Keep/小米运动同步数据")
        messagebox.showinfo("设备同步模拟", "已自动填入步数、距离、心率和运动时长，可点击保存正式打卡。")

    def clear_sport_form(self, keep_basic: bool = False) -> None:
        for key in ["时长(分钟)", "距离(km)", "步数", "心率", "备注/凭证"]:
            self.sport_vars[key].set("0" if key in {"距离(km)", "步数", "心率"} else "")
        if not keep_basic:
            self.sport_vars["日期"].set(str(date.today()))
            self.sport_vars["运动类型"].set("足球")
            self.sport_vars["打卡分类"].set("球类")
            self.sport_vars["打卡方式"].set("手动录入")
            self.sport_vars["地点"].set("校园操场")

    def save_profile(self) -> None:
        if not self._require_role("student"):
            return
        try:
            profile = HealthProfile(
                student_id=self.profile_vars["学号"].get(),
                name=self.profile_vars["姓名"].get(),
                role=self.profile_vars["角色"].get(),
                class_name=self.profile_vars["班级"].get(),
                gender=self.profile_vars["性别"].get(),
                height=to_float(self.profile_vars["身高(cm)"].get()),
                weight=to_float(self.profile_vars["体重(kg)"].get()),
                body_fat=to_float(self.profile_vars["体脂率(%)"].get()),
                blood_pressure=self.profile_vars["血压"].get(),
                lung_capacity=to_int(self.profile_vars["肺活量"].get()),
                injuries=self.profile_vars["既往伤病"].get(),
                allergies=self.profile_vars["过敏史"].get(),
                medical_note=self.profile_vars["体检备注"].get(),
                weekly_target=to_int(self.profile_vars["周运动目标"].get()),
                step_goal=to_int(self.profile_vars["每日步数目标"].get()),
                fitness_goal=self.profile_vars["健身目标"].get(),
            ).normalize()
            self.profile_store.save(profile)
            self.profile = profile
            self.role_var.set(profile.role)
            self.sync_profile_to_forms()
            self._refresh_profile_preview()
            self._refresh_dashboard()
            self._refresh_analysis()
            messagebox.showinfo("保存成功", "个人健康档案与目标已保存。")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查档案内容：{exc}")

    def sync_profile_to_forms(self) -> None:
        for var_dict in [self.sport_vars, self.health_vars, self.test_vars]:
            if "学号" in var_dict:
                var_dict["学号"].set(self.profile.student_id)
            if "姓名" in var_dict:
                var_dict["姓名"].set(self.profile.name)
            if "班级" in var_dict:
                var_dict["班级"].set(self.profile.class_name)
            if "性别" in var_dict:
                var_dict["性别"].set(self.profile.gender)
        self.sport_vars["体重(kg)"].set(str(self.profile.weight))
        self.health_vars["晨起体重"].set(str(self.profile.weight))
        self.test_vars["肺活量"].set(str(self.profile.lung_capacity))

    def add_health_log(self) -> None:
        if not self._require_role("student"):
            return
        try:
            log = HealthLog(
                student_id=self.health_vars["学号"].get(),
                name=self.health_vars["姓名"].get(),
                day=self.health_vars["日期"].get(),
                weight=to_float(self.health_vars["晨起体重"].get()),
                sleep_hours=to_float(self.health_vars["睡眠时长"].get()),
                meals=self.health_vars["三餐饮食"].get(),
                heart_rate=to_int(self.health_vars["当日心率"].get()),
                fatigue_level=self.health_vars["疲劳程度"].get(),
                injury_note=self.health_vars["伤病记录"].get(),
                menstrual_note=self.health_vars["生理期备注"].get(),
            )
            self.health_store.append(log)
            self.refresh_after_health_change()
            messagebox.showinfo("保存成功", "健康自测记录已保存。")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查自测内容：{exc}")

    def add_test_record(self) -> None:
        if not self._require_role("student"):
            return
        try:
            total_score = to_float(self.test_vars["总分"].get())
            rating = evaluate_physical_test(total_score)
            record = PhysicalTestRecord(
                student_id=self.test_vars["学号"].get(),
                name=self.test_vars["姓名"].get(),
                gender=self.test_vars["性别"].get(),
                year=to_int(self.test_vars["年份"].get()),
                run_score=to_float(self.test_vars["跑步单项分"].get()),
                long_jump=to_float(self.test_vars["立定跳远(cm)"].get()),
                lung_capacity=to_int(self.test_vars["肺活量"].get()),
                sit_reach=to_float(self.test_vars["坐位体前屈(cm)"].get()),
                total_score=total_score,
                rating=rating,
            )
            self.test_store.append(record)
            self.refresh_after_test_change()
            extra = "\n系统已生成补强任务建议。" if rating == "不及格" else ""
            messagebox.showinfo("体测保存成功", f"评级：{rating}{extra}")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查体测内容：{exc}")

    def update_test_score(self) -> None:
        try:
            total, _rating = calculate_physical_test_score(
                self.test_vars["性别"].get(),
                to_float(self.test_vars["跑步单项分"].get()),
                to_float(self.test_vars["立定跳远(cm)"].get()),
                to_int(self.test_vars["肺活量"].get()),
                to_float(self.test_vars["坐位体前屈(cm)"].get()),
            )
        except (ValueError, tk.TclError):
            return
        self.test_vars["总分"].set(str(total))

    # ------------------------------------------------------------------
    # 删除、审核、导出、配置
    # ------------------------------------------------------------------
    def reset_filters(self) -> None:
        self.filter_keyword.set("")
        self.filter_sport.set("全部")
        self.filter_category.set("全部")
        self.filter_status.set("全部")
        self.filter_start.set("")
        self.filter_end.set("")
        self.sport_page = 1
        self.refresh_sport_page()

    def delete_selected(self) -> None:
        if not self._require_role("student"):
            return
        selected = self.sport_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在打卡明细表中选择记录。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(selected)} 条打卡记录吗？"):
            return
        try:
            for item in selected:
                self.sport_service.delete(int(item))
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.refresh_after_sport_change()
        messagebox.showinfo("删除成功", "选中打卡记录已删除。")

    def delete_health_log(self) -> None:
        if not self._require_role("student"):
            return
        selected = self.health_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择健康自测记录。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(selected)} 条健康记录吗？"):
            return
        try:
            for item in selected:
                self.health_store.delete(int(item))
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("删除失败", str(exc))
            return
        self.refresh_after_health_change()
        messagebox.showinfo("删除成功", "选中健康自测记录已删除。")

    def review_selected(self, status: str) -> None:
        if not self._require_role("teacher", "admin"):
            return
        selected = self.pending_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择待审核补卡/异常记录。")
            return
        for item in selected:
            self.sport_service.review(int(item), status)
        self.refresh_after_sport_change()
        messagebox.showinfo("审核完成", f"已将选中记录标记为：{status}")

    def publish_task(self) -> None:
        if not self._require_role("teacher", "admin"):
            return
        self.admin_settings_service.save_teacher_task(
            self.teacher_task.get().strip(), self.teacher_deadline.get().strip(),
            self.teacher_location.get().strip(),
        )
        messagebox.showinfo("任务发布成功", f"已发布运动作业：{self.teacher_task.get()}\n地点：{self.teacher_location.get()}\n有效期：{self.teacher_deadline.get()}")

    def add_location_point(self) -> None:
        if not self._require_role("admin"):
            return
        point = self.new_point.get().strip()
        if not point:
            messagebox.showwarning("提示", "请输入点位名称。")
            return
        if point not in self.config_points:
            self.config_points.append(point)
            self.admin_settings_service.save_locations(self.config_points)
            self.new_point.set("")
            self._refresh_admin_lists()
            self.refresh_admin_overview()
            # 更新相关下拉框的值
            self.sport_vars["地点"].set(point)
            messagebox.showinfo("添加成功", f"已添加校园打卡点位：{point}")

    def delete_location_point(self) -> None:
        if not self._require_role("admin"):
            return
        selection = self.point_list.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的点位。")
            return
        point = self.point_list.get(selection[0])
        if point in self.config_points:
            self.config_points.remove(point)
            self.admin_settings_service.save_locations(self.config_points)
            self._refresh_admin_lists()
            self.refresh_admin_overview()

    def add_blacklist(self) -> None:
        if not self._require_role("admin"):
            return
        student_id = self.black_id.get().strip()
        if not student_id:
            messagebox.showwarning("提示", "请输入学号。")
            return
        self.blacklist.add(student_id)
        self.admin_settings_service.save_blacklist(sorted(self.blacklist))
        self.black_id.set("")
        self.refresh_admin_overview()
        messagebox.showinfo("已加入黑名单", f"学号 {student_id} 已限制打卡权限。")

    def save_admin_rules(self) -> None:
        if not self._require_role("admin"):
            return
        min_duration = to_int(self.min_duration_rule.get(), 20)
        if not 1 <= min_duration <= 600:
            messagebox.showerror("输入错误", "最短有效时长应在 1-600 分钟之间。")
            return
        self.settings_store.set("min_duration", min_duration)
        try:
            rule = {key: to_int(var.get()) for key, var in self.score_rule_vars.items()}
            self.admin_settings_service.save_score_rule(rule)
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("输入错误", str(exc))
            return
        self.refresh_admin_overview()
        self._refresh_social_tables()
        messagebox.showinfo("保存成功", "结构化计分规则已生效并重新计算排行榜。")

    def change_password(self) -> None:
        if PasswordChangeDialog(self.root, self.current_user).show():
            self.current_user["is_initial_password"] = 0
            messagebox.showinfo("修改成功", "密码已更新，请妥善保管。")

    def switch_account(self) -> None:
        if not VerificationDialog(self.root).show():
            return
        self.switch_requested = True
        close_conn()
        self.root.destroy()

    def _run_async_io(self, action, success_title: str, success_text) -> None:
        self.root.configure(cursor="wait")

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                self.root.after(0, lambda: finish_error(str(exc)))
            else:
                self.root.after(0, lambda: finish_success(result))

        def finish_error(error: str) -> None:
            self.root.configure(cursor="")
            messagebox.showerror("操作失败", error)

        def finish_success(result) -> None:
            self.root.configure(cursor="")
            messagebox.showinfo(success_title, success_text(result))

        threading.Thread(target=worker, daemon=True).start()

    def export_report(self) -> None:
        if not self.all_records and not self.health_logs:
            messagebox.showwarning("提示", "暂无数据，无法生成报告。")
            return
        snapshot = (self.profile, list(self.all_records), list(self.health_logs), list(self.tests))
        self._run_async_io(
            lambda: export_health_report_txt(*snapshot), "导出成功",
            lambda path: f"健康周报已导出：\n{path}",
        )

    def export_current_csv(self) -> None:
        if not self.visible_records:
            messagebox.showwarning("提示", "当前没有可导出的打卡数据。")
            return
        records = list(self.visible_records)
        self._run_async_io(
            lambda: export_sport_excel(records), "导出成功",
            lambda path: f"当前页数据已导出：\n{path}",
        )

    def export_class_report(self) -> None:
        if not self._require_role("teacher", "admin"):
            return
        REPORT_DIR.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="导出班级运动数据报表",
            initialdir=REPORT_DIR,
            initialfile=f"class_report_{date.today()}.txt",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not path:
            return
        lines = ["班级运动数据报表", "=" * 30]
        for name, class_name, count, duration, calories, pending in class_statistics(self.all_records):
            lines.append(f"{class_name}｜{name}：有效{count}次，{duration}分钟，{calories:.1f}kcal，待审批{pending}条")
        if not class_statistics(self.all_records):
            lines.append("暂无数据")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        messagebox.showinfo("导出成功", f"班级报表已导出：\n{path}")

    def backup_data(self) -> None:
        if not self._require_role("admin"):
            return
        self._run_async_io(
            backup_database, "备份成功", lambda path: f"SQLite 数据库已备份：\n{path}"
        )


def main() -> None:
    if sys.platform.startswith("win"):
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    init_db()
    if sum(table_count(name) for name in ("sport_records", "health_logs", "physical_tests")) == 0:
        migrate_from_csv()

    while True:
        root = ttk.Window(themename="flatly")
        root.withdraw()
        user = LoginDialog(root).show()
        if not user:
            close_conn()
            root.destroy()
            return
        if bool(user.get("is_initial_password", 0)):
            if not PasswordChangeDialog(root, user, force=True).show():
                close_conn()
                root.destroy()
                return
            user["is_initial_password"] = 0
        root.deiconify()
        app = SportApp(root, user)
        root.mainloop()
        should_switch = app.switch_requested
        close_conn()
        if not should_switch:
            break
        init_db()


if __name__ == "__main__":
    main()
