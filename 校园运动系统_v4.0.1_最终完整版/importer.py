"""管理员 CSV/XLSX 批量导入，逐行校验并返回错误明细。"""
from __future__ import annotations

import csv
from pathlib import Path

from analytics import evaluate_physical_test, estimate_calories
from database import AuthDAO, PhysicalTestDAO, SportDAO
from models import PhysicalTestRecord, SportRecord, to_float, to_int


def _rows(path: str | Path) -> list[dict]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))
    if source.suffix.lower() == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("导入 XLSX 需要安装 openpyxl") from exc
        sheet = openpyxl.load_workbook(source, read_only=True, data_only=True).active
        values = list(sheet.iter_rows(values_only=True))
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        return [dict(zip(headers, row)) for row in values[1:]]
    raise ValueError("仅支持 CSV 或 XLSX 文件")


def _pick(row: dict, *names: str, default=""):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def import_file(path: str | Path, data_type: str) -> tuple[int, list[str]]:
    rows = _rows(path)
    success = 0
    errors: list[str] = []
    role_map = {"学生": "student", "体育老师": "teacher", "教师": "teacher", "管理员": "admin"}
    for number, row in enumerate(rows, start=2):
        try:
            if data_type == "学生名单":
                role_text = str(_pick(row, "角色", "role", default="student")).strip()
                AuthDAO().add_user(
                    str(_pick(row, "账号", "学号", "student_id")).strip(),
                    str(_pick(row, "姓名", "username")).strip(),
                    str(_pick(row, "初始密码", "password", default="123456")),
                    role_map.get(role_text, role_text),
                    str(_pick(row, "班级", "class_name")).strip(),
                )
            elif data_type == "运动记录":
                duration = to_int(_pick(row, "时长(分钟)", "duration"))
                weight = to_float(_pick(row, "体重(kg)", "weight", default=65))
                sport_type = str(_pick(row, "运动类型", "sport_type", default="其他"))
                record = SportRecord(
                    student_id=str(_pick(row, "学号", "student_id")),
                    name=str(_pick(row, "姓名", "name")),
                    class_name=str(_pick(row, "班级", "class_name")),
                    day=str(_pick(row, "日期", "day")), sport_type=sport_type,
                    category=str(_pick(row, "打卡分类", "category", default="课外体育")),
                    checkin_method=str(_pick(row, "打卡方式", "checkin_method", default="批量导入")),
                    location=str(_pick(row, "地点", "location", default="未填写")),
                    duration=duration, distance=to_float(_pick(row, "距离(km)", "distance")),
                    steps=to_int(_pick(row, "步数", "steps")),
                    heart_rate=to_int(_pick(row, "心率", "heart_rate")),
                    calories=estimate_calories(sport_type, duration, weight),
                    status=str(_pick(row, "审核状态", "status", default="待审批")),
                    remark=str(_pick(row, "备注", "remark", default="批量导入")),
                )
                SportDAO().insert(record)
            elif data_type == "体测成绩":
                total = to_float(_pick(row, "总分", "total_score"))
                PhysicalTestDAO().insert(PhysicalTestRecord(
                    student_id=str(_pick(row, "学号", "student_id")),
                    name=str(_pick(row, "姓名", "name")),
                    gender=str(_pick(row, "性别", "gender", default="男")),
                    year=to_int(_pick(row, "年份", "year")),
                    run_score=to_float(_pick(row, "跑步单项分", "800/1000米", "run_score")),
                    long_jump=to_float(_pick(row, "立定跳远(cm)", "long_jump")),
                    lung_capacity=to_int(_pick(row, "肺活量", "lung_capacity")),
                    sit_reach=to_float(_pick(row, "坐位体前屈(cm)", "sit_reach")),
                    total_score=total, rating=evaluate_physical_test(total),
                ))
            else:
                raise ValueError("未知导入类型")
            success += 1
        except Exception as exc:
            errors.append(f"第 {number} 行：{exc}")
    return success, errors
