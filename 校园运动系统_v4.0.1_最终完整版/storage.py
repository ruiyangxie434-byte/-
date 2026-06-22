"""数据存储模块：负责 CSV/JSON 文件创建、读取、追加、重写与备份。"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Generic, TypeVar

from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord

T = TypeVar("T")

SPORT_HEADER = ["学号", "姓名", "班级", "日期", "运动类型", "打卡分类", "打卡方式", "地点", "时长(分钟)", "距离(km)", "步数", "心率", "消耗(kcal)", "审核状态", "备注"]
HEALTH_HEADER = ["学号", "姓名", "日期", "晨起体重", "睡眠时长", "三餐饮食", "当日心率", "疲劳程度", "伤病记录", "生理期备注"]
TEST_HEADER = ["学号", "姓名", "性别", "年份", "800/1000米", "立定跳远(cm)", "肺活量", "坐位体前屈(cm)", "总分", "评级"]


class CsvTable(Generic[T]):
    """通用 CSV 表，负责持久化 dataclass 类数据。"""

    def __init__(self, file_path: str | Path, header: list[str], row_factory: Callable[[list[str]], T]):
        self.file_path = Path(file_path)
        self.header = header
        self.row_factory = row_factory
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            with self.file_path.open("w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(self.header)

    def load(self) -> list[T]:
        self._ensure_file()
        rows: list[T] = []
        with self.file_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                try:
                    rows.append(self.row_factory(row))
                except (ValueError, IndexError):
                    # 遇到坏数据时跳过，避免程序直接崩溃。
                    continue
        return rows

    def append(self, item: T) -> None:
        with self.file_path.open("a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(item.to_row())  # type: ignore[attr-defined]

    def rewrite(self, items: list[T]) -> None:
        with self.file_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(self.header)
            for item in items:
                writer.writerow(item.to_row())  # type: ignore[attr-defined]

    def export(self, items: list[T], target: str | Path) -> Path:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(self.header)
            for item in items:
                writer.writerow(item.to_row())  # type: ignore[attr-defined]
        return target_path

    def backup(self, backup_dir: str | Path) -> Path:
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_path / f"{self.file_path.stem}_backup_{stamp}.csv"
        shutil.copy2(self.file_path, target)
        return target


class SportStorage(CsvTable[SportRecord]):
    def __init__(self, file_path: str | Path):
        super().__init__(file_path, SPORT_HEADER, SportRecord.from_row)

    # 兼容旧代码命名，方便老师看懂
    def save_record(self, record: SportRecord) -> None:
        self.append(record)

    def load_records(self) -> list[SportRecord]:
        return self.load()

    def rewrite_records(self, records: list[SportRecord]) -> None:
        self.rewrite(records)


class HealthLogStorage(CsvTable[HealthLog]):
    def __init__(self, file_path: str | Path):
        super().__init__(file_path, HEALTH_HEADER, HealthLog.from_row)


class PhysicalTestStorage(CsvTable[PhysicalTestRecord]):
    def __init__(self, file_path: str | Path):
        super().__init__(file_path, TEST_HEADER, PhysicalTestRecord.from_row)


class ProfileStorage:
    """JSON 存储个人健康档案。"""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> HealthProfile:
        if not self.file_path.exists():
            profile = HealthProfile().normalize()
            self.save(profile)
            return profile
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return HealthProfile.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return HealthProfile().normalize()

    def save(self, profile: HealthProfile) -> None:
        self.file_path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
