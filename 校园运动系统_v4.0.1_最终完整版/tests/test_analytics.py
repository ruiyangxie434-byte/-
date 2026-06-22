"""
单元测试模块 —— analytics 和 models 核心逻辑
运行方式：
    pip install pytest
    pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from analytics import (
    bmi_level,
    calc_bmi,
    daily_trend,
    estimate_calories,
    evaluate_physical_test,
    filter_records,
    leaderboard,
    risk_warnings,
    summarize,
)
from models import HealthLog, HealthProfile, PhysicalTestRecord, SportRecord


# ───────────────────────────────────────────────────────────────
# Fixtures（公用测试数据）
# ───────────────────────────────────────────────────────────────
def _make_record(**kwargs) -> SportRecord:
    defaults = dict(
        student_id="20250101",
        name="张三",
        class_name="25大数据本3",
        day="2026-06-01",
        sport_type="跑步",
        category="课外体育",
        checkin_method="手动录入",
        location="操场",
        duration=30,
        distance=3.0,
        steps=4000,
        heart_rate=140,
        calories=280.0,
        status="已通过",
        remark="",
    )
    defaults.update(kwargs)
    return SportRecord(**defaults)


def _make_log(**kwargs) -> HealthLog:
    defaults = dict(
        student_id="20250101",
        name="张三",
        day="2026-06-01",
        weight=65.0,
        sleep_hours=7.5,
        meals="正常",
        heart_rate=72,
        fatigue_level="正常",
    )
    defaults.update(kwargs)
    return HealthLog(**defaults)


def _make_profile(**kwargs) -> HealthProfile:
    defaults = dict(
        student_id="20250101",
        name="张三",
        height=175.0,
        weight=67.0,
        body_fat=15.0,
        weekly_target=150,
        step_goal=8000,
        fitness_goal="增肌",
    )
    defaults.update(kwargs)
    return HealthProfile(**defaults)


# ───────────────────────────────────────────────────────────────
# 热量估算测试
# ───────────────────────────────────────────────────────────────
class TestEstimateCalories:
    def test_running_30min_65kg(self):
        """跑步 MET=8.0，30 分钟，65kg → 8.0×65×0.5 = 260"""
        result = estimate_calories("跑步", 30, 65.0)
        assert result == pytest.approx(260.0, abs=0.5)

    def test_yoga_60min_60kg(self):
        """瑜伽 MET=3.0，60 分钟，60kg → 3.0×60×1.0 = 180"""
        result = estimate_calories("瑜伽", 60, 60.0)
        assert result == pytest.approx(180.0, abs=0.5)

    def test_unknown_sport_uses_default(self):
        """未知运动类型使用默认 MET=5.0"""
        result = estimate_calories("电竞", 30, 70.0)
        assert result == pytest.approx(175.0, abs=0.5)

    def test_zero_duration(self):
        """时长为 0 时热量应为 0"""
        assert estimate_calories("跑步", 0, 70.0) == 0.0


# ───────────────────────────────────────────────────────────────
# BMI 计算测试
# ───────────────────────────────────────────────────────────────
class TestBMI:
    @pytest.mark.parametrize("h, w, expected", [
        (175, 67, 21.9),   # 正常
        (160, 90, 35.2),   # 肥胖
        (180, 50, 15.4),   # 偏瘦
        (0,   65, 0.0),    # 身高为 0 → 返回 0
    ])
    def test_calc_bmi(self, h, w, expected):
        assert calc_bmi(h, w) == pytest.approx(expected, abs=0.2)

    @pytest.mark.parametrize("bmi, level", [
        (17.0, "偏瘦"),
        (21.0, "正常"),
        (25.5, "超重"),
        (30.0, "肥胖"),
        (0.0,  "暂无"),
    ])
    def test_bmi_level(self, bmi, level):
        assert bmi_level(bmi) == level


# ───────────────────────────────────────────────────────────────
# 运动记录过滤测试
# ───────────────────────────────────────────────────────────────
class TestFilterRecords:
    def setup_method(self):
        self.records = [
            _make_record(name="张三", sport_type="跑步",  day="2026-05-28", status="已通过"),
            _make_record(name="李四", sport_type="篮球",  day="2026-06-01", status="待审批"),
            _make_record(name="张三", sport_type="力量训练", day="2026-06-02", status="已通过"),
        ]

    def test_filter_by_keyword(self):
        result = filter_records(self.records, keyword="李四")
        assert len(result) == 1
        assert result[0].name == "李四"

    def test_filter_by_sport_type(self):
        result = filter_records(self.records, sport_type="跑步")
        assert all(r.sport_type == "跑步" for r in result)

    def test_filter_by_status(self):
        result = filter_records(self.records, status="已通过")
        assert all(r.status == "已通过" for r in result)
        assert len(result) == 2

    def test_filter_by_date_range(self):
        result = filter_records(self.records, start_day="2026-06-01", end_day="2026-06-02")
        assert all("2026-06-01" <= r.day <= "2026-06-02" for r in result)

    def test_no_filter_returns_all(self):
        result = filter_records(self.records)
        assert len(result) == 3


# ───────────────────────────────────────────────────────────────
# 统计汇总测试
# ───────────────────────────────────────────────────────────────
class TestSummarize:
    def test_empty_records(self):
        s = summarize([])
        assert s["count"] == 0
        assert s["duration"] == 0

    def test_basic_summary(self):
        records = [
            _make_record(duration=30, calories=280.0, status="已通过"),
            _make_record(duration=45, calories=400.0, status="已通过"),
            _make_record(duration=20, calories=150.0, status="待审批"),
        ]
        s = summarize(records, target_minutes=150)
        assert s["valid_count"] == 2
        assert s["pending_count"] == 1
        assert s["duration"] == 75       # 30+45
        assert s["calories"] == pytest.approx(680.0, abs=0.5)

    def test_target_achieved(self):
        records = [_make_record(duration=200, status="已通过")]
        s = summarize(records, target_minutes=150)
        assert s["target_status"] == "已达标"
        assert s["target_percent"] == 100


# ───────────────────────────────────────────────────────────────
# 体测评级测试
# ───────────────────────────────────────────────────────────────
class TestPhysicalTest:
    @pytest.mark.parametrize("score, expected", [
        (95.0, "优秀"),
        (85.0, "良好"),
        (70.0, "及格"),
        (55.0, "不及格"),
        (60.0, "及格"),   # 边界：60 为及格
        (80.0, "良好"),   # 边界：80 为良好
        (90.0, "优秀"),   # 边界：90 为优秀
    ])
    def test_evaluate(self, score, expected):
        assert evaluate_physical_test(score) == expected


# ───────────────────────────────────────────────────────────────
# Model 验证测试
# ───────────────────────────────────────────────────────────────
class TestModels:
    def test_sport_record_invalid_name(self):
        with pytest.raises(ValueError, match="姓名不能为空"):
            _make_record(name="")

    def test_sport_record_negative_duration(self):
        with pytest.raises(ValueError, match="运动时长必须大于 0"):
            _make_record(duration=-1)

    def test_health_log_zero_weight(self):
        with pytest.raises(ValueError, match="晨起体重必须大于 0"):
            _make_log(weight=0)

    def test_health_log_invalid_sleep(self):
        with pytest.raises(ValueError, match="睡眠时长应在"):
            _make_log(sleep_hours=25)

    def test_health_profile_defaults(self):
        p = HealthProfile().normalize()
        assert p.height > 0
        assert p.weekly_target > 0

    def test_sport_record_from_row_compat(self):
        """测试旧版 6 列 CSV 兼容解析。"""
        row = ["张三", "2026-06-01", "跑步", "30", "3.0", "280.0"]
        r = SportRecord.from_row(row)
        assert r.name == "张三"
        assert r.duration == 30


# ───────────────────────────────────────────────────────────────
# 风险预警测试
# ───────────────────────────────────────────────────────────────
class TestRiskWarnings:
    def test_no_records_triggers_sedentary_warning(self):
        profile = _make_profile()
        warnings = risk_warnings(profile, [], [])
        # 无记录时应有久坐/缺运动预警
        assert any("久坐" in w or "缺运动" in w or "偏少" in w for w in warnings)

    def test_obesity_bmi_warning(self):
        profile = _make_profile(height=170, weight=100)  # BMI≈34.6
        warnings = risk_warnings(profile, [], [])
        assert any("BMI 偏高" in w for w in warnings)

    def test_underweight_bmi_warning(self):
        profile = _make_profile(height=175, weight=45)   # BMI≈14.7
        warnings = risk_warnings(profile, [], [])
        assert any("BMI 偏低" in w for w in warnings)


# ───────────────────────────────────────────────────────────────
# 排行榜测试
# ───────────────────────────────────────────────────────────────
class TestLeaderboard:
    def test_sorted_by_duration(self):
        records = [
            _make_record(student_id="S1", name="甲", duration=120, status="已通过"),
            _make_record(student_id="S2", name="乙", duration=60,  status="已通过"),
            _make_record(student_id="S1", name="甲", duration=30,  status="已通过"),
        ]
        lb = leaderboard(records)
        assert lb[0][1] == "甲"   # 甲总时长 150 > 乙 60

    def test_pending_not_counted(self):
        records = [
            _make_record(student_id="S1", name="甲", duration=100, status="已通过"),
            _make_record(student_id="S1", name="甲", duration=200, status="待审批"),
        ]
        lb = leaderboard(records)
        # 待审批不计入，甲只有 100 分钟
        assert lb[0][3] == 100

    def test_structured_score_rule_changes_points(self):
        records = [_make_record(student_id="S1", name="甲", duration=30, status="已通过")]
        rule = {
            "base_points": 2, "minutes_per_point": 5,
            "session_bonus_threshold": 20, "session_bonus_points": 7,
            "full_bonus_threshold": 30, "full_bonus_points": 11,
        }
        lb = leaderboard(records, rule)
        assert lb[0][5] == 26  # 2 + 30/5 + 7 + 11


def test_auto_physical_score():
    from analytics import calculate_physical_test_score
    score, rating = calculate_physical_test_score("男", 90, 273, 4800, 21.3)
    assert score == 96.0
    assert rating == "优秀"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
