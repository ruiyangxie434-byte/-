"""数据模型模块：定义校园运动健康系统中用到的核心对象。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime

DATE_FORMAT = "%Y-%m-%d"


def normalize_date(value: str) -> str:
    """校验并标准化日期字符串，返回 YYYY-MM-DD。"""
    value = str(value).strip()
    try:
        return datetime.strptime(value, DATE_FORMAT).strftime(DATE_FORMAT)
    except ValueError as exc:
        raise ValueError("日期格式应为 YYYY-MM-DD，例如 2026-06-06") from exc


def to_float(value: str | int | float, default: float = 0.0) -> float:
    """安全转换为浮点数。"""
    value = str(value).strip()
    if value == "":
        return default
    return float(value)


def to_int(value: str | int | float, default: int = 0) -> int:
    """安全转换为整数，支持用户输入 30.0 这类内容。"""
    value = str(value).strip()
    if value == "":
        return default
    return int(float(value))


@dataclass(slots=True)
class SportRecord:
    """一条运动打卡记录。"""

    student_id: str
    name: str
    class_name: str
    day: str
    sport_type: str
    category: str
    checkin_method: str
    location: str
    duration: int
    distance: float
    steps: int
    heart_rate: int
    calories: float
    status: str = "已通过"
    remark: str = ""
    record_id: int | None = None

    def __post_init__(self) -> None:
        self.student_id = self.student_id.strip() or "未填学号"
        self.name = self.name.strip()
        self.class_name = self.class_name.strip() or "未分班级"
        self.day = normalize_date(self.day)
        self.sport_type = self.sport_type.strip() or "其他"
        self.category = self.category.strip() or "课外体育"
        self.checkin_method = self.checkin_method.strip() or "手动录入"
        self.location = self.location.strip() or "未填写"
        self.duration = to_int(self.duration)
        self.distance = round(to_float(self.distance), 2)
        self.steps = to_int(self.steps)
        self.heart_rate = to_int(self.heart_rate)
        self.calories = round(to_float(self.calories), 1)
        self.status = self.status.strip() or "已通过"
        self.remark = self.remark.strip()

        if not self.name:
            raise ValueError("姓名不能为空")
        if self.duration <= 0:
            raise ValueError("运动时长必须大于 0")
        if self.duration > 600:
            raise ValueError("单次运动时长不能超过 600 分钟")
        if self.distance < 0:
            raise ValueError("运动距离不能小于 0")
        if self.steps < 0:
            raise ValueError("步数不能小于 0")
        if self.heart_rate != 0 and not 30 <= self.heart_rate <= 240:
            raise ValueError("心率应在 30-240 次/分钟之间，未知时填 0")
        if self.calories < 0:
            raise ValueError("热量消耗不能小于 0")

    def to_row(self) -> list[str]:
        return [
            self.student_id,
            self.name,
            self.class_name,
            self.day,
            self.sport_type,
            self.category,
            self.checkin_method,
            self.location,
            str(self.duration),
            f"{self.distance:.2f}",
            str(self.steps),
            str(self.heart_rate),
            f"{self.calories:.1f}",
            self.status,
            self.remark,
        ]

    @staticmethod
    def from_row(row: list[str]) -> "SportRecord":
        """兼容新版 15 列和旧版 6 列 CSV。"""
        if len(row) >= 15:
            return SportRecord(
                student_id=row[0], name=row[1], class_name=row[2], day=row[3],
                sport_type=row[4], category=row[5], checkin_method=row[6], location=row[7],
                duration=to_int(row[8]), distance=to_float(row[9]), steps=to_int(row[10]),
                heart_rate=to_int(row[11]), calories=to_float(row[12]), status=row[13], remark=row[14],
            )
        if len(row) >= 6:
            return SportRecord(
                student_id="20250101", name=row[0], class_name="25数据科学与大数据技术本3",
                day=row[1], sport_type=row[2], category="课外体育", checkin_method="手动录入",
                location="校园操场", duration=to_int(row[3]), distance=to_float(row[4]),
                steps=0, heart_rate=0, calories=to_float(row[5]), status="已通过", remark="旧数据自动兼容",
            )
        raise ValueError("CSV 行字段不足")


@dataclass(slots=True)
class HealthProfile:
    """学生个人健康档案与目标设置。"""

    student_id: str = "20250101"
    name: str = "谢睿阳"
    role: str = "学生"
    class_name: str = "25数据科学与大数据技术本3"
    gender: str = "男"
    height: float = 175.0
    weight: float = 67.0
    body_fat: float = 15.0
    blood_pressure: str = "120/80"
    lung_capacity: int = 4200
    injuries: str = "无"
    allergies: str = "无"
    medical_note: str = "体检数据正常"
    weekly_target: int = 150
    step_goal: int = 8000
    fitness_goal: str = "增肌"

    def normalize(self) -> "HealthProfile":
        self.student_id = self.student_id.strip() or "未填学号"
        self.name = self.name.strip() or "未命名学生"
        self.role = self.role.strip() or "学生"
        self.class_name = self.class_name.strip() or "未分班级"
        self.gender = self.gender.strip() or "男"
        self.height = round(to_float(self.height, 170), 1)
        self.weight = round(to_float(self.weight, 65), 1)
        self.body_fat = round(to_float(self.body_fat, 0), 1)
        self.lung_capacity = to_int(self.lung_capacity)
        self.weekly_target = max(1, to_int(self.weekly_target, 150))
        self.step_goal = max(1, to_int(self.step_goal, 8000))
        self.fitness_goal = self.fitness_goal.strip() or "体测达标"
        if not 100 <= self.height <= 250:
            raise ValueError("身高应在 100-250 cm 之间")
        if not 20 <= self.weight <= 300:
            raise ValueError("体重应在 20-300 kg 之间")
        if not 0 <= self.body_fat <= 70:
            raise ValueError("体脂率应在 0-70% 之间")
        return self

    def to_dict(self) -> dict[str, object]:
        self.normalize()
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, object]) -> "HealthProfile":
        fields = HealthProfile.__dataclass_fields__.keys()
        kwargs = {key: data.get(key, getattr(HealthProfile(), key)) for key in fields}
        return HealthProfile(**kwargs).normalize()


@dataclass(slots=True)
class HealthLog:
    """日常健康自测记录。"""

    student_id: str
    name: str
    day: str
    weight: float
    sleep_hours: float
    meals: str
    heart_rate: int
    fatigue_level: str
    injury_note: str = "无"
    menstrual_note: str = ""
    record_id: int | None = None

    def __post_init__(self) -> None:
        self.student_id = self.student_id.strip() or "未填学号"
        self.name = self.name.strip() or "未命名学生"
        self.day = normalize_date(self.day)
        self.weight = round(to_float(self.weight), 1)
        self.sleep_hours = round(to_float(self.sleep_hours), 1)
        self.meals = self.meals.strip() or "未填写"
        self.heart_rate = to_int(self.heart_rate)
        self.fatigue_level = self.fatigue_level.strip() or "正常"
        self.injury_note = self.injury_note.strip() or "无"
        self.menstrual_note = self.menstrual_note.strip()
        if self.weight <= 0:
            raise ValueError("晨起体重必须大于 0")
        if not 20 <= self.weight <= 300:
            raise ValueError("晨起体重应在 20-300 kg 之间")
        if not 0 <= self.sleep_hours <= 24:
            raise ValueError("睡眠时长应在 0-24 小时之间")
        if self.heart_rate != 0 and not 30 <= self.heart_rate <= 240:
            raise ValueError("心率应在 30-240 次/分钟之间，未知时填 0")

    def to_row(self) -> list[str]:
        return [
            self.student_id, self.name, self.day, f"{self.weight:.1f}", f"{self.sleep_hours:.1f}",
            self.meals, str(self.heart_rate), self.fatigue_level, self.injury_note, self.menstrual_note,
        ]

    @staticmethod
    def from_row(row: list[str]) -> "HealthLog":
        return HealthLog(
            student_id=row[0], name=row[1], day=row[2], weight=to_float(row[3]),
            sleep_hours=to_float(row[4]), meals=row[5], heart_rate=to_int(row[6]),
            fatigue_level=row[7], injury_note=row[8] if len(row) > 8 else "无",
            menstrual_note=row[9] if len(row) > 9 else "",
        )


@dataclass(slots=True)
class PhysicalTestRecord:
    """体测专项成绩记录。"""

    student_id: str
    name: str
    gender: str
    year: int
    run_score: float
    long_jump: float
    lung_capacity: int
    sit_reach: float
    total_score: float
    rating: str = ""
    record_id: int | None = None

    def __post_init__(self) -> None:
        self.student_id = self.student_id.strip() or "未填学号"
        self.name = self.name.strip() or "未命名学生"
        self.gender = self.gender.strip() or "男"
        self.year = to_int(self.year, datetime.now().year)
        self.run_score = round(to_float(self.run_score), 1)
        self.long_jump = round(to_float(self.long_jump), 1)
        self.lung_capacity = to_int(self.lung_capacity)
        self.sit_reach = round(to_float(self.sit_reach), 1)
        self.total_score = round(to_float(self.total_score), 1)
        self.rating = self.rating.strip()
        if not 0 <= self.total_score <= 100:
            raise ValueError("体测总分应在 0-100 分之间")
        if not 2000 <= self.year <= datetime.now().year + 1:
            raise ValueError("体测年份超出合理范围")

    def to_row(self) -> list[str]:
        return [
            self.student_id, self.name, self.gender, str(self.year), f"{self.run_score:.1f}",
            f"{self.long_jump:.1f}", str(self.lung_capacity), f"{self.sit_reach:.1f}",
            f"{self.total_score:.1f}", self.rating,
        ]

    @staticmethod
    def from_row(row: list[str]) -> "PhysicalTestRecord":
        return PhysicalTestRecord(
            student_id=row[0], name=row[1], gender=row[2], year=to_int(row[3]),
            run_score=to_float(row[4]), long_jump=to_float(row[5]), lung_capacity=to_int(row[6]),
            sit_reach=to_float(row[7]), total_score=to_float(row[8]), rating=row[9] if len(row) > 9 else "",
        )
