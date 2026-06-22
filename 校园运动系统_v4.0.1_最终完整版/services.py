"""业务服务层：集中权限、打卡、审核、用户与配置规则。"""
from __future__ import annotations

from database import AuditDAO, AuthDAO, SettingsDAO
from models import SportRecord
from repositories import SportRepository


class AuthService:
    def __init__(self, actor: dict | None = None):
        self.actor = actor
        self.dao = AuthDAO()
        self.audit = AuditDAO()

    def login(self, account: str, password: str) -> dict | None:
        return self.dao.authenticate(account.strip(), password)

    def change_password(self, account: str, new_password: str,
                        current_password: str | None = None) -> None:
        self.dao.change_password(account, new_password, current_password)

    def _require_admin(self) -> str:
        if not self.actor or self.actor.get("role") != "admin":
            raise PermissionError("只有管理员可以管理用户")
        return str(self.actor["student_id"])

    def list_users(self) -> list[dict]:
        self._require_admin()
        return self.dao.get_all_users()

    def add_user(self, account: str, name: str, password: str,
                 role: str, class_name: str) -> None:
        actor = self._require_admin()
        self.dao.add_user(account.strip(), name.strip(), password, role, class_name.strip())
        self.audit.log(actor, "add_user", "user", account, {"role": role})

    def update_user(self, account: str, name: str, role: str, class_name: str) -> None:
        actor = self._require_admin()
        self.dao.update_user(account, name, role, class_name)
        self.audit.log(actor, "update_user", "user", account, {"role": role})

    def set_active(self, account: str, active: bool) -> None:
        actor = self._require_admin()
        if account == actor and not active:
            raise ValueError("不能禁用当前登录的管理员账号")
        self.dao.set_active(account, active)
        self.audit.log(actor, "enable_user" if active else "disable_user", "user", account)

    def reset_password(self, account: str, temporary_password: str = "123456") -> None:
        actor = self._require_admin()
        self.dao.reset_password(account, temporary_password)
        self.audit.log(actor, "reset_password", "user", account)


class SportService:
    def __init__(self, user: dict):
        self.user = user
        self.repo = SportRepository(user)
        self.settings = SettingsDAO()
        self.audit = AuditDAO()

    def submit(self, record: SportRecord, makeup: bool = False) -> SportRecord:
        if self.user.get("role") != "student":
            raise PermissionError("只有学生账号可以提交打卡")
        if makeup:
            record.status = "待审批"
            record.checkin_method = "补卡申请"
        else:
            minimum = int(self.settings.get("min_duration", 20))
            if record.duration < minimum:
                record.status = "待审批"
                record.remark = (
                    record.remark + f"｜低于最短有效时长 {minimum} 分钟"
                ).strip("｜")
        self.repo.save_record(record)
        self.audit.log(str(self.user["student_id"]), "submit_sport", "sport_record",
                       str(record.record_id), {"status": record.status})
        return record

    def delete(self, record_id: int) -> None:
        self.repo.delete(record_id)
        self.audit.log(str(self.user["student_id"]), "delete_sport", "sport_record", str(record_id))

    def review(self, record_id: int, status: str) -> None:
        if self.user.get("role") not in {"teacher", "admin"}:
            raise PermissionError("只有教师或管理员可以审核")
        if status not in {"已通过", "已驳回"}:
            raise ValueError("审核状态不合法")
        self.repo.update_status(record_id, status)
        self.audit.log(str(self.user["student_id"]), "review_sport", "sport_record",
                       str(record_id), {"status": status})


class AdminSettingsService:
    def __init__(self, user: dict):
        self.user = user
        self.settings = SettingsDAO()
        self.audit = AuditDAO()

    def _require_admin(self) -> str:
        if self.user.get("role") != "admin":
            raise PermissionError("只有管理员可以修改系统配置")
        return str(self.user["student_id"])

    def save_score_rule(self, rule: dict[str, int]) -> None:
        actor = self._require_admin()
        self.settings.set_score_rule(rule)
        self.audit.log(actor, "update_score_rule", "settings", "score_rule", rule)

    def get_score_rule(self) -> dict[str, int]:
        return self.settings.get_score_rule()

    def save_locations(self, locations: list[str]) -> None:
        actor = self._require_admin()
        self.settings.set("locations", locations)
        self.audit.log(actor, "update_locations", "settings", "locations", {"locations": locations})

    def save_blacklist(self, student_ids: list[str]) -> None:
        actor = self._require_admin()
        self.settings.set("blacklist", student_ids)
        self.audit.log(actor, "update_blacklist", "settings", "blacklist", {"student_ids": student_ids})

    def save_teacher_task(self, task: str, deadline: str, location: str) -> None:
        if self.user.get("role") not in {"teacher", "admin"}:
            raise PermissionError("只有教师或管理员可以发布任务")
        self.settings.set("teacher_task", task)
        self.settings.set("teacher_deadline", deadline)
        self.settings.set("teacher_location", location)
        self.audit.log(str(self.user["student_id"]), "publish_task", "settings", "teacher_task",
                       {"task": task, "deadline": deadline, "location": location})
