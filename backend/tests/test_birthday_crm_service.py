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

    def test_recommended_bonus_uses_new_boundary_tiers_and_separates_service_actions(self):
        from app.services.birthday_crm_service import recommend_birthday_bonus

        cases = [
            (19_999_00, "bonus_points", 500, None, []),
            (20_000_00, "bonus_points", 1000, None, []),
            (49_999_00, "bonus_points", 1000, None, []),
            (50_000_00, "bonus_points", 2000, None, []),
            (99_999_00, "bonus_points", 2000, None, []),
            (100_000_00, "gift_certificate", None, 5_000_00, ["personal_call"]),
            (299_999_00, "gift_certificate", None, 5_000_00, ["personal_call"]),
            (300_000_00, "gift_certificate", None, 5_000_00, ["personal_call", "flowers"]),
        ]

        for total_spent, expected_type, expected_points, expected_certificate, expected_actions in cases:
            with self.subTest(total_spent=total_spent):
                bonus = recommend_birthday_bonus("ignored", {"real_total_spent": total_spent})

                self.assertEqual(bonus["type"], expected_type)
                self.assertEqual(bonus.get("bonus_points"), expected_points)
                self.assertEqual(bonus.get("certificate_kopecks"), expected_certificate)
                self.assertEqual(bonus.get("service_actions"), expected_actions)
                if expected_type == "bonus_points":
                    self.assertFalse(bonus["requires_approval"])
                else:
                    self.assertTrue(bonus["requires_approval"])

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
        self.assertEqual(card["recommended_bonus"]["type"], "gift_certificate")
        self.assertIsNone(card["recommended_bonus"].get("bonus_points"))
        self.assertEqual(card["recommended_bonus"]["certificate_kopecks"], 5_000_00)
        self.assertEqual(card["recommended_bonus"]["service_actions"], ["personal_call"])
        self.assertIn("Анна", card["draft_message"])
        self.assertFalse(card["auto_send"])
        self.assertEqual(card["status"], "draft")

    def test_birthday_crm_card_texts_do_not_include_old_bonus_rules_or_selection_as_gift(self):
        from app.services.birthday_crm_service import build_birthday_crm_card

        forbidden_fragments = ["3 000 бонус", "5 000 бонус", "7 000 бонус", "7–10%", "7-10%", "5%", "подборк"]
        for total_spent in [19_999_00, 20_000_00, 49_999_00, 50_000_00, 99_999_00, 100_000_00, 299_999_00, 300_000_00]:
            customer = Customer(
                id=uuid4(),
                full_name="Анна Иванова",
                phone="79780000000",
                email=None,
                birth_date=date(1990, 6, 4),
            )
            card = build_birthday_crm_card(
                customer,
                [PurchaseLine(datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc), "r-1", "Колье", total_spent)],
                today=date(2026, 6, 1),
            )
            generated_text = " ".join(
                str(value)
                for value in [
                    card["recommended_bonus"].get("title"),
                    card["recommended_bonus"].get("description"),
                    card["draft_message"],
                ]
            ).lower()

            for fragment in forbidden_fragments:
                self.assertNotIn(fragment.lower(), generated_text)

    def test_upcoming_birthday_window_handles_year_boundary(self):
        from app.services.birthday_crm_service import is_birthday_within_window, next_birthday_date

        self.assertTrue(is_birthday_within_window(date(1988, 1, 2), today=date(2026, 12, 31), days_ahead=3))
        self.assertEqual(next_birthday_date(date(1988, 1, 2), date(2026, 12, 31)), date(2027, 1, 2))
        self.assertFalse(is_birthday_within_window(date(1988, 1, 5), today=date(2026, 12, 31), days_ahead=3))

    def test_birthday_tier_covers_approved_boundary_values(self):
        from app.services.birthday_crm_service import birthday_tier

        cases = [
            (19_999_00, "bonus_500", 500, None, False),
            (20_000_00, "bonus_1000", 1000, None, False),
            (49_999_00, "bonus_1000", 1000, None, False),
            (50_000_00, "bonus_2000", 2000, None, False),
            (99_999_00, "bonus_2000", 2000, None, False),
            (100_000_00, "vip_100_300", None, 5_000_00, False),
            (299_999_00, "vip_100_300", None, 5_000_00, False),
            (300_000_00, "vip_300_plus", None, 5_000_00, True),
        ]

        for total_spent, expected_code, expected_points, expected_certificate, expected_flowers in cases:
            with self.subTest(total_spent=total_spent):
                tier = birthday_tier({"real_total_spent": total_spent})

                self.assertEqual(tier["code"], expected_code)
                self.assertEqual(tier.get("bonus_points"), expected_points)
                self.assertEqual(tier.get("certificate_kopecks"), expected_certificate)
                self.assertEqual(bool(tier.get("flowers")), expected_flowers)
                if expected_certificate:
                    self.assertEqual(tier["gift_certificate"], {"amount_kopecks": expected_certificate})
                    self.assertEqual(
                        tier["service_actions"],
                        ["personal_call", "flowers"] if expected_flowers else ["personal_call"],
                    )
                    self.assertEqual(tier["certificate_validity_days"], 30)
                    self.assertNotIn("certificate_validity_months", tier)
                else:
                    self.assertNotIn("gift_certificate", tier)
                    self.assertNotIn("service_actions", tier)

    def test_vip_birthday_text_mentions_30_days_not_six_months(self):
        from app.services.birthday_crm_service import _birthday_message, birthday_tier

        customer = Customer(
            id=uuid4(),
            full_name="Анна Иванова",
            phone="79780000000",
            email=None,
            birth_date=date(1990, 6, 4),
        )
        text = _birthday_message(
            customer,
            birthday_tier({"real_total_spent": 125_000_00}),
            date(2026, 6, 4),
            date(2026, 6, 1),
        )

        self.assertIn("30 дней", text)
        self.assertNotIn("6 месяцев", text)

    def test_birthday_certificate_sms_window_is_moscow_10_to_18(self):
        from app.services.birthday_crm_service import _birthday_certificate_sms_window

        self.assertFalse(_birthday_certificate_sms_window(datetime(2026, 8, 24, 6, 59, tzinfo=timezone.utc))["allowed"])
        self.assertTrue(_birthday_certificate_sms_window(datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc))["allowed"])
        self.assertTrue(_birthday_certificate_sms_window(datetime(2026, 8, 24, 14, 59, tzinfo=timezone.utc))["allowed"])
        self.assertFalse(_birthday_certificate_sms_window(datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc))["allowed"])

    def test_birthday_certificate_sms_uses_final_glame_template(self):
        from app.services.birthday_crm_service import _birthday_certificate_sms_text

        customer = Customer(
            id=uuid4(),
            full_name="Татьяна Иванова",
            phone="79780000000",
            email=None,
            birth_date=date(1990, 8, 30),
        )
        cert = type("Cert", (), {"nominal_amount": 5_000_00, "number": "GC-12345"})()

        text = _birthday_certificate_sms_text(customer, cert, "111111", "30.09.2026")

        self.assertIn("Татьяна, здравствуйте!", text)
        self.assertIn("электронным сертификатом на 5 000 ₽", text)
        self.assertIn("Ваш сертификат: № GC-12345", text)
        self.assertIn("Действует до 30.09.2026.", text)
        self.assertIn("команда GLAME", text)

if __name__ == "__main__":
    unittest.main()
