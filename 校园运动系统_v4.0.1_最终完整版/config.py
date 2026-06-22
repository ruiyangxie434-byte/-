"""
配置管理模块
统一管理数据库路径、日志级别、系统参数等配置项。
"""
from __future__ import annotations

from pathlib import Path

# ─────────────────────────── 路径配置 ───────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
DATA_DIR   = BASE_DIR / "data"
LOG_DIR    = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"

DB_PATH      = DATA_DIR / "sport_system.db"
PROFILE_PATH = DATA_DIR / "profile.json"          # 兼容旧版留存

# ─────────────────────────── 应用配置 ───────────────────────────
APP_TITLE   = "校园运动打卡与健康数据分析系统"
APP_VERSION = "4.0.1"
WINDOW_SIZE = "1400x900"
MIN_SIZE    = (1200, 780)

# ─────────────────────────── 安全配置 ───────────────────────────
PASSWORD_ITERATIONS = 260_000    # PBKDF2-HMAC-SHA256 迭代次数
PASSWORD_MIN_LEN    = 6

# ─────────────────────────── 数据配置 ───────────────────────────
BACKUP_KEEP_DAYS = 30           # 保留最近 N 天备份
WEEKLY_TARGET    = 150          # 默认每周目标分钟数
DAILY_STEP_GOAL  = 8000

# ─────────────────────────── 图表配置 ───────────────────────────
CHART_THEME     = "seaborn-v0_8-muted"   # matplotlib 主题
CHART_DPI       = 100
CHART_FIG_SIZE  = (8, 3.6)              # 默认图表尺寸（英寸）

# ─────────────────────────── 日志配置 ───────────────────────────
LOG_LEVEL    = "INFO"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB
LOG_BACKUP   = 3                  # 保留 3 个滚动备份

# 初始化目录
for _d in (DATA_DIR, LOG_DIR, REPORT_DIR, BACKUP_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
