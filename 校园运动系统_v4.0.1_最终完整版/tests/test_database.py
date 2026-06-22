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
    def test_hash_is_deterministic_with_same_salt(self):
        from database import _hash_password
        salt = b"0123456789abcdef"
        assert _hash_password("abc123", salt) == _hash_password("abc123", salt)

    def test_random_salts_produce_different_hashes(self):
        from database import _hash_password
        assert _hash_password("abc123") != _hash_password("abc123")

    def test_hash_contains_algorithm_metadata(self):
        from database import _hash_password
        assert _hash_password("abc123").startswith("pbkdf2_sha256$")

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


class TestIntegratedPersistence:
    def test_default_account_can_authenticate(self, tmp_path):
        from database import AuthDAO, close_conn, init_db, _local
        _local.conn = None
        init_db(tmp_path / "auth.db")
        user = AuthDAO().authenticate("20250101", "123456")
        assert user is not None
        assert user["role"] == "student"
        close_conn()

    def test_settings_round_trip(self, tmp_path):
        from database import SettingsDAO, close_conn, init_db, _local
        _local.conn = None
        init_db(tmp_path / "settings.db")
        settings = SettingsDAO()
        settings.set("locations", ["操场", "体育馆"])
        assert settings.get("locations") == ["操场", "体育馆"]
        close_conn()

    def test_student_repository_is_scoped(self, tmp_path):
        from database import SportDAO, close_conn, init_db, _local
        from repositories import SportRepository
        _local.conn = None
        init_db(tmp_path / "scope.db")
        SportDAO().insert(_make_record(student_id="S001", name="甲"))
        SportDAO().insert(_make_record(student_id="S002", name="乙"))
        student = {"student_id": "S001", "username": "甲", "role": "student", "class_name": "测试班级"}
        teacher = {"student_id": "T001", "username": "老师", "role": "teacher", "class_name": "体育组"}
        assert [r.student_id for r in SportRepository(student).load_records()] == ["S001"]
        assert len(SportRepository(teacher).load_records()) == 2
        close_conn()

    def test_initial_password_flag_and_disable(self, tmp_path):
        from database import AuthDAO, close_conn, init_db, _local
        _local.conn = None
        init_db(tmp_path / "users_v4.db")
        dao = AuthDAO()
        user = dao.authenticate("20250101", "123456")
        assert user["is_initial_password"] == 1
        dao.change_password("20250101", "newpass88")
        assert dao.authenticate("20250101", "newpass88")["is_initial_password"] == 0
        dao.set_active("20250101", False)
        assert dao.authenticate("20250101", "newpass88") is None
        close_conn()

    def test_unique_sport_and_health_constraints(self, tmp_path):
        from database import HealthLogDAO, SportDAO, close_conn, init_db, _local
        _local.conn = None
        init_db(tmp_path / "unique.db")
        SportDAO().insert(_make_record())
        with pytest.raises(ValueError, match="不能重复"):
            SportDAO().insert(_make_record())
        log = HealthLog("S1", "甲", "2026-06-01", 60, 7, "正常", 70, "正常")
        HealthLogDAO().insert(log)
        with pytest.raises(ValueError, match="每天只能"):
            HealthLogDAO().insert(HealthLog("S1", "甲", "2026-06-01", 60, 7, "正常", 70, "正常"))
        close_conn()

    def test_repository_blacklist_and_profile_weight(self, tmp_path):
        from analytics import estimate_calories
        from database import ProfileDAO, SettingsDAO, close_conn, init_db, _local
        from models import HealthProfile
        from repositories import SportRepository
        _local.conn = None
        init_db(tmp_path / "rules.db")
        user = {"student_id": "S001", "username": "甲", "role": "student", "class_name": "测试班"}
        ProfileDAO().save(HealthProfile(student_id="S001", name="甲", weight=80).normalize())
        repo = SportRepository(user)
        record = _make_record(student_id="S001", name="甲", calories=1)
        repo.save_record(record)
        assert record.calories == estimate_calories("跑步", 30, 80)
        SettingsDAO().set("blacklist", ["S001"])
        blocked = _make_record(student_id="S001", name="甲", day="2026-06-02")
        with pytest.raises(PermissionError, match="限制打卡"):
            repo.save_record(blocked)
        close_conn()

    def test_page_query_and_incremental_delete(self, tmp_path):
        from database import SportDAO, close_conn, init_db, _local
        _local.conn = None
        init_db(tmp_path / "page.db")
        dao = SportDAO()
        for index in range(5):
            dao.insert(_make_record(day=f"2026-06-{index + 1:02d}", sport_type=f"类型{index}"))
        page, total = dao.get_page(limit=2, offset=2)
        assert total == 5 and len(page) == 2
        dao.delete(page[0].record_id)
        assert len(dao.get_all()) == 4
        close_conn()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
