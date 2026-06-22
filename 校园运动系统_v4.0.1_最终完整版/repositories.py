"""面向 GUI 的 SQLite 仓储适配层。

保留旧版 storage.py 的易读方法名，让界面层无需关心 SQL，同时按登录角色
自动限制学生只能读取和修改自己的数据。
"""
from __future__ import annotations

from pathlib import Path

from database import (
    HealthLogDAO,
    PhysicalTestDAO,
    ProfileDAO,
    SettingsDAO,
    SportDAO,
    backup_db,
)
from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord


ROLE_LABELS = {"student": "学生", "teacher": "体育老师", "admin": "管理员"}


class _ScopedRepository:
    def __init__(self, user: dict):
        self.user = user
        self.student_id = str(user["student_id"])
        self.role = str(user["role"])

    @property
    def is_staff(self) -> bool:
        return self.role in {"teacher", "admin"}


class ProfileRepository(_ScopedRepository):
    def __init__(self, user: dict):
        super().__init__(user)
        self.dao = ProfileDAO()

    def load(self) -> HealthProfile:
        profile = self.dao.load(self.student_id)
        profile.student_id = self.student_id
        profile.name = str(self.user["username"])
        profile.class_name = str(self.user.get("class_name") or profile.class_name)
        profile.role = ROLE_LABELS.get(self.role, "学生")
        return profile.normalize()

    def save(self, profile: HealthProfile) -> None:
        # 身份字段来自登录会话，不接受界面伪造。
        profile.student_id = self.student_id
        profile.role = ROLE_LABELS.get(self.role, "学生")
        self.dao.save(profile.normalize())


class SportRepository(_ScopedRepository):
    def __init__(self, user: dict):
        super().__init__(user)
        self.dao = SportDAO()

    def load_records(self) -> list[SportRecord]:
        return self.dao.get_all() if self.is_staff else self.dao.get_by_student(self.student_id)

    def save_record(self, record: SportRecord) -> None:
        if not self.is_staff and record.student_id != self.student_id:
            raise PermissionError("学生账号不能写入他人运动数据")
        blacklist = set(SettingsDAO().get("blacklist", []))
        if record.student_id in blacklist:
            raise PermissionError("该账号已被管理员限制打卡")
        if not self.is_staff:
            # 热量只能使用健康档案基准体重计算，不接受表单伪造值。
            from analytics import estimate_calories
            profile = ProfileDAO().load(self.student_id)
            record.calories = estimate_calories(record.sport_type, record.duration, profile.weight)
        self.dao.insert(record)

    def rewrite_records(self, records: list[SportRecord]) -> None:
        self.dao.replace(records, None if self.is_staff else self.student_id)

    def delete(self, record_id: int) -> None:
        if not self.is_staff:
            owned = {r.record_id for r in self.dao.get_by_student(self.student_id)}
            if record_id not in owned:
                raise PermissionError("不能删除他人的运动记录")
        self.dao.delete(record_id)

    def update_status(self, record_id: int, status: str) -> None:
        if not self.is_staff:
            raise PermissionError("只有教师或管理员可以审核")
        self.dao.update_status(record_id, status)

    def get_page(self, page: int = 1, page_size: int = 40, **filters):
        return self.dao.get_page(
            limit=page_size,
            offset=(max(1, page) - 1) * page_size,
            student_id=None if self.is_staff else self.student_id,
            **filters,
        )


class HealthLogRepository(_ScopedRepository):
    def __init__(self, user: dict):
        super().__init__(user)
        self.dao = HealthLogDAO()

    def load(self) -> list[HealthLog]:
        return self.dao.get_all() if self.is_staff else self.dao.get_by_student(self.student_id)

    def append(self, item: HealthLog) -> None:
        if not self.is_staff and item.student_id != self.student_id:
            raise PermissionError("学生账号不能写入他人健康数据")
        self.dao.insert(item)

    def rewrite(self, items: list[HealthLog]) -> None:
        self.dao.replace(items, None if self.is_staff else self.student_id)

    def delete(self, record_id: int) -> None:
        if not self.is_staff:
            owned = {r.record_id for r in self.dao.get_by_student(self.student_id)}
            if record_id not in owned:
                raise PermissionError("不能删除他人的健康记录")
        self.dao.delete(record_id)


class PhysicalTestRepository(_ScopedRepository):
    def __init__(self, user: dict):
        super().__init__(user)
        self.dao = PhysicalTestDAO()

    def load(self) -> list[PhysicalTestRecord]:
        return self.dao.get_all() if self.is_staff else self.dao.get_by_student(self.student_id)

    def append(self, item: PhysicalTestRecord) -> None:
        if not self.is_staff and item.student_id != self.student_id:
            raise PermissionError("学生账号不能写入他人体测数据")
        self.dao.insert(item)

    def rewrite(self, items: list[PhysicalTestRecord]) -> None:
        self.dao.replace(items, None if self.is_staff else self.student_id)


def backup_database() -> Path:
    return backup_db()
