"""
数据可视化模块
使用 matplotlib 在 tkinter 窗口中内嵌交互图表。

支持图表类型：
- 最近 N 天运动时长柱状图
- 体重趋势折线图
- 运动类型分布饼图
- 班级积分排行横向条形图
- 热量与时长双轴对比图
"""
from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from typing import TYPE_CHECKING

from config import CHART_DPI, CHART_FIG_SIZE, CHART_THEME

if TYPE_CHECKING:
    from models import HealthLog, SportRecord

# matplotlib 按需导入，避免在不需要图表时拖慢启动速度
try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# 设置中文字体，兼容 Windows / macOS / Linux
def _set_chinese_font() -> None:
    if not HAS_MPL:
        return
    import matplotlib.font_manager as fm
    candidates = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "DejaVu Sans"]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in candidates:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False


_set_chinese_font()

_PALETTE = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4", "#F97316", "#6B7280"]


def _apply_theme() -> None:
    try:
        plt.style.use(CHART_THEME)
    except OSError:
        plt.style.use("seaborn-v0_8-whitegrid")


# ───────────────────────────────────────────────────────────────
# 基础内嵌画布组件
# ───────────────────────────────────────────────────────────────
class ChartFrame(tk.Frame):
    """
    可复用的内嵌 matplotlib 画布 tkinter 组件。
    使用方法：
        cf = ChartFrame(parent, figsize=(8, 3.5))
        cf.pack(fill="both", expand=True)
        cf.draw_bar(labels, values, title="xxx")
    """

    def __init__(self, parent: tk.Widget, figsize: tuple[float, float] = CHART_FIG_SIZE, **kw):
        super().__init__(parent, bg="#FFFFFF", **kw)
        if not HAS_MPL:
            tk.Label(self, text="⚠ 图表功能需安装 matplotlib\npip install matplotlib",
                     font=("Microsoft YaHei UI", 11), fg="#DC2626", bg="#FEF2F2",
                     justify="center").pack(expand=True)
            self._canvas = None
            self.fig = None
            return

        _apply_theme()
        self.fig = Figure(figsize=figsize, dpi=CHART_DPI, tight_layout=True)
        self.fig.patch.set_facecolor("#FFFFFF")
        self._canvas = FigureCanvasTkAgg(self.fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

    def _clear(self) -> "Figure | None":
        if self.fig is None:
            return None
        self.fig.clf()
        return self.fig

    def _refresh(self) -> None:
        if self._canvas:
            self._canvas.draw_idle()

    # ── 柱状图 ──
    def draw_bar(
        self,
        labels: list[str],
        values: list[float],
        title: str = "",
        ylabel: str = "",
        color: str = _PALETTE[0],
    ) -> None:
        fig = self._clear()
        if fig is None:
            return
        ax = fig.add_subplot(111)
        bars = ax.bar(labels, values, color=color, width=0.55, zorder=3, edgecolor="white")
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=9, color="#374151")
        ax.set_title(title, fontsize=12, fontweight="bold", color="#1E293B", pad=8)
        ax.set_ylabel(ylabel, fontsize=9, color="#64748B")
        ax.tick_params(axis="x", labelsize=9, rotation=0)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(axis="y", alpha=0.35, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        self._refresh()

    # ── 折线图 ──
    def draw_line(
        self,
        labels: list[str],
        values: list[float],
        title: str = "",
        ylabel: str = "",
        color: str = _PALETTE[1],
    ) -> None:
        fig = self._clear()
        if fig is None:
            return
        ax = fig.add_subplot(111)
        ax.plot(labels, values, color=color, marker="o", linewidth=2.2,
                markersize=5, zorder=3)
        ax.fill_between(labels, values, alpha=0.12, color=color)
        for i, (x, y) in enumerate(zip(labels, values)):
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points",
                        xytext=(0, 7), ha="center", fontsize=8, color="#374151")
        ax.set_title(title, fontsize=12, fontweight="bold", color="#1E293B", pad=8)
        ax.set_ylabel(ylabel, fontsize=9, color="#64748B")
        ax.tick_params(axis="x", labelsize=9, rotation=0)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(alpha=0.35, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        self._refresh()

    # ── 饼图 ──
    def draw_pie(
        self,
        labels: list[str],
        values: list[float],
        title: str = "",
    ) -> None:
        fig = self._clear()
        if fig is None:
            return
        ax = fig.add_subplot(111)
        colors = _PALETTE[: len(values)]
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            pctdistance=0.78,
        )
        for t in autotexts:
            t.set_fontsize(8)
            t.set_color("white")
        ax.set_title(title, fontsize=12, fontweight="bold", color="#1E293B", pad=8)
        self._refresh()

    # ── 横向条形图（排行榜）──
    def draw_hbar(
        self,
        labels: list[str],
        values: list[float],
        title: str = "",
        xlabel: str = "",
    ) -> None:
        fig = self._clear()
        if fig is None:
            return
        ax = fig.add_subplot(111)
        colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]
        bars = ax.barh(labels, values, color=colors, height=0.55, zorder=3)
        ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=9, color="#374151")
        ax.set_title(title, fontsize=12, fontweight="bold", color="#1E293B", pad=8)
        ax.set_xlabel(xlabel, fontsize=9, color="#64748B")
        ax.tick_params(axis="y", labelsize=9)
        ax.tick_params(axis="x", labelsize=8)
        ax.grid(axis="x", alpha=0.35, zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
        ax.invert_yaxis()
        self._refresh()

    # ── 双轴对比图（时长 vs 热量）──
    def draw_dual(
        self,
        labels: list[str],
        values1: list[float],
        values2: list[float],
        title: str = "",
        label1: str = "时长(分钟)",
        label2: str = "热量(kcal)",
    ) -> None:
        fig = self._clear()
        if fig is None:
            return
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()
        x = range(len(labels))
        ax1.bar([i - 0.2 for i in x], values1, width=0.35, color=_PALETTE[0],
                label=label1, zorder=3, alpha=0.85)
        ax2.plot(list(x), values2, color=_PALETTE[3], marker="D", linewidth=2,
                 markersize=5, label=label2, zorder=4)
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(labels, fontsize=9, rotation=0)
        ax1.set_ylabel(label1, fontsize=9, color=_PALETTE[0])
        ax2.set_ylabel(label2, fontsize=9, color=_PALETTE[3])
        ax1.set_title(title, fontsize=12, fontweight="bold", color="#1E293B", pad=8)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper left")
        ax1.grid(axis="y", alpha=0.3, zorder=0)
        ax1.spines[["top"]].set_visible(False)
        self._refresh()


# ───────────────────────────────────────────────────────────────
# 高层便捷函数（供 main.py 直接调用）
# ───────────────────────────────────────────────────────────────
def render_duration_bar(frame: ChartFrame, records: list["SportRecord"], days: int = 7) -> None:
    """最近 N 天运动时长柱状图。"""
    from analytics import daily_trend
    trend = daily_trend(records, days)
    labels = [t[0] for t in trend]
    values = [float(t[1]) for t in trend]
    frame.draw_bar(labels, values, title=f"最近 {days} 天运动时长（分钟）", ylabel="分钟",
                   color="#3B82F6")


def render_weight_line(frame: ChartFrame, logs: list["HealthLog"], days: int = 10) -> None:
    """体重趋势折线图。"""
    from analytics import weight_trend
    trend = weight_trend(logs, days)
    if not trend:
        return
    labels = [t[0] for t in trend]
    values = [t[1] for t in trend]
    frame.draw_line(labels, values, title="体重趋势（kg）", ylabel="体重 kg", color="#10B981")


def render_sport_pie(frame: ChartFrame, records: list["SportRecord"]) -> None:
    """运动类型分布饼图。"""
    bucket: dict[str, int] = defaultdict(int)
    for r in records:
        if r.status == "已通过":
            bucket[r.sport_type] += r.duration
    if not bucket:
        return
    sorted_items = sorted(bucket.items(), key=lambda x: x[1], reverse=True)
    top = sorted_items[:6]
    labels = [i[0] for i in top]
    values = [float(i[1]) for i in top]
    frame.draw_pie(labels, values, title="运动类型时长分布")


def render_leaderboard_bar(frame: ChartFrame, records: list["SportRecord"], top_n: int = 8) -> None:
    """积分排行横向条形图。"""
    from analytics import leaderboard
    lb = leaderboard(records)[:top_n]
    if not lb:
        return
    labels = [f"{r[1]}（{r[2][:6]}）" for r in lb]
    values = [float(r[4]) for r in lb]           # 积分列
    frame.draw_hbar(labels[::-1], values[::-1], title="积分排行榜 TOP 8", xlabel="积分")


def render_dual_chart(frame: ChartFrame, records: list["SportRecord"], days: int = 7) -> None:
    """时长 vs 热量双轴对比图。"""
    from collections import defaultdict
    from datetime import date, timedelta
    today = date.today()
    dur_map: dict[str, float] = defaultdict(float)
    cal_map: dict[str, float] = defaultdict(float)
    for r in records:
        if r.status == "已通过":
            dur_map[r.day] += r.duration
            cal_map[r.day] += r.calories
    labels, vals1, vals2 = [], [], []
    for i in range(days - 1, -1, -1):
        key = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        labels.append(key[5:])
        vals1.append(dur_map[key])
        vals2.append(cal_map[key])
    frame.draw_dual(labels, vals1, vals2, title=f"最近 {days} 天时长 & 热量对比")
