from datetime import date, datetime, timezone


def test_post_purchase_touchpoints_map_legacy_meganom_by_cutoff_date():
    from app.services.crm_touchpoint_service import _crm_display_store_name

    assert _crm_display_store_name("Меганом", date(2026, 5, 31)) == "Меганом"
    assert _crm_display_store_name("Меганом", date(2026, 6, 1)) == "Мрия"
    assert _crm_display_store_name("MEGANOM", datetime(2026, 8, 1, tzinfo=timezone.utc)) == "Мрия"
    assert _crm_display_store_name("ТРК Центрум", date(2026, 8, 1)) == "ТРК Центрум"


def test_new_arrival_maps_legacy_meganom_by_cutoff_date():
    from app.services.crm_new_arrival_service import _crm_store_key, _display_store_name

    assert _display_store_name("Меганом", date(2026, 5, 31)) == "Меганом"
    assert _crm_store_key("Меганом", event_date=date(2026, 5, 31)) == "CENTRUM"
    assert _display_store_name("Меганом", date(2026, 6, 1)) == "Мрия"
    assert _crm_store_key("Меганом", event_date=date(2026, 6, 1)) == "YALTA"
