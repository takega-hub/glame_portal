import asyncio

import pytest
from fastapi import HTTPException

from app.services.gift_certificate_service import validate_gift_certificate_nominal
from app.services.onec_gift_certificate_service import OneCGiftCertificateService


class FakeOneCGiftCertificateService(OneCGiftCertificateService):
    def __init__(self, rows):
        self.rows = rows

    async def close(self):
        return None

    async def _request_json(self, method, endpoint, *, params=None, json_body=None, max_retries=2):
        if endpoint.startswith("/Catalog_Номенклатура(guid'"):
            ref = endpoint.split("guid'", 1)[1].split("'", 1)[0]
            for row in self.rows:
                if row.get("Ref_Key") == ref:
                    return row
            return {}
        return {"value": self.rows}


def _gift_row(ref, nominal, *, arbitrary=False, deleted=False, series=True):
    return {
        "Ref_Key": ref,
        "Description": f"Подарочный сертификат {nominal}",
        "Артикул": ref,
        "ТипНоменклатуры": "ПодарочныйСертификат",
        "Номинал": nominal,
        "ПроизвольныйНоминал": arbitrary,
        "ИспользоватьСерииНоменклатуры": series,
        "DeletionMark": deleted,
    }


def test_onec_finds_fixed_gift_nomenclature_before_arbitrary(monkeypatch):
    monkeypatch.setenv("ONEC_GIFT_NOMENCLATURE_SCAN_LIMIT", "500")
    service = FakeOneCGiftCertificateService(
        [
            _gift_row("fixed-5000", 5000),
            _gift_row("arbitrary", 0, arbitrary=True),
        ]
    )

    row = asyncio.run(service.find_gift_nomenclature_by_nominal(500_000))
    asyncio.run(service.close())

    assert row["Ref_Key"] == "fixed-5000"


def test_onec_finds_arbitrary_gift_nomenclature(monkeypatch):
    monkeypatch.setenv("ONEC_GIFT_NOMENCLATURE_SCAN_LIMIT", "500")
    service = FakeOneCGiftCertificateService(
        [
            _gift_row("fixed-5000", 5000),
            _gift_row("arbitrary", 0, arbitrary=True),
        ]
    )

    fixed = asyncio.run(service.find_gift_nomenclature_by_nominal(7_500_00))
    arbitrary = asyncio.run(service.find_arbitrary_gift_nomenclature())
    asyncio.run(service.close())

    assert fixed is None
    assert arbitrary["Ref_Key"] == "arbitrary"


def test_onec_uses_configured_arbitrary_ref(monkeypatch):
    monkeypatch.setenv("ONEC_GIFT_CERTIFICATE_ARBITRARY_REF_KEY", "configured")
    service = FakeOneCGiftCertificateService(
        [
            _gift_row("first", 0, arbitrary=True),
            _gift_row("configured", 0, arbitrary=True),
        ]
    )

    row = asyncio.run(service.find_arbitrary_gift_nomenclature())
    asyncio.run(service.close())

    assert row["Ref_Key"] == "configured"


def test_validate_custom_certificate_nominal_limits(monkeypatch):
    monkeypatch.setenv("GIFT_CERTIFICATE_MIN_AMOUNT", "100000")
    monkeypatch.setenv("GIFT_CERTIFICATE_MAX_AMOUNT", "10000000")
    monkeypatch.setenv("GIFT_CERTIFICATE_AMOUNT_STEP", "10000")

    assert validate_gift_certificate_nominal(7_500_00) == 7_500_00

    with pytest.raises(HTTPException):
        validate_gift_certificate_nominal(999_00)

    with pytest.raises(HTTPException):
        validate_gift_certificate_nominal(100_001_00)

    with pytest.raises(HTTPException):
        validate_gift_certificate_nominal(7_550_50)


class FakeOneCProgramBalance(OneCGiftCertificateService):
    def __init__(self):
        self.documents = []
        self.movements = []
        self.posts = 0
        self.series = {"DeletionMark": False, "Продан": False}

    async def _request_json(self, method, endpoint, *, params=None, json_body=None, max_retries=2):
        if endpoint == "/AccumulationRegister_ПодарочныеСертификаты_RecordType":
            return {"value": self.movements}
        if endpoint == "/Document_ВводНачальныхОстатков" and method == "GET":
            return {"value": self.documents}
        if endpoint == "/Document_ВводНачальныхОстатков" and method == "POST":
            doc = {**json_body, "Ref_Key": "document-ref"}
            self.documents.append(doc)
            return doc
        if endpoint == "/Catalog_СерииНоменклатуры(guid'series-ref')":
            if method == "PATCH":
                self.series.update(json_body)
            return self.series
        if endpoint.endswith("/Post"):
            self.posts += 1
            doc = self.documents[0]
            doc["Posted"] = True
            self.movements.append({
                "Active": True,
                "RecordType": "Receipt",
                "НомерСертификата_Key": doc["ПодарочныеСертификаты"][0]["НомерСертификата_Key"],
                "Сумма": doc["ПодарочныеСертификаты"][0]["Сумма"],
            })
            return {}
        raise AssertionError((method, endpoint))


def test_program_certificate_posts_1c_balance_once():
    service = FakeOneCProgramBalance()
    kwargs = {
        "series_ref_key": "series-ref",
        "gift_nomenclature_ref": "gift-ref",
        "nominal_kopeks": 500_000,
        "organization_ref_key": "org-ref",
        "certificate_number": "GLM-2026-TEST-TEST",
    }
    first = asyncio.run(service.issue_program_balance(**kwargs))
    second = asyncio.run(service.issue_program_balance(**kwargs))

    assert first["Ref_Key"] == "document-ref"
    assert second["balance"] == 5000
    assert service.posts == 1
    assert len(service.documents) == 1
    assert service.documents[0]["РазделУчета"] == "СкидкиБонусы"
    assert service.series["Продан"] is True


def test_purchased_certificate_posts_1c_balance_once():
    service = FakeOneCProgramBalance()
    kwargs = {
        "series_ref_key": "series-ref",
        "gift_nomenclature_ref": "gift-ref",
        "nominal_kopeks": 1_750_000,
        "organization_ref_key": "org-ref",
        "certificate_number": "GLM-2026-PAID-TEST",
        "source": "purchase",
    }
    first = asyncio.run(service.issue_program_balance(**kwargs))
    second = asyncio.run(service.issue_program_balance(**kwargs))

    assert first["balance"] == 17500
    assert second["balance"] == 17500
    assert service.posts == 1
    assert service.documents[0]["Комментарий"] == "GLAME purchase certificate GLM-2026-PAID-TEST"


def test_purchased_certificate_retries_unposted_document():
    service = FakeOneCProgramBalance()
    service.documents.append({
        "Ref_Key": "document-ref",
        "Posted": False,
        "Комментарий": "GLAME purchase certificate GLM-2026-PAID-TEST",
        "ПодарочныеСертификаты": [{
            "НомерСертификата_Key": "series-ref",
            "Сумма": 17500,
        }],
    })
    result = asyncio.run(service.issue_program_balance(
        series_ref_key="series-ref",
        gift_nomenclature_ref="gift-ref",
        nominal_kopeks=1_750_000,
        organization_ref_key="org-ref",
        certificate_number="GLM-2026-PAID-TEST",
        source="purchase",
    ))

    assert result["balance"] == 17500
    assert service.posts == 1
    assert len(service.documents) == 1


def test_program_certificate_rejects_different_existing_balance():
    service = FakeOneCProgramBalance()
    service.movements.append({
        "Active": True,
        "RecordType": "Receipt",
        "НомерСертификата_Key": "series-ref",
        "Сумма": 3000,
    })
    with pytest.raises(RuntimeError, match="не совпадает"):
        asyncio.run(service.issue_program_balance(
            series_ref_key="series-ref",
            gift_nomenclature_ref="gift-ref",
            nominal_kopeks=500_000,
            organization_ref_key="org-ref",
            certificate_number="GLM-2026-TEST-TEST",
        ))
    assert service.documents == []
