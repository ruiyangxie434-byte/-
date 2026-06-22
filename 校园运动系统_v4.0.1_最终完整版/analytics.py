"""统计分析模块：完成热量估算、健康风险预警、体测评级、排行榜与报告生成。"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord

SPORT_FACTOR = {
    "跑步": 8.0,
    "足球": 7.5,
    "篮球": 7.0,
    "羽毛球": 5.5,
    "跳绳": 9.0,
    "骑行": 6.5,
    "力量训练": 6.0,
    "瑜伽": 3.0,
    "游泳": 8.3,
    "早操": 4.0,
    "其他": 5.0,
}
SPORT_TYPES = list(SPORT_FACTOR.keys())
CHECKIN_CATEGORIES = ["跑步", "球类", "健身", "早操", "课外体育", "体育课实训", "体测专项"]
CHECKIN_METHODS = ["GPS实景打卡", "手动录入", "设备同步", "补卡申请"]
LOCATIONS = ["校园操场", "篮球场", "田径场", "体育馆", "健身房", "游泳馆", "宿舍区", "校外/其他"]
ROLES = ["学生", "体育老师", "管理员"]
FATIGUE_LEVELS = ["轻松", "正常", "疲劳", "非常疲劳"]
GOALS = ["减脂", "增肌", "体测达标", "每日步数", "保持健康"]


def estimate_calories(sport_type: str, duration: int, weight: float = 65.0) -> float:
    """按 MET 简化公式估算热量：kcal = MET × 体重 kg × 小时。"""
    met = SPORT_FACTOR.get(sport_type, SPORT_FACTOR["其他"])
    return round(met * weight * duration / 60, 1)


def calc_bmi(height_cm: float, weight_kg: float) -> float:
    if height_cm <= 0:
        return 0.0
    return round(weight_kg / ((height_cm / 100) ** 2), 1)


def bmi_level(bmi: float) -> str:
    if bmi <= 0:
        return "暂无"
    if bmi < 18.5:
        return "偏瘦"
    if bmi < 24:
        return "正常"
    if bmi < 28:
        return "超重"
    return "肥胖"


def filter_records(
    records: list[SportRecord],
    keyword: str = "",
    sport_type: str = "全部",
    category: str = "全部",
    status: str = "全部",
    start_day: str = "",
    end_day: str = "",
) -> list[SportRecord]:
    filtered = records
    keyword = keyword.strip().lower()
    if keyword:
        filtered = [r for r in filtered if keyword in r.name.lower() or keyword in r.student_id.lower() or keyword in r.class_name.lower()]
    if sport_type and sport_type != "全部":
        filtered = [r for r in filtered if r.sport_type == sport_type]
    if category and category != "全部":
        filtered = [r for r in filtered if r.category == category]
    if status and status != "全部":
        filtered = [r for r in filtered if r.status == status]
    if start_day.strip():
        filtered = [r for r in filtered if r.day >= start_day.strip()]
    if end_day.strip():
        filtered = [r for r in filtered if r.day <= end_day.strip()]
    return sorted(filtered, key=lambda r: (r.day, r.name), reverse=True)


def summarize(records: list[SportRecord], target_minutes: int = 150) -> dict[str, object]:
    valid = [r for r in records if r.status == "已通过"]
    sport_count = Counter(r.sport_type for r in valid)
    total_duration = sum(r.duration for r in valid)
    total_distance = round(sum(r.distance for r in valid), 2)
    total_calories = round(sum(r.calories for r in valid), 1)
    total_steps = sum(r.steps for r in valid)
    active_days = len({r.day for r in valid})
    average_duration = round(total_duration / len(valid), 1) if valid else 0
    favorite = sport_count.most_common(1)[0][0] if sport_count else "暂无"
    target_percent = min(round(total_duration / target_minutes * 100), 100) if target_minutes else 0
    pending_count = len([r for r in records if r.status == "待审批"])
    rejected_count = len([r for r in records if r.status == "已驳回"])

    return {
        "count": len(records),
        "valid_count": len(valid),
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "duration": total_duration,
        "distance": total_distance,
        "calories": total_calories,
        "steps": total_steps,
        "favorite": favorite,
        "active_days": active_days,
        "average_duration": average_duration,
        "target_status": "已达标" if total_duration >= target_minutes else f"还差 {target_minutes - total_duration} 分钟",
        "target_percent": target_percent,
    }


def summarize_by_sport(records: list[SportRecord]) -> list[tuple[str, int, int, float]]:
    bucket: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "duration": 0, "calories": 0.0})
    for r in records:
        if r.status != "已通过":
            continue
        bucket[r.sport_type]["count"] += 1
        bucket[r.sport_type]["duration"] += r.duration
        bucket[r.sport_type]["calories"] += r.calories
    result = []
    for sport, data in bucket.items():
        result.append((sport, int(data["count"]), int(data["duration"]), round(data["calories"], 1)))
    return sorted(result, key=lambda item: item[2], reverse=True)


def daily_trend(records: list[SportRecord], days: int = 7) -> list[tuple[str, int]]:
    today = date.today()
    minutes = defaultdict(int)
    for r in records:
        if r.status == "已通过":
            minutes[r.day] += r.duration
    trend = []
    for i in range(days - 1, -1, -1):
        current = today - timedelta(days=i)
        key = current.strftime("%Y-%m-%d")
        trend.append((key[5:], minutes[key]))
    return trend


def weight_trend(logs: list[HealthLog], days: int = 10) -> list[tuple[str, float]]:
    sorted_logs = sorted(logs, key=lambda x: x.day)[-days:]
    return [(log.day[5:], log.weight) for log in sorted_logs]


def class_statistics(records: list[SportRecord]) -> list[tuple[str, str, int, int, float, int]]:
    """按学生统计：姓名、班级、次数、时长、热量、待审批。"""
    bucket: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"count": 0, "duration": 0, "calories": 0.0, "pending": 0})
    name_map: dict[tuple[str, str], str] = {}
    for r in records:
        key = (r.student_id, r.class_name)
        name_map[key] = r.name
        if r.status == "待审批":
            bucket[key]["pending"] += 1
        if r.status == "已通过":
            bucket[key]["count"] += 1
            bucket[key]["duration"] += r.duration
            bucket[key]["calories"] += r.calories
    result = []
    for key, data in bucket.items():
        result.append((name_map[key], key[1], int(data["count"]), int(data["duration"]), round(data["calories"], 1), int(data["pending"])))
    return sorted(result, key=lambda item: item[3], reverse=True)


def leaderboard(
    records: list[SportRecord], score_rule: dict[str, int] | None = None
) -> list[tuple[int, str, str, int, float, int]]:
    if score_rule is None:
        try:
            from database import SettingsDAO
            score_rule = SettingsDAO().get_score_rule()
        except Exception:
            score_rule = {
                "base_points": 1, "minutes_per_point": 10,
                "session_bonus_threshold": 30, "session_bonus_points": 5,
                "full_bonus_threshold": 150, "full_bonus_points": 20,
            }
    base = max(0, int(score_rule.get("base_points", 1)))
    minute_unit = max(1, int(score_rule.get("minutes_per_point", 10)))
    session_threshold = max(0, int(score_rule.get("session_bonus_threshold", 30)))
    session_bonus = max(0, int(score_rule.get("session_bonus_points", 5)))
    full_threshold = max(0, int(score_rule.get("full_bonus_threshold", 150)))
    full_bonus = max(0, int(score_rule.get("full_bonus_points", 20)))
    bucket: dict[str, dict[str, float | str]] = defaultdict(lambda: {"name": "", "class": "", "duration": 0, "calories": 0.0, "points": 0})
    for r in records:
        if r.status != "已通过":
            continue
        item = bucket[r.student_id]
        item["name"] = r.name
        item["class"] = r.class_name
        item["duration"] = int(item["duration"]) + r.duration
        item["calories"] = float(item["calories"]) + r.calories
        item["points"] = (
            int(item["points"]) + base + r.duration // minute_unit
            + (session_bonus if r.duration >= session_threshold else 0)
        )
    rows = []
    for item in bucket.values():
        total_duration = int(item["duration"])
        points = int(item["points"]) + (full_bonus if total_duration >= full_threshold else 0)
        rows.append((str(item["name"]), str(item["class"]), total_duration, round(float(item["calories"]), 1), points))
    rows.sort(key=lambda x: (x[2], x[4]), reverse=True)
    return [(i + 1, *row) for i, row in enumerate(rows)]


def evaluate_physical_test(total_score: float) -> str:
    if total_score >= 90:
        return "优秀"
    if total_score >= 80:
        return "良好"
    if total_score >= 60:
        return "及格"
    return "不及格"


def calculate_physical_test_score(
    gender: str, run_score: float, long_jump_cm: float,
    lung_capacity: int, sit_reach_cm: float,
) -> tuple[float, str]:
    """依据常用高校体测区间进行自动折算（跑步单项分占 40%）。

    项目没有采集 50 米、引体向上/仰卧起坐等全部国标项目，因此这里对已采集
    的四项按 40/20/20/20 加权，并在界面明确标注为“系统估算分”。
    """
    def scale(value: float, pass_line: float, excellent: float) -> float:
        if value <= 0:
            return 0.0
        return max(0.0, min(100.0, 60 + (value - pass_line) * 40 / (excellent - pass_line)))

    male = gender.strip() != "女"
    run = max(0.0, min(100.0, float(run_score)))
    jump = scale(float(long_jump_cm), 208 if male else 151, 273 if male else 207)
    lung = scale(float(lung_capacity), 3100 if male else 2000, 4800 if male else 3400)
    sit = scale(float(sit_reach_cm), 3.7 if male else 6.0, 21.3 if male else 24.0)
    total = round(run * 0.4 + jump * 0.2 + lung * 0.2 + sit * 0.2, 1)
    return total, evaluate_physical_test(total)


def test_suggestion(record: PhysicalTestRecord) -> str:
    rating = record.rating or evaluate_physical_test(record.total_score)
    if rating == "优秀":
        return "保持当前训练节奏，注意恢复和拉伸。"
    if rating == "良好":
        return "建议每周增加 1 次耐力跑或力量训练，冲刺优秀。"
    if rating == "及格":
        return "建议设置补强任务：每周 3 次跑步 + 2 次核心力量。"
    return "需生成补强打卡任务：低强度有氧循序渐进，重点提升跑步和肺活量。"


def risk_warnings(profile: HealthProfile, records: list[SportRecord], logs: list[HealthLog]) -> list[str]:
    warnings: list[str] = []
    bmi = calc_bmi(profile.height, profile.weight)
    if bmi >= 28:
        warnings.append("BMI 偏高：建议控制高油高糖饮食，优先安排低冲击有氧。")
    elif bmi < 18.5:
        warnings.append("BMI 偏低：建议提高优质蛋白和力量训练比例，避免过度有氧。")

    today = date.today()
    recent_records = [r for r in records if r.status == "已通过" and r.day >= (today - timedelta(days=7)).strftime("%Y-%m-%d")]
    recent_minutes = sum(r.duration for r in recent_records)
    active_days = len({r.day for r in recent_records})
    if active_days <= 1:
        warnings.append("久坐/缺运动风险：近 7 天有效运动天数偏少，建议今天完成 20-30 分钟轻运动。")
    if recent_minutes > 420:
        warnings.append("运动过量风险：近 7 天运动量较大，请安排恢复日并关注关节疼痛。")
    if any(r.duration >= 180 for r in recent_records):
        warnings.append("单次运动过长：存在疲劳积累风险，建议拆分训练。")

    recent_logs = sorted(logs, key=lambda x: x.day)[-3:]
    if recent_logs and sum(log.sleep_hours for log in recent_logs) / len(recent_logs) < 6:
        warnings.append("睡眠不足：最近自测平均睡眠低于 6 小时，不建议高强度训练。")
    if recent_logs and any(log.fatigue_level in {"疲劳", "非常疲劳"} for log in recent_logs):
        warnings.append("疲劳预警：近期疲劳程度较高，建议降低训练强度。")
    if recent_logs and len(recent_logs) >= 2 and abs(recent_logs[-1].weight - recent_logs[-2].weight) >= 2:
        warnings.append("体重骤变：最近体重变化超过 2kg，请检查饮食、水分和测量时间。")
    if not warnings:
        warnings.append("暂无明显风险：当前运动和健康记录整体正常。")
    return warnings


def personal_plan(profile: HealthProfile, records: list[SportRecord]) -> str:
    summary = summarize(records, profile.weekly_target)
    bmi = calc_bmi(profile.height, profile.weight)
    goal = profile.fitness_goal
    if goal == "减脂" or bmi >= 24:
        return "建议方案：每周 3 次 30-45 分钟慢跑/骑行 + 2 次力量训练；饮食控制油炸和奶茶，保证蛋白质。"
    if goal == "增肌" or profile.body_fat < 12:
        return "建议方案：每周 3-4 次力量训练，重点安排深蹲、推、拉、核心；有氧控制在 20 分钟以内，训练后补充蛋白。"
    if summary["duration"] < profile.weekly_target:
        return "建议方案：先完成达标目标，每周至少累计 150 分钟中等强度运动，可从快走、慢跑、早操开始。"
    return "建议方案：保持当前节奏，加入 1 次体测专项训练，例如 800/1000 米配速跑或立定跳远爆发力训练。"


def diet_advice(profile: HealthProfile, recent_calories: float) -> str:
    bmi = calc_bmi(profile.height, profile.weight)
    if profile.fitness_goal == "减脂" or bmi >= 24:
        return f"饮食建议：本统计周期运动约消耗 {recent_calories:.0f} kcal，可适当增加鸡胸肉/鸡蛋/豆制品，主食减量但不要完全不吃。"
    if profile.fitness_goal == "增肌":
        return f"饮食建议：本统计周期运动约消耗 {recent_calories:.0f} kcal，训练后 1-2 小时内补充碳水和蛋白，避免只吃零食。"
    return f"饮食建议：本统计周期运动约消耗 {recent_calories:.0f} kcal，三餐保持蔬菜、蛋白和主食均衡即可。"


def predict_test_score(records: list[SportRecord], tests: list[PhysicalTestRecord]) -> str:
    cutoff = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    recent_minutes = sum(
        r.duration for r in records if r.status == "已通过" and r.day >= cutoff
    )
    latest_score = sorted(tests, key=lambda x: x.year)[-1].total_score if tests else 70
    predicted = min(100, round(latest_score + recent_minutes / 300 * 3, 1))
    rating = evaluate_physical_test(predicted)
    return f"体测预判：根据当前运动量和历史体测，预计综合分约 {predicted} 分，评级约为「{rating}」。"


def weekly_report(profile: HealthProfile, records: list[SportRecord], logs: list[HealthLog], tests: list[PhysicalTestRecord], title: str = "校园运动健康周报") -> str:
    s = summarize(records, profile.weekly_target)
    sport_lines = summarize_by_sport(records)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    bmi = calc_bmi(profile.height, profile.weight)
    lines = [
        title,
        "=" * 36,
        f"生成时间：{generated_at}",
        f"学生：{profile.name}｜学号：{profile.student_id}｜班级：{profile.class_name}",
        f"BMI：{bmi}（{bmi_level(bmi)}）｜目标：{profile.fitness_goal}",
        "",
        "一、运动统计",
        f"运动次数：{s['valid_count']} 次｜待审批：{s['pending_count']} 次｜已驳回：{s['rejected_count']} 次",
        f"累计时长：{s['duration']} 分钟｜累计距离：{s['distance']} km｜累计步数：{s['steps']} 步",
        f"累计消耗：{s['calories']} kcal｜活跃天数：{s['active_days']} 天｜偏好运动：{s['favorite']}",
        f"每周 {profile.weekly_target} 分钟目标：{s['target_status']}（{s['target_percent']}%）",
        "",
        "二、运动类型分布",
    ]
    if sport_lines:
        for sport, count, duration, calories in sport_lines:
            lines.append(f"- {sport}：{count} 次，{duration} 分钟，{calories} kcal")
    else:
        lines.append("- 暂无有效运动数据")
    lines.extend([
        "",
        "三、风险预警",
        *[f"- {text}" for text in risk_warnings(profile, records, logs)],
        "",
        "四、智能建议",
        f"- {personal_plan(profile, records)}",
        f"- {diet_advice(profile, float(s['calories']))}",
        f"- {predict_test_score(records, tests)}",
    ])
    return "\n".join(lines)
