"""
数据库模块单元测试
使用 SQLite 内存数据库（:memory:），测试完全隔离，不影响正式数据。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3
import threading
import pytest
from unittest.mock import patch

from models import SportRecord, HealthLog, PhysicalTestRecord


# ── 使用内存 DB 替代文件 DB ──
TEST_DB = Path(":memory:")


def _make_record(**kw) -> SportRecord:
    defaults = dict(
        student_id="20250101", name="测试用户", class_name="测试班级",
        day="2026-06-01", sport_type="跑步", category="课外体育",
        checkin_method="手动录入", location="操场",
        duration=30, distance=3.0, steps=4000,
        heart_rate=140, calories=280.0, status="已通过", remark="",
    )
    defaults.update(kw)
    return SportRecord(**defaults)


class TestPasswordHashing:
    def test_hash_is_deterministic(self):
        from database import _hash_password
        assert _hash_password("abc123") == _hash_password("abc123")

    def test_different_passwords_differ(self):
        from database import _hash_password
        assert _hash_password("abc123") != _hash_password("xyz789")

    def test_verify_correct_password(self):
        from database import verify_password, _hash_password
        hashed = _hash_password("secret")
        assert verify_password("secret", hashed) is True

    def test_verify_wrong_password(self):
        from database import verify_password, _hash_password
        hashed = _hash_password("secret")
        assert verify_password("wrong", hashed) is False


class TestDBBackup:
    def test_backup_creates_file(self, tmp_path):
        from database import init_db, backup_db, _get_conn, _local
        db_path = tmp_path / "test.db"
        # 重置线程本地连接
        _local.conn = None
        init_db(db_path)
        out = backup_db(db_path)
        assert out.exists()
        assert out.suffix == ".db"
        # 清理
        _local.conn = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
