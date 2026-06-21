"""校园运动打卡与健康数据分析系统 - 豪华完善版
运行方式：在 PyCharm 中打开项目，直接运行 main.py。

说明：本项目使用 Python 标准库 tkinter + csv/json 完成，适合作为课程实训/答辩项目。
真实的教务系统、GPS、手环同步在桌面版中使用“模拟入口/预留字段”表达，便于演示系统设计完整性。
"""
from __future__ import annotations

import random
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
    class_statistics,
    daily_trend,
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
    weekly_report,
    weight_trend,
)
from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord, normalize_date, to_float, to_int
from storage import HealthLogStorage, PhysicalTestStorage, ProfileStorage, SportStorage

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
BACKUP_DIR = BASE_DIR / "backups"
PROFILE_PATH = DATA_DIR / "profile.json"
SPORT_PATH = DATA_DIR / "sport_records.csv"
HEALTH_PATH = DATA_DIR / "health_logs.csv"
TEST_PATH = DATA_DIR / "physical_tests.csv"

COLORS = {
    "bg": "#EEF3FA",
    "panel": "#F8FAFC",
    "card": "#FFFFFF",
    "primary": "#2563EB",
    "primary_dark": "#1D4ED8",
    "accent": "#16A34A",
    "accent_soft": "#DCFCE7",
    "warning": "#F59E0B",
    "warning_soft": "#FEF3C7",
    "danger": "#DC2626",
    "danger_soft": "#FEE2E2",
    "text": "#0F172A",
    "muted": "#64748B",
    "border": "#CBD5E1",
    "table_alt": "#F1F5F9",
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

    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)


class SportApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("校园运动打卡与健康数据分析系统 - 豪华完善版")
        self.root.geometry("1320x860")
        self.root.minsize(1180, 760)
        self.root.configure(bg=COLORS["bg"])

        self.profile_store = ProfileStorage(PROFILE_PATH)
        self.sport_store = SportStorage(SPORT_PATH)
        self.health_store = HealthLogStorage(HEALTH_PATH)
        self.test_store = PhysicalTestStorage(TEST_PATH)

        self.profile = self.profile_store.load()
        self.all_records: list[SportRecord] = []
        self.visible_records: list[SportRecord] = []
        self.health_logs: list[HealthLog] = []
        self.tests: list[PhysicalTestRecord] = []
        self.card_vars: dict[str, tk.StringVar] = {}
        self.config_points = LOCATIONS.copy()
        self.blacklist: set[str] = set()

        self._setup_style()
        self._ensure_demo_data()
        self._build_ui()
        self.refresh_all()

    # ------------------------------------------------------------------
    # 基础样式和布局
    # ------------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = (FONT, 12)
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Card.TFrame", background=COLORS["card"], relief="flat")
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=default_font)
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=default_font)
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT, 11))
        style.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=(FONT, 11, "bold"))
        style.configure("CardValue.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=(FONT, 21, "bold"))
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=(FONT, 26, "bold"))
        style.configure("SubTitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT, 12))
        style.configure("TLabelframe", background=COLORS["bg"], bordercolor=COLORS["border"], relief="solid")
        style.configure("TLabelframe.Label", background=COLORS["bg"], foreground=COLORS["text"], font=(FONT, 14, "bold"))
        style.configure("TEntry", padding=8, fieldbackground="white", font=default_font)
        style.configure("TCombobox", padding=8, fieldbackground="white", font=default_font)
        style.configure("TButton", font=(FONT, 12), padding=(13, 8))
        style.configure("Primary.TButton", font=(FONT, 12, "bold"), padding=(15, 9), foreground="white", background=COLORS["primary"])
        style.map("Primary.TButton", background=[("active", COLORS["primary_dark"]), ("pressed", COLORS["primary_dark"])])
        style.configure("Success.TButton", font=(FONT, 12, "bold"), padding=(15, 9), foreground="white", background=COLORS["accent"])
        style.map("Success.TButton", background=[("active", "#15803D")])
        style.configure("Danger.TButton", font=(FONT, 12, "bold"), padding=(15, 9), foreground="white", background=COLORS["danger"])
        style.map("Danger.TButton", background=[("active", "#B91C1C")])
        style.configure("Treeview", font=(FONT, 12), rowheight=36, background="white", fieldbackground="white", bordercolor=COLORS["border"])
        style.configure("Treeview.Heading", font=(FONT, 12, "bold"), background="#DBEAFE", foreground=COLORS["text"], padding=9)
        style.map("Treeview", background=[("selected", "#BFDBFE")], foreground=[("selected", COLORS["text"])])
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", font=(FONT, 13, "bold"), padding=(18, 10))
        style.configure("Horizontal.TProgressbar", background=COLORS["accent"], troughcolor="#E5E7EB", bordercolor="#E5E7EB")

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)
        self._build_header(container)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        self.tabs: dict[str, ttk.Frame] = {}
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
            tab = ttk.Frame(self.notebook, padding=14)
            self.notebook.add(tab, text=title)
            self.tabs[key] = tab

        self._build_dashboard_tab(self.tabs["dashboard"])
        self._build_student_tab(self.tabs["student"])
        self._build_profile_tab(self.tabs["profile"])
        self._build_health_tab(self.tabs["health"])
        self._build_analysis_tab(self.tabs["analysis"])
        self._build_teacher_tab(self.tabs["teacher"])
        self._build_admin_tab(self.tabs["admin"])
        self._build_social_tab(self.tabs["social"])

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 14))
        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="校园运动打卡与健康数据分析系统", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="学生打卡 · 健康档案 · 智能分析 · 教师审核 · 管理员配置 · 排行激励", style="SubTitle.TLabel").pack(anchor="w", pady=(5, 0))

        right = ttk.Frame(header)
        right.pack(side="right")
        ttk.Label(right, text="当前角色").grid(row=0, column=0, padx=(0, 6))
        self.role_var = tk.StringVar(value=self.profile.role)
        ttk.Combobox(right, textvariable=self.role_var, values=ROLES, width=10, state="readonly").grid(row=0, column=1, padx=(0, 10))
        ttk.Button(right, text="备份数据", command=self.backup_data).grid(row=0, column=2, padx=5)
        ttk.Button(right, text="导出健康周报", style="Primary.TButton", command=self.export_report).grid(row=0, column=3, padx=5)

    def _card(self, parent: ttk.Frame, key: str, title: str, value: str, col: int) -> None:
        frame = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 12, 0), pady=(0, 10))
        parent.columnconfigure(col, weight=1)
        tk.Label(frame, text=title, bg=COLORS["card"], fg=COLORS["muted"], font=(FONT, 11, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
        var = tk.StringVar(value=value)
        self.card_vars[key] = var
        tk.Label(frame, textvariable=var, bg=COLORS["card"], fg=COLORS["text"], font=(FONT, 21, "bold")).pack(anchor="w", padx=16, pady=(4, 14))

    def _make_tree(self, parent: ttk.Frame, columns: tuple[str, ...], widths: dict[str, int], height: int = 8) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 120), anchor="center")
        tree.tag_configure("even", background="white")
        tree.tag_configure("odd", background=COLORS["table_alt"])
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _form_field(self, parent: ttk.Frame, label: str, var: tk.StringVar, row: int, col: int, values: list[str] | None = None, width: int = 16) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=8, pady=(8, 4))
        if values is None:
            ttk.Entry(parent, textvariable=var, width=width).grid(row=row + 1, column=col, sticky="ew", padx=8, pady=(0, 6))
        else:
            ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly").grid(row=row + 1, column=col, sticky="ew", padx=8, pady=(0, 6))
        parent.columnconfigure(col, weight=1)

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
        self.sport_chart = tk.Canvas(chart_box, height=220, bg="white", highlightthickness=1, highlightbackground=COLORS["border"])
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
            self._form_field(form, label, self.sport_vars[label], (idx // 4) * 2, idx % 4, values, width=19)
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
        ttk.Button(filter_box, text="应用筛选", style="Primary.TButton", command=self.refresh_all).grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="重置筛选", command=self.reset_filters).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="删除选中", style="Danger.TButton", command=self.delete_selected).grid(row=2, column=2, padx=8, pady=8, sticky="w")
        ttk.Button(filter_box, text="导出当前 CSV", command=self.export_current_csv).grid(row=2, column=3, padx=8, pady=8, sticky="w")

        table_box = ttk.LabelFrame(parent, text="  打卡记录明细  ", padding=12)
        table_box.pack(fill="both", expand=True)
        columns = ("序号", "学号", "姓名", "班级", "日期", "类型", "分类", "方式", "地点", "时长", "距离", "步数", "心率", "热量", "状态")
        widths = {"序号": 60, "学号": 105, "姓名": 100, "班级": 210, "日期": 120, "类型": 90, "分类": 110, "方式": 120, "地点": 110, "时长": 90, "距离": 90, "步数": 90, "心率": 80, "热量": 100, "状态": 90}
        self.sport_tree = self._make_tree(table_box, columns, widths, height=10)

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
            self._form_field(info, label, self.profile_vars[label], (idx // 4) * 2, idx % 4, values, width=20)
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
            self._form_field(form, label, self.health_vars[label], (idx // 4) * 2, idx % 4, values, width=20)
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
        self.weight_chart = tk.Canvas(right, height=330, bg="white", highlightthickness=1, highlightbackground=COLORS["border"])
        self.weight_chart.pack(fill="both", expand=True)
        self.analysis_hint = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.analysis_hint, justify="left", style="Muted.TLabel").pack(anchor="w", pady=(12, 0))

    # ------------------------------------------------------------------
    # 教师端
    # ------------------------------------------------------------------
    def _build_teacher_tab(self, parent: ttk.Frame) -> None:
        action = ttk.LabelFrame(parent, text="  体育教师端：班级管理、任务发布、异常审核、批量导出  ", padding=14)
        action.pack(fill="x", pady=(0, 12))
        self.teacher_task = tk.StringVar(value="每周 3 次 3km 跑步打卡")
        self.teacher_deadline = tk.StringVar(value=str(date.today()))
        self.teacher_location = tk.StringVar(value="校园操场")
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
        stat_box.pack(side="left", fill="both", expand=True, padx=(0, 8))
        columns = ("序号", "姓名", "班级", "有效次数", "总时长", "总热量", "待审批")
        widths = {"序号": 60, "姓名": 100, "班级": 220, "有效次数": 100, "总时长": 100, "总热量": 100, "待审批": 100}
        self.class_tree = self._make_tree(stat_box, columns, widths, height=13)

        pending_box = ttk.LabelFrame(middle, text="  补卡/异常审核  ", padding=12)
        pending_box.pack(side="right", fill="both", expand=True, padx=(8, 0))
        columns = ("序号", "学号", "姓名", "日期", "类型", "方式", "地点", "时长", "备注", "状态")
        widths = {"序号": 60, "学号": 105, "姓名": 90, "日期": 115, "类型": 85, "方式": 120, "地点": 100, "时长": 80, "备注": 160, "状态": 90}
        self.pending_tree = self._make_tree(pending_box, columns, widths, height=13)

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
        self.min_duration_rule = tk.StringVar(value="20")
        self.score_rule = tk.StringVar(value="每 30 分钟计 5 积分，满勤加 20 积分")
        self.black_id = tk.StringVar()
        self._form_field(rule_box, "最短有效时长", self.min_duration_rule, 0, 0, None, width=16)
        self._form_field(rule_box, "计分规则", self.score_rule, 0, 1, None, width=34)
        self._form_field(rule_box, "黑名单学号", self.black_id, 2, 0, None, width=16)
        ttk.Button(rule_box, text="加入黑名单", style="Danger.TButton", command=self.add_blacklist).grid(row=4, column=0, padx=8, pady=8, sticky="w")
        ttk.Button(rule_box, text="全校数据总览", style="Primary.TButton", command=self.refresh_admin_overview).grid(row=4, column=1, padx=8, pady=8, sticky="w")

        overview = ttk.LabelFrame(parent, text="  全校大数据总览 / 年度报表摘要  ", padding=16)
        overview.pack(fill="both", expand=True)
        self.admin_text = tk.Text(overview, height=18, wrap="word", font=(FONT, 13), bg="white", padx=12, pady=12)
        self.admin_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # 社交激励和体测
    # ------------------------------------------------------------------
    def _build_social_tab(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="both", expand=True)
        rank_box = ttk.LabelFrame(top, text="  运动排行榜 / 积分商城  ", padding=12)
        rank_box.pack(side="left", fill="both", expand=True, padx=(0, 8))
        columns = ("排名", "姓名", "班级", "总时长", "总热量", "积分")
        widths = {"排名": 70, "姓名": 110, "班级": 230, "总时长": 110, "总热量": 110, "积分": 90}
        self.rank_tree = self._make_tree(rank_box, columns, widths, height=12)
        self.shop_hint = tk.StringVar(value="积分商城示例：50积分=饮用水；100积分=运动小礼品；200积分=体育课平时分加分申请。")
        ttk.Label(rank_box, textvariable=self.shop_hint, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(12, 0))

        test_box = ttk.LabelFrame(top, text="  国家学生体质健康标准：体测录入与自动评级  ", padding=12)
        test_box.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.test_vars = {
            "学号": tk.StringVar(value=self.profile.student_id),
            "姓名": tk.StringVar(value=self.profile.name),
            "性别": tk.StringVar(value=self.profile.gender),
            "年份": tk.StringVar(value=str(date.today().year)),
            "800/1000米": tk.StringVar(value="75"),
            "立定跳远(cm)": tk.StringVar(value="220"),
            "肺活量": tk.StringVar(value=str(self.profile.lung_capacity)),
            "坐位体前屈(cm)": tk.StringVar(value="12"),
            "总分": tk.StringVar(value="78"),
        }
        test_fields = [
            ("学号", None), ("姓名", None), ("性别", ["男", "女"]),
            ("年份", None), ("800/1000米", None), ("立定跳远(cm)", None),
            ("肺活量", None), ("坐位体前屈(cm)", None), ("总分", None),
        ]
        for idx, (label, values) in enumerate(test_fields):
            self._form_field(test_box, label, self.test_vars[label], (idx // 3) * 2, idx % 3, values, width=15)
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
    def _ensure_demo_data(self) -> None:
        # 兼容旧版 6 列运动 CSV：启动时自动重写为新版 15 列表头。
        sport_records = self.sport_store.load_records()
        if sport_records:
            self.sport_store.rewrite_records(sport_records)
        else:
            demo_sports = [
                SportRecord(self.profile.student_id, self.profile.name, self.profile.class_name, "2026-06-01", "足球", "球类", "GPS实景打卡", "校园操场", 75, 5.4, 8200, 142, estimate_calories("足球", 75, self.profile.weight), "已通过", "操场围栏内打卡"),
                SportRecord(self.profile.student_id, self.profile.name, self.profile.class_name, "2026-06-03", "力量训练", "健身", "手动录入", "健身房", 50, 0, 1600, 128, estimate_calories("力量训练", 50, self.profile.weight), "已通过", "上肢+核心"),
                SportRecord("20250102", "成员2", self.profile.class_name, "2026-06-04", "跑步", "跑步", "设备同步", "田径场", 35, 4.2, 5600, 150, estimate_calories("跑步", 35, 60), "已通过", "Keep同步"),
                SportRecord("20250103", "成员3", self.profile.class_name, "2026-06-05", "篮球", "球类", "补卡申请", "篮球场", 60, 3.0, 7200, 138, estimate_calories("篮球", 60, 70), "待审批", "上传比赛截图作为凭证"),
            ]
            self.sport_store.rewrite_records(demo_sports)
        if not self.health_store.load():
            samples = [
                HealthLog(self.profile.student_id, self.profile.name, "2026-06-02", self.profile.weight, 7.5, "三餐正常，晚饭偏清淡", 72, "正常", "无", ""),
                HealthLog(self.profile.student_id, self.profile.name, "2026-06-04", self.profile.weight - 0.2, 6.5, "蛋白质充足，水分一般", 76, "疲劳", "小腿酸痛", ""),
            ]
            self.health_store.rewrite(samples)
        if not self.test_store.load():
            score = 78.0
            self.test_store.rewrite([
                PhysicalTestRecord(self.profile.student_id, self.profile.name, self.profile.gender, 2026, 76, 225, self.profile.lung_capacity, 12, score, evaluate_physical_test(score))
            ])

    def refresh_all(self) -> None:
        if not self._validate_filter_dates():
            return
        self.profile = self.profile_store.load()
        self.all_records = self.sport_store.load_records()
        self.health_logs = self.health_store.load()
        self.tests = self.test_store.load()
        self.visible_records = filter_records(
            self.all_records,
            keyword=self.filter_keyword.get() if hasattr(self, "filter_keyword") else "",
            sport_type=self.filter_sport.get() if hasattr(self, "filter_sport") else "全部",
            category=self.filter_category.get() if hasattr(self, "filter_category") else "全部",
            status=self.filter_status.get() if hasattr(self, "filter_status") else "全部",
            start_day=self.filter_start.get() if hasattr(self, "filter_start") else "",
            end_day=self.filter_end.get() if hasattr(self, "filter_end") else "",
        )
        self._refresh_dashboard()
        self._refresh_sport_table()
        self._refresh_health_table()
        self._refresh_analysis()
        self._refresh_teacher_tables()
        self._refresh_admin_lists()
        self.refresh_admin_overview()
        self._refresh_social_tables()
        self._refresh_profile_preview()

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
        self._draw_bar_chart(self.sport_chart, daily_trend(self.all_records, 7), "分钟")
        self._fill_latest_tree()

    def _fill_latest_tree(self) -> None:
        self.latest_tree.delete(*self.latest_tree.get_children())
        for index, record in enumerate(sorted(self.all_records, key=lambda r: r.day, reverse=True)[:20], start=1):
            tag = "odd" if index % 2 else "even"
            self.latest_tree.insert("", "end", values=(index, record.name, record.class_name, record.day, record.sport_type, record.category, record.checkin_method, record.location, f"{record.duration}分", record.status), tags=(tag,))

    def _refresh_sport_table(self) -> None:
        self.sport_tree.delete(*self.sport_tree.get_children())
        for index, r in enumerate(self.visible_records, start=1):
            tag = "odd" if index % 2 else "even"
            self.sport_tree.insert("", "end", iid=str(index - 1), values=(
                index, r.student_id, r.name, r.class_name, r.day, r.sport_type, r.category, r.checkin_method, r.location,
                f"{r.duration}分", f"{r.distance:.2f}", r.steps, r.heart_rate, f"{r.calories:.1f}", r.status,
            ), tags=(tag,))

    def _refresh_health_table(self) -> None:
        self.health_tree.delete(*self.health_tree.get_children())
        for index, h in enumerate(sorted(self.health_logs, key=lambda x: x.day, reverse=True), start=1):
            tag = "odd" if index % 2 else "even"
            self.health_tree.insert("", "end", iid=str(index - 1), values=(index, h.student_id, h.name, h.day, f"{h.weight:.1f}", f"{h.sleep_hours:.1f}h", h.meals, h.heart_rate, h.fatigue_level, h.injury_note, h.menstrual_note), tags=(tag,))

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
        self._draw_line_chart(self.weight_chart, weight_trend(self.health_logs), "体重 kg")
        self.analysis_hint.set("说明：桌面版使用本地 CSV/JSON 数据进行智能分析；真实项目可进一步接入教务系统、手环 API、GPS 围栏和小程序端。")

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
            self.pending_tree.insert("", "end", iid=str(self.all_records.index(r)), values=(index, r.student_id, r.name, r.day, r.sport_type, r.checkin_method, r.location, f"{r.duration}分", r.remark, r.status), tags=(tag,))

    def _refresh_admin_lists(self) -> None:
        self.point_list.delete(0, tk.END)
        for point in self.config_points:
            self.point_list.insert(tk.END, point)

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
            f"计分规则：{self.score_rule.get() if hasattr(self, 'score_rule') else '默认规则'}",
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
    # 图表绘制
    # ------------------------------------------------------------------
    def _draw_bar_chart(self, canvas: tk.Canvas, data: list[tuple[str, int]], unit: str) -> None:
        canvas.delete("all")
        canvas.update_idletasks()
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        padding = 42
        max_value = max([value for _, value in data] + [30])
        canvas.create_line(padding, height - padding, width - padding, height - padding, fill=COLORS["border"], width=2)
        canvas.create_text(padding, 18, text=unit, anchor="w", fill=COLORS["muted"], font=(FONT, 11, "bold"))
        if not data:
            canvas.create_text(width / 2, height / 2, text="暂无数据", fill=COLORS["muted"], font=(FONT, 14))
            return
        bar_area_width = width - padding * 2
        bar_width = max(26, bar_area_width // (len(data) * 2))
        gap = (bar_area_width - bar_width * len(data)) / max(len(data) - 1, 1)
        for i, (label, value) in enumerate(data):
            x1 = padding + i * (bar_width + gap)
            x2 = x1 + bar_width
            bar_height = (height - padding * 2) * value / max_value if max_value else 0
            y1 = height - padding - bar_height
            y2 = height - padding
            canvas.create_rectangle(x1, y1, x2, y2, fill=COLORS["primary"], outline="")
            canvas.create_text((x1 + x2) / 2, y1 - 12, text=str(value), fill=COLORS["text"], font=(FONT, 10, "bold"))
            canvas.create_text((x1 + x2) / 2, height - 18, text=label, fill=COLORS["muted"], font=(FONT, 10))

    def _draw_line_chart(self, canvas: tk.Canvas, data: list[tuple[str, float]], unit: str) -> None:
        canvas.delete("all")
        canvas.update_idletasks()
        width = max(canvas.winfo_width(), 460)
        height = max(canvas.winfo_height(), 300)
        padding = 48
        canvas.create_text(padding, 20, text=unit, anchor="w", fill=COLORS["muted"], font=(FONT, 11, "bold"))
        canvas.create_line(padding, height - padding, width - padding, height - padding, fill=COLORS["border"], width=2)
        if len(data) < 2:
            canvas.create_text(width / 2, height / 2, text="自测记录不足，保存几天后会显示趋势", fill=COLORS["muted"], font=(FONT, 13))
            return
        values = [v for _, v in data]
        lo = min(values) - 1
        hi = max(values) + 1
        span = max(hi - lo, 1)
        points = []
        for i, (label, value) in enumerate(data):
            x = padding + i * (width - padding * 2) / max(len(data) - 1, 1)
            y = height - padding - (value - lo) / span * (height - padding * 2)
            points.append((x, y, label, value))
        for i in range(len(points) - 1):
            canvas.create_line(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], fill=COLORS["accent"], width=3)
        for x, y, label, value in points:
            canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=COLORS["accent"], outline="white", width=2)
            canvas.create_text(x, y - 18, text=str(value), fill=COLORS["text"], font=(FONT, 10, "bold"))
            canvas.create_text(x, height - 18, text=label, fill=COLORS["muted"], font=(FONT, 10))

    # ------------------------------------------------------------------
    # 操作方法：打卡、档案、自测、体测
    # ------------------------------------------------------------------
    def _make_sport_record(self, status: str) -> SportRecord:
        sport_type = self.sport_vars["运动类型"].get()
        duration = to_int(self.sport_vars["时长(分钟)"].get())
        weight = to_float(self.sport_vars["体重(kg)"].get(), self.profile.weight)
        calories = estimate_calories(sport_type, duration, weight)
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
        try:
            student_id = self.sport_vars["学号"].get().strip()
            if student_id in self.blacklist:
                messagebox.showwarning("权限限制", "该学号在黑名单中，暂时限制打卡。")
                return
            record = self._make_sport_record("已通过")
            min_duration = to_int(self.min_duration_rule.get(), 20) if hasattr(self, "min_duration_rule") else 20
            if record.duration < min_duration:
                record.status = "待审批"
                record.remark = (record.remark + f"｜低于最短有效时长 {min_duration} 分钟，需老师审核").strip("｜")
            self.sport_store.save_record(record)
            self.clear_sport_form(keep_basic=True)
            self.refresh_all()
            messagebox.showinfo("保存成功", f"已保存 {record.name} 的 {record.sport_type} 打卡，估算消耗 {record.calories} kcal。")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查输入内容：{exc}")

    def add_makeup_record(self) -> None:
        try:
            self.sport_vars["打卡方式"].set("补卡申请")
            record = self._make_sport_record("待审批")
            if not record.remark:
                record.remark = "补卡申请：已上传/补充凭证说明"
            self.sport_store.save_record(record)
            self.clear_sport_form(keep_basic=True)
            self.refresh_all()
            messagebox.showinfo("提交成功", "补卡申请已提交，等待体育老师在线审批。")
        except ValueError as exc:
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
            self.refresh_all()
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
            self.refresh_all()
            messagebox.showinfo("保存成功", "健康自测记录已保存。")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查自测内容：{exc}")

    def add_test_record(self) -> None:
        try:
            total_score = to_float(self.test_vars["总分"].get())
            rating = evaluate_physical_test(total_score)
            record = PhysicalTestRecord(
                student_id=self.test_vars["学号"].get(),
                name=self.test_vars["姓名"].get(),
                gender=self.test_vars["性别"].get(),
                year=to_int(self.test_vars["年份"].get()),
                run_score=to_float(self.test_vars["800/1000米"].get()),
                long_jump=to_float(self.test_vars["立定跳远(cm)"].get()),
                lung_capacity=to_int(self.test_vars["肺活量"].get()),
                sit_reach=to_float(self.test_vars["坐位体前屈(cm)"].get()),
                total_score=total_score,
                rating=rating,
            )
            self.test_store.append(record)
            self.refresh_all()
            extra = "\n系统已生成补强任务建议。" if rating == "不及格" else ""
            messagebox.showinfo("体测保存成功", f"评级：{rating}{extra}")
        except ValueError as exc:
            messagebox.showerror("输入错误", f"请检查体测内容：{exc}")

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
        self.refresh_all()

    def delete_selected(self) -> None:
        selected = self.sport_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在打卡明细表中选择记录。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(selected)} 条打卡记录吗？"):
            return
        selected_records = [self.visible_records[int(item)] for item in selected]
        remaining = self.all_records.copy()
        for record in selected_records:
            try:
                remaining.remove(record)
            except ValueError:
                continue
        self.sport_store.rewrite_records(remaining)
        self.refresh_all()
        messagebox.showinfo("删除成功", "选中打卡记录已删除。")

    def delete_health_log(self) -> None:
        selected = self.health_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择健康自测记录。")
            return
        sorted_logs = sorted(self.health_logs, key=lambda x: x.day, reverse=True)
        selected_logs = [sorted_logs[int(item)] for item in selected]
        remaining = self.health_logs.copy()
        for log in selected_logs:
            try:
                remaining.remove(log)
            except ValueError:
                continue
        self.health_store.rewrite(remaining)
        self.refresh_all()
        messagebox.showinfo("删除成功", "选中健康自测记录已删除。")

    def review_selected(self, status: str) -> None:
        selected = self.pending_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择待审核补卡/异常记录。")
            return
        for item in selected:
            record_index = int(item)
            self.all_records[record_index].status = status
            if status == "已驳回" and "疑似异常" not in self.all_records[record_index].remark:
                self.all_records[record_index].remark = (self.all_records[record_index].remark + "｜疑似异常或凭证不足").strip("｜")
        self.sport_store.rewrite_records(self.all_records)
        self.refresh_all()
        messagebox.showinfo("审核完成", f"已将选中记录标记为：{status}")

    def publish_task(self) -> None:
        messagebox.showinfo("任务发布成功", f"已发布运动作业：{self.teacher_task.get()}\n地点：{self.teacher_location.get()}\n有效期：{self.teacher_deadline.get()}")

    def add_location_point(self) -> None:
        point = self.new_point.get().strip()
        if not point:
            messagebox.showwarning("提示", "请输入点位名称。")
            return
        if point not in self.config_points:
            self.config_points.append(point)
            self.new_point.set("")
            self._refresh_admin_lists()
            self.refresh_admin_overview()
            # 更新相关下拉框的值
            self.sport_vars["地点"].set(point)
            messagebox.showinfo("添加成功", f"已添加校园打卡点位：{point}")

    def delete_location_point(self) -> None:
        selection = self.point_list.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的点位。")
            return
        point = self.point_list.get(selection[0])
        if point in self.config_points:
            self.config_points.remove(point)
            self._refresh_admin_lists()
            self.refresh_admin_overview()

    def add_blacklist(self) -> None:
        student_id = self.black_id.get().strip()
        if not student_id:
            messagebox.showwarning("提示", "请输入学号。")
            return
        self.blacklist.add(student_id)
        self.black_id.set("")
        self.refresh_admin_overview()
        messagebox.showinfo("已加入黑名单", f"学号 {student_id} 已限制打卡权限。")

    def export_report(self) -> None:
        if not self.all_records and not self.health_logs:
            messagebox.showwarning("提示", "暂无数据，无法生成报告。")
            return
        REPORT_DIR.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="保存运动健康周报",
            initialdir=REPORT_DIR,
            initialfile=f"health_report_{date.today()}.txt",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not path:
            return
        Path(path).write_text(weekly_report(self.profile, self.all_records, self.health_logs, self.tests), encoding="utf-8")
        messagebox.showinfo("导出成功", f"健康周报已导出：\n{path}")

    def export_current_csv(self) -> None:
        if not self.visible_records:
            messagebox.showwarning("提示", "当前没有可导出的打卡数据。")
            return
        path = filedialog.asksaveasfilename(
            title="导出当前筛选后的打卡 CSV",
            initialdir=BASE_DIR,
            initialfile=f"sport_records_export_{date.today()}.csv",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
        )
        if not path:
            return
        self.sport_store.export(self.visible_records, path)
        messagebox.showinfo("导出成功", f"CSV 已导出：\n{path}")

    def export_class_report(self) -> None:
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
        paths = [self.sport_store.backup(BACKUP_DIR), self.health_store.backup(BACKUP_DIR), self.test_store.backup(BACKUP_DIR)]
        messagebox.showinfo("备份成功", "已备份：\n" + "\n".join(str(p) for p in paths))


def main() -> None:
    if sys.platform.startswith("win"):
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    app = SportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
