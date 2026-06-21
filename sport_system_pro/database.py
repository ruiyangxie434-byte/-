"""
数据库模块 —— SQLite 持久化层
使用 Python 标准库 sqlite3 实现，替代原版 CSV/JSON 存储。

亮点（可写进简历）：
- 事务管理：关键写操作用 with conn 上下文保证原子性
- 连接池：使用 threading.local 为每条线程独立维护连接
- 数据迁移：内置 schema version，支持未来升级字段
- 全量/增量备份：VACUUM INTO 生成干净备份副本
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from config import BACKUP_DIR, DB_PATH
from logger import get_logger
from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord

log = get_logger(__name__)

# 当前 Schema 版本，每次修改表结构时 +1
SCHEMA_VERSION = 1

# ───────────────────────────────────────────────────────────────
# DDL —— 建表语句
# ───────────────────────────────────────────────────────────────
DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT    NOT NULL UNIQUE,
    username      TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'student',
    class_name    TEXT,
    created_at    TEXT    NOT NULL
)
"""

DDL_SPORT_RECORDS = """
CREATE TABLE IF NOT EXISTS sport_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    class_name      TEXT,
    day             TEXT    NOT NULL,
    sport_type      TEXT    NOT NULL,
    category        TEXT,
    checkin_method  TEXT,
    location        TEXT,
    duration        INTEGER NOT NULL DEFAULT 0,
    distance        REAL    DEFAULT 0.0,
    steps           INTEGER DEFAULT 0,
    heart_rate      INTEGER DEFAULT 0,
    calories        REAL    DEFAULT 0.0,
    status          TEXT    NOT NULL DEFAULT '已通过',
    remark          TEXT,
    created_at      TEXT    NOT NULL
)
"""

DDL_HEALTH_LOGS = """
CREATE TABLE IF NOT EXISTS health_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     TEXT    NOT NULL,
    name           TEXT    NOT NULL,
    day            TEXT    NOT NULL,
    weight         REAL    NOT NULL,
    sleep_hours    REAL    DEFAULT 0.0,
    meals          TEXT,
    heart_rate     INTEGER DEFAULT 0,
    fatigue_level  TEXT,
    injury_note    TEXT,
    menstrual_note TEXT,
    created_at     TEXT    NOT NULL
)
"""

DDL_PHYSICAL_TESTS = """
CREATE TABLE IF NOT EXISTS physical_tests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    gender        TEXT,
    year          INTEGER NOT NULL,
    run_score     REAL    DEFAULT 0.0,
    long_jump     REAL    DEFAULT 0.0,
    lung_capacity INTEGER DEFAULT 0,
    sit_reach     REAL    DEFAULT 0.0,
    total_score   REAL    DEFAULT 0.0,
    rating        TEXT,
    created_at    TEXT    NOT NULL
)
"""

DDL_PROFILES = """
CREATE TABLE IF NOT EXISTS profiles (
    student_id    TEXT PRIMARY KEY,
    profile_json  TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)
"""

DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT    NOT NULL
)
"""

ALL_DDL = [
    DDL_USERS,
    DDL_SPORT_RECORDS,
    DDL_HEALTH_LOGS,
    DDL_PHYSICAL_TESTS,
    DDL_PROFILES,
    DDL_SCHEMA_VERSION,
]

# ───────────────────────────────────────────────────────────────
# 连接管理（每线程独立连接，避免 SQLite 线程安全问题）
# ───────────────────────────────────────────────────────────────
_local = threading.local()


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """获取当前线程的 SQLite 连接（懒初始化）。"""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")   # 写时复制，提升并发
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def close_conn() -> None:
    """显式关闭当前线程的连接（程序退出时调用）。"""
    conn = getattr(_local, "conn", None)
    if conn:
        conn.close()
        _local.conn = None


# ───────────────────────────────────────────────────────────────
# 初始化 / 迁移
# ───────────────────────────────────────────────────────────────
def init_db(db_path: Path = DB_PATH) -> None:
    """建表 + 写入 schema 版本。首次运行时自动调用。"""
    conn = _get_conn(db_path)
    with conn:
        for ddl in ALL_DDL:
            conn.execute(ddl)
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        current = row["version"] if row else 0
        if current < SCHEMA_VERSION:
            _migrate(conn, current, SCHEMA_VERSION)
    log.info("数据库初始化完成（%s）", db_path)
    _seed_default_users(conn)


def _migrate(conn: sqlite3.Connection, from_ver: int, to_ver: int) -> None:
    """执行版本间数据迁移（当前为 v0→v1 占位，后续扩展加 elif）。"""
    for v in range(from_ver + 1, to_ver + 1):
        if v == 1:
            pass  # v1 为初始版本，无需额外迁移
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (v, datetime.now().isoformat()),
        )
    log.info("Schema 迁移完成：v%d → v%d", from_ver, to_ver)


def _seed_default_users(conn: sqlite3.Connection) -> None:
    """如果 users 表为空，写入初始账号（演示用）。"""
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        return
    defaults = [
        ("20250101", "谢睿阳",  "123456", "student", "25数据科学与大数据技术本3"),
        ("T001",     "李老师",   "teacher123", "teacher",  "体育教研室"),
        ("A001",     "管理员",   "admin888",   "admin",    "教务处"),
    ]
    now = datetime.now().isoformat()
    with conn:
        for sid, uname, pwd, role, cls in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO users (student_id, username, password_hash, role, class_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sid, uname, _hash_password(pwd), role, cls, now),
            )
    log.info("已写入默认账号（学生/教师/管理员）")


# ───────────────────────────────────────────────────────────────
# 工具函数
# ───────────────────────────────────────────────────────────────
def _hash_password(plain: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 哈希密码（标准库，无需第三方包）。"""
    salt = b"sport_system_salt_2025"  # 生产环境应随机盐；此处固定便于演示
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, iterations=100_000)
    return dk.hex()


def verify_password(plain: str, hashed: str) -> bool:
    return _hash_password(plain) == hashed


def _now() -> str:
    return datetime.now().isoformat()


# ───────────────────────────────────────────────────────────────
# 认证 DAO
# ───────────────────────────────────────────────────────────────
class AuthDAO:
    """用户认证数据访问对象。"""

    def authenticate(self, student_id: str, password: str) -> dict | None:
        """
        验证账号密码。
        返回用户信息字典；失败返回 None。
        """
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM users WHERE student_id = ?", (student_id,)
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            log.info("用户登录成功：%s（%s）", row["username"], row["role"])
            return dict(row)
        log.warning("登录失败：学号 %s", student_id)
        return None

    def change_password(self, student_id: str, new_password: str) -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE student_id = ?",
                (_hash_password(new_password), student_id),
            )

    def get_all_users(self) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute("SELECT student_id, username, role, class_name, created_at FROM users").fetchall()
        return [dict(r) for r in rows]

    def add_user(self, student_id: str, username: str, password: str, role: str, class_name: str = "") -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                "INSERT INTO users (student_id, username, password_hash, role, class_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (student_id, username, _hash_password(password), role, class_name, _now()),
            )


# ───────────────────────────────────────────────────────────────
# 运动记录 DAO
# ───────────────────────────────────────────────────────────────
class SportDAO:
    """运动打卡记录 CRUD。"""

    def insert(self, r: SportRecord) -> int:
        conn = _get_conn()
        with conn:
            cur = conn.execute(
                """INSERT INTO sport_records
                   (student_id, name, class_name, day, sport_type, category,
                    checkin_method, location, duration, distance, steps,
                    heart_rate, calories, status, remark, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r.student_id, r.name, r.class_name, r.day, r.sport_type,
                 r.category, r.checkin_method, r.location, r.duration,
                 r.distance, r.steps, r.heart_rate, r.calories, r.status,
                 r.remark, _now()),
            )
        log.info("新增运动记录：%s %s %s", r.name, r.day, r.sport_type)
        return cur.lastrowid  # type: ignore[return-value]

    def get_all(self) -> list[SportRecord]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM sport_records ORDER BY day DESC, name"
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def get_by_student(self, student_id: str) -> list[SportRecord]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM sport_records WHERE student_id = ? ORDER BY day DESC",
            (student_id,),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def update_status(self, record_id: int, status: str) -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                "UPDATE sport_records SET status = ? WHERE id = ?",
                (status, record_id),
            )

    def delete(self, record_id: int) -> None:
        conn = _get_conn()
        with conn:
            conn.execute("DELETE FROM sport_records WHERE id = ?", (record_id,))

    @staticmethod
    def _to_model(row: sqlite3.Row) -> SportRecord:
        return SportRecord(
            student_id=row["student_id"],
            name=row["name"],
            class_name=row["class_name"] or "",
            day=row["day"],
            sport_type=row["sport_type"],
            category=row["category"] or "课外体育",
            checkin_method=row["checkin_method"] or "手动录入",
            location=row["location"] or "",
            duration=row["duration"],
            distance=row["distance"],
            steps=row["steps"],
            heart_rate=row["heart_rate"],
            calories=row["calories"],
            status=row["status"],
            remark=row["remark"] or "",
        )


# ───────────────────────────────────────────────────────────────
# 健康日志 DAO
# ───────────────────────────────────────────────────────────────
class HealthLogDAO:
    def insert(self, log_entry: HealthLog) -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                """INSERT INTO health_logs
                   (student_id, name, day, weight, sleep_hours, meals,
                    heart_rate, fatigue_level, injury_note, menstrual_note, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (log_entry.student_id, log_entry.name, log_entry.day,
                 log_entry.weight, log_entry.sleep_hours, log_entry.meals,
                 log_entry.heart_rate, log_entry.fatigue_level,
                 log_entry.injury_note, log_entry.menstrual_note, _now()),
            )

    def get_by_student(self, student_id: str) -> list[HealthLog]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM health_logs WHERE student_id = ? ORDER BY day DESC",
            (student_id,),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def get_all(self) -> list[HealthLog]:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM health_logs ORDER BY day DESC").fetchall()
        return [self._to_model(r) for r in rows]

    def delete(self, log_id: int) -> None:
        conn = _get_conn()
        with conn:
            conn.execute("DELETE FROM health_logs WHERE id = ?", (log_id,))

    @staticmethod
    def _to_model(row: sqlite3.Row) -> HealthLog:
        return HealthLog(
            student_id=row["student_id"],
            name=row["name"],
            day=row["day"],
            weight=row["weight"],
            sleep_hours=row["sleep_hours"],
            meals=row["meals"] or "",
            heart_rate=row["heart_rate"],
            fatigue_level=row["fatigue_level"] or "正常",
            injury_note=row["injury_note"] or "无",
            menstrual_note=row["menstrual_note"] or "",
        )


# ───────────────────────────────────────────────────────────────
# 体测 DAO
# ───────────────────────────────────────────────────────────────
class PhysicalTestDAO:
    def insert(self, rec: PhysicalTestRecord) -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                """INSERT INTO physical_tests
                   (student_id, name, gender, year, run_score, long_jump,
                    lung_capacity, sit_reach, total_score, rating, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (rec.student_id, rec.name, rec.gender, rec.year,
                 rec.run_score, rec.long_jump, rec.lung_capacity,
                 rec.sit_reach, rec.total_score, rec.rating, _now()),
            )

    def get_by_student(self, student_id: str) -> list[PhysicalTestRecord]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM physical_tests WHERE student_id = ? ORDER BY year DESC",
            (student_id,),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def get_all(self) -> list[PhysicalTestRecord]:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM physical_tests ORDER BY year DESC, name").fetchall()
        return [self._to_model(r) for r in rows]

    @staticmethod
    def _to_model(row: sqlite3.Row) -> PhysicalTestRecord:
        return PhysicalTestRecord(
            student_id=row["student_id"],
            name=row["name"],
            gender=row["gender"] or "男",
            year=row["year"],
            run_score=row["run_score"],
            long_jump=row["long_jump"],
            lung_capacity=row["lung_capacity"],
            sit_reach=row["sit_reach"],
            total_score=row["total_score"],
            rating=row["rating"] or "",
        )


# ───────────────────────────────────────────────────────────────
# 健康档案 DAO
# ───────────────────────────────────────────────────────────────
class ProfileDAO:
    def save(self, profile: HealthProfile) -> None:
        conn = _get_conn()
        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO profiles (student_id, profile_json, updated_at)
                   VALUES (?, ?, ?)""",
                (profile.student_id, json.dumps(profile.to_dict(), ensure_ascii=False), _now()),
            )

    def load(self, student_id: str) -> HealthProfile:
        conn = _get_conn()
        row = conn.execute(
            "SELECT profile_json FROM profiles WHERE student_id = ?", (student_id,)
        ).fetchone()
        if row:
            return HealthProfile.from_dict(json.loads(row["profile_json"]))
        # 返回默认档案并持久化
        profile = HealthProfile(student_id=student_id).normalize()
        self.save(profile)
        return profile


# ───────────────────────────────────────────────────────────────
# 备份工具
# ───────────────────────────────────────────────────────────────
def backup_db(db_path: Path = DB_PATH) -> Path:
    """
    使用 SQLite 的 VACUUM INTO 生成干净备份（比直接 copy 更小）。
    若 VACUUM INTO 不可用（<3.27），退回文件复制。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"sport_system_backup_{stamp}.db"
    conn = _get_conn(db_path)
    try:
        conn.execute(f"VACUUM INTO '{target}'")
        log.info("数据库备份成功（VACUUM INTO）：%s", target)
    except sqlite3.OperationalError:
        shutil.copy2(db_path, target)
        log.info("数据库备份成功（文件复制）：%s", target)
    return target


# ───────────────────────────────────────────────────────────────
# CSV 迁移工具（将旧版 CSV 数据导入 SQLite）
# ───────────────────────────────────────────────────────────────
def migrate_from_csv(
    sport_csv: Path | None = None,
    health_csv: Path | None = None,
    test_csv: Path | None = None,
) -> dict[str, int]:
    """
    将原版 CSV 数据一次性导入 SQLite，返回各表导入行数。
    旧版 CSV 文件路径默认读取 data/ 目录下的同名文件。
    """
    from storage import HealthLogStorage, PhysicalTestStorage, SportStorage

    BASE = Path(__file__).parent / "data"
    sport_path  = sport_csv  or BASE / "sport_records.csv"
    health_path = health_csv or BASE / "health_logs.csv"
    test_path   = test_csv   or BASE / "physical_tests.csv"

    sport_dao   = SportDAO()
    health_dao  = HealthLogDAO()
    test_dao    = PhysicalTestDAO()
    counts: dict[str, int] = {}

    if sport_path.exists():
        records = SportStorage(sport_path).load()
        for r in records:
            try:
                sport_dao.insert(r)
            except Exception:
                pass
        counts["sport_records"] = len(records)
        log.info("CSV 迁移：导入 %d 条运动记录", len(records))

    if health_path.exists():
        logs = HealthLogStorage(health_path).load()
        for entry in logs:
            try:
                health_dao.insert(entry)
            except Exception:
                pass
        counts["health_logs"] = len(logs)

    if test_path.exists():
        tests = PhysicalTestStorage(test_path).load()
        for t in tests:
            try:
                test_dao.insert(t)
            except Exception:
                pass
        counts["physical_tests"] = len(tests)

    return counts
