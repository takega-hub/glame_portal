import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SellerPersonalKpiShiftCalendarTests(unittest.TestCase):
    def test_personal_page_shows_daily_corrected_plan_values_and_agent_recommendation(self):
        source = (ROOT / "frontend/src/components/profile/SellerPersonalKpiPage.tsx").read_text(encoding="utf-8")

        self.assertIn("dailyPlan", source)
        self.assertIn("План на сегодня", source)
        self.assertIn("Нужно сегодня", source)
        self.assertIn("Плановый темп к сегодняшнему дню", source)
        self.assertIn("До месячного плана осталось", source)
        self.assertIn("Совет AI-тренера на сегодня", source)
        self.assertIn("requiredDailyRevenue", source)
        self.assertIn("remainingRevenue", source)
        self.assertIn("expectedRevenueToDate", source)

    def test_shift_section_is_rendered_as_calendar_not_plain_list(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "frontend/src/components/profile/SellerPersonalKpiPage.tsx").read_text(encoding="utf-8")

        self.assertIn("const shiftCalendarDays = useMemo", source)
        self.assertIn("grid grid-cols-7", source)
        self.assertIn("Пн", source)
        self.assertIn("События смен", source)
        self.assertIn("shiftCalendarDays.map", source)
        self.assertNotIn("shifts.length ? shifts.map((shift)", source)


if __name__ == "__main__":
    unittest.main()
