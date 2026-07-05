import unittest
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import uuid4


@dataclass
class PurchaseLine:
    purchase_date: datetime
    document_id_1c: str
    product_name: str
    total_amount: int
    product_article: str = "A100"
    category: str = "Украшения"
    product_id_1c: str | None = None
    product_id: str | None = None
    quantity: int = 1


@dataclass
class Customer:
    id: object
    full_name: str
    phone: str
    email: str | None
    birth_date: date
    loyalty_points: int = 0
    customer_segment: str | None = None


class BirthdayCrmServiceTests(unittest.TestCase):
    def test_real_receipts_exclude_accessories_and_merge_customer_checks_within_one_hour(self):
        from app.services.birthday_crm_service import calculate_real_purchase_profile

        lines = [
            PurchaseLine(datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc), "r-1", "Кольцо GLAME", 20_000_00),
            PurchaseLine(datetime(2026, 5, 1, 12, 5, tzinfo=timezone.utc), "r-1", "Подарочная упаковка", 500_00, product_article="400123"),
            PurchaseLine(datetime(2026, 5, 1, 12, 45, tzinfo=timezone.utc), "r-2", "Серьги GLAME", 15_000_00),
            PurchaseLine(datetime(2026, 5, 1, 14, 10, tzinfo=timezone.utc), "r-3", "Браслет GLAME", 5_000_00),
        ]

        profile = calculate_real_purchase_profile(lines)

        self.assertEqual(profile["real_receipts_count"], 2)
        self.assertEqual(profile["real_total_spent"], 40_000_00)
        self.assertEqual(profile["average_receipt"], 20_000_00)
        self.assertEqual([r["total_amount"] for r in profile["receipt_bundles"]], [35_000_00, 5_000_00])
        self.assertEqual(profile["excluded_accessory_amount"], 500_00)

    def test_segment_bonus_and_draft_are_based_on_real_sum_and_receipt_quality_without_auto_send(self):
        from app.services.birthday_crm_service import build_birthday_crm_card

        customer = Customer(
            id=uuid4(),
            full_name="Анна Иванова",
            phone="79780000000",
            email=None,
            birth_date=date(1990, 6, 4),
            loyalty_points=1200,
        )
        purchases = [
            PurchaseLine(datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc), "vip-1", "Колье премиум", 80_000_00),
            PurchaseLine(datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc), "vip-2", "Серьги премиум", 45_000_00),
            PurchaseLine(datetime(2026, 5, 1, 10, 20, tzinfo=timezone.utc), "vip-3", "Футляр", 700_00, product_article="400777"),
        ]

        card = build_birthday_crm_card(customer, purchases, today=date(2026, 6, 1))

        self.assertEqual(card["days_until_birthday"], 3)
        self.assertEqual(card["crm_segment"], "VIP")
        self.assertEqual(card["real_total_spent"], 125_000_00)
        self.assertIn("персональный подарок", card["recommended_bonus"]["title"].lower())
        self.assertIn("Анна", card["draft_message"])
        self.assertFalse(card["auto_send"])
        self.assertEqual(card["status"], "draft")

    def test_upcoming_birthday_window_handles_year_boundary(self):
        from app.services.birthday_crm_service import is_birthday_within_window, next_birthday_date

        self.assertTrue(is_birthday_within_window(date(1988, 1, 2), today=date(2026, 12, 31), days_ahead=3))
        self.assertEqual(next_birthday_date(date(1988, 1, 2), date(2026, 12, 31)), date(2027, 1, 2))
        self.assertFalse(is_birthday_within_window(date(1988, 1, 5), today=date(2026, 12, 31), days_ahead=3))


if __name__ == "__main__":
    unittest.main()
