"""單元測試：純函式與個別方法的孤立測試。"""
import sqlite3
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import requests

from app.helpers.validators import (
    validate_settings,
    validate_auction_record,
    filter_valid_auction_records,
)
from tests.conftest import SETTINGS, insert_item


# ══════════════════════════════════════════════════════════════════════════════
# validators.py
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateSettings:

    def test_valid_settings_passes(self):
        assert validate_settings(SETTINGS) == []

    def test_missing_key_reported(self):
        cfg = dict(SETTINGS)
        del cfg['history_days']
        errors = validate_settings(cfg)
        assert any('history_days' in e for e in errors)

    def test_wrong_type_int_reported(self):
        errors = validate_settings(dict(SETTINGS, history_days='oops'))
        assert any('history_days' in e for e in errors)

    def test_wrong_type_list_reported(self):
        errors = validate_settings(dict(SETTINGS, tracked_item_classes='not_a_list'))
        assert any('tracked_item_classes' in e for e in errors)

    def test_out_of_range_history_days(self):
        errors = validate_settings(dict(SETTINGS, history_days=0))
        assert any('history_days' in e for e in errors)

    def test_price_drop_threshold_must_be_negative(self):
        errors = validate_settings(dict(SETTINGS, price_drop_threshold=5))
        assert any('price_drop_threshold' in e for e in errors)

    def test_empty_tracked_classes_reported(self):
        errors = validate_settings(dict(SETTINGS, tracked_item_classes=[]))
        assert any('tracked_item_classes' in e for e in errors)

    def test_non_string_class_reported(self):
        errors = validate_settings(dict(SETTINGS, tracked_item_classes=[1, 2]))
        assert any('tracked_item_classes' in e for e in errors)

    def test_non_int_custom_items_reported(self):
        errors = validate_settings(dict(SETTINGS, custom_tracked_items=['abc']))
        assert any('custom_tracked_items' in e for e in errors)


class TestValidateAuctionRecord:

    def _valid(self, **kwargs):
        base = {'id': 1, 'quantity': 5, 'unit_price': 50000,
                'time_left': 'VERY_LONG', 'item': {'id': 238365}}
        return {**base, **kwargs}

    def test_valid_record_passes(self):
        assert validate_auction_record(self._valid()) is True

    def test_missing_quantity_fails(self):
        r = self._valid()
        del r['quantity']
        assert validate_auction_record(r) is False

    def test_missing_unit_price_fails(self):
        r = self._valid()
        del r['unit_price']
        assert validate_auction_record(r) is False

    def test_missing_item_id_fails(self):
        assert validate_auction_record(self._valid(item={})) is False

    def test_zero_quantity_fails(self):
        assert validate_auction_record(self._valid(quantity=0)) is False

    def test_negative_quantity_fails(self):
        assert validate_auction_record(self._valid(quantity=-1)) is False

    def test_negative_price_fails(self):
        assert validate_auction_record(self._valid(unit_price=-1)) is False

    def test_zero_price_passes(self):
        assert validate_auction_record(self._valid(unit_price=0)) is True

    def test_non_dict_fails(self):
        assert validate_auction_record("not a dict") is False


class TestFilterValidAuctionRecords:

    def test_all_valid_returns_all(self):
        records = [
            {'id': 1, 'quantity': 5, 'unit_price': 100, 'item': {'id': 1}},
            {'id': 2, 'quantity': 3, 'unit_price': 200, 'item': {'id': 2}},
        ]
        assert len(filter_valid_auction_records(records)) == 2

    def test_invalid_records_removed(self):
        records = [
            {'id': 1, 'quantity': 5, 'unit_price': 100, 'item': {'id': 1}},
            {'id': 2, 'quantity': 0, 'unit_price': 200, 'item': {'id': 2}},  # invalid
        ]
        result = filter_valid_auction_records(records)
        assert len(result) == 1
        assert result[0]['id'] == 1

    def test_all_invalid_returns_empty(self):
        assert filter_valid_auction_records([{'bad': 'data'}]) == []

    def test_empty_input_returns_empty(self):
        assert filter_valid_auction_records([]) == []

    def test_dropped_count_logged(self, caplog):
        import logging
        records = [
            {'id': 1, 'quantity': 5, 'unit_price': 100, 'item': {'id': 1}},
            {'id': 2, 'quantity': -1, 'unit_price': 100, 'item': {'id': 2}},
        ]
        with caplog.at_level(logging.WARNING, logger='app.helpers.validators'):
            filter_valid_auction_records(records)
        assert '1 筆' in caplog.text


# ══════════════════════════════════════════════════════════════════════════════
# statics_auction_records
# ══════════════════════════════════════════════════════════════════════════════

class TestStaticsAuctionRecords:

    def _make_df(self, records: list) -> pd.DataFrame:
        return pd.json_normalize(records)[['id', 'quantity', 'unit_price', 'time_left', 'item.id']]

    def test_aggregates_min_max_median_qty(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'Herb')

        records = [
            {'id': 1, 'quantity': 5, 'unit_price': 30000, 'time_left': 'LONG', 'item': {'id': 238365}},
            {'id': 2, 'quantity': 3, 'unit_price': 80000, 'time_left': 'LONG', 'item': {'id': 238365}},
            {'id': 3, 'quantity': 2, 'unit_price': 50000, 'time_left': 'LONG', 'item': {'id': 238365}},
        ]
        df = self._make_df(records)
        result = ctrl.statics_auction_records(df, '2026-01-01')

        assert len(result) == 1
        row = result.iloc[0]
        assert row['item_id'] == 238365
        assert row['min'] == 30000
        assert row['max'] == 80000
        assert row['qty'] == 10   # 5 + 3 + 2
        assert row['date'] == '2026-01-01'

    def test_untracked_items_excluded(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'TrackedGem')
        # 999 未在 items table → 不追蹤

        records = [
            {'id': 1, 'quantity': 1, 'unit_price': 10000, 'time_left': 'LONG', 'item': {'id': 238365}},
            {'id': 2, 'quantity': 1, 'unit_price': 20000, 'time_left': 'LONG', 'item': {'id': 999}},
        ]
        df = self._make_df(records)
        result = ctrl.statics_auction_records(df, '2026-01-01')

        assert all(result['item_id'] == 238365)

    def test_multiple_items_aggregated_separately(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'GemA')
        insert_item(db, 238366, 'GemB')

        records = [
            {'id': 1, 'quantity': 2, 'unit_price': 10000, 'time_left': 'LONG', 'item': {'id': 238365}},
            {'id': 2, 'quantity': 4, 'unit_price': 20000, 'time_left': 'LONG', 'item': {'id': 238366}},
        ]
        df = self._make_df(records)
        result = ctrl.statics_auction_records(df, '2026-01-01')

        assert len(result) == 2
        assert set(result['item_id']) == {238365, 238366}

    def test_date_attached_to_result(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'Gem')
        records = [{'id': 1, 'quantity': 1, 'unit_price': 5000, 'time_left': 'LONG', 'item': {'id': 238365}}]
        result = ctrl.statics_auction_records(self._make_df(records), '2025-12-31')
        assert result.iloc[0]['date'] == '2025-12-31'


# ══════════════════════════════════════════════════════════════════════════════
# query_item_quality
# ══════════════════════════════════════════════════════════════════════════════

class TestQueryItemQuality:

    def _insert_triple(self, db: str) -> None:
        """插入三個同名物品（模擬一星/二星/三星變體）。"""
        with sqlite3.connect(db) as conn:
            for item_id in (238365, 238366, 238367):
                conn.execute(
                    "INSERT INTO items VALUES (?,?,1,1,'UNCOMMON','罕見','寶石',8,'寶石',0)",
                    (item_id, 'StarGem'),
                )

    def test_first_id_is_one_star(self, controller):
        ctrl, db, _ = controller
        self._insert_triple(db)
        result = ctrl.query_item_quality(238365, 'StarGem')
        assert result == 'StarGem ⭐'

    def test_second_id_is_two_stars(self, controller):
        ctrl, db, _ = controller
        self._insert_triple(db)
        result = ctrl.query_item_quality(238366, 'StarGem')
        assert result == 'StarGem ⭐⭐'

    def test_third_id_is_three_stars(self, controller):
        ctrl, db, _ = controller
        self._insert_triple(db)
        result = ctrl.query_item_quality(238367, 'StarGem')
        assert result == 'StarGem ⭐⭐⭐'

    def test_single_variant_item_no_stars(self, controller):
        """只有一個 ID 的物品（不滿 3 個變體）→ 不加星。"""
        ctrl, db, _ = controller
        insert_item(db, 238365, 'UniqueGem')
        result = ctrl.query_item_quality(238365, 'UniqueGem')
        assert result == 'UniqueGem'

    def test_unknown_item_returns_plain_name(self, controller):
        ctrl, db, _ = controller
        result = ctrl.query_item_quality(999999, 'Unknown')
        assert result == 'Unknown'


# ══════════════════════════════════════════════════════════════════════════════
# notify_message（Discord，2000 字元上限）
# ══════════════════════════════════════════════════════════════════════════════

class TestNotifyMessage:

    def test_short_message_single_request(self, controller):
        ctrl, _, _ = controller
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=204)
            ctrl.notify_message('短訊息')
        mock_post.assert_called_once()

    def test_long_message_split_into_multiple_requests(self, controller):
        ctrl, _, _ = controller
        line = 'A' * 100 + '\n'
        msg = line * 25   # 25 * 101 = 2525 bytes > 2000
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=204)
            ctrl.notify_message(msg)
        assert mock_post.call_count >= 2

    def test_each_chunk_within_2000_chars(self, controller):
        ctrl, _, _ = controller
        line = 'B' * 100 + '\n'
        msg = line * 30   # > 2000
        chunks_sent = []
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=204)
            mock_post.side_effect = lambda url, **kw: (
                chunks_sent.append(kw['json']['content']) or MagicMock(status_code=204)
            )
            ctrl.notify_message(msg)
        assert all(len(c) <= 2000 for c in chunks_sent)

    def test_network_error_no_exception_raised(self, controller):
        ctrl, _, _ = controller
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError('timeout')):
            ctrl.notify_message('測試訊息')  # 不應拋出例外


# ══════════════════════════════════════════════════════════════════════════════
# notify_telegram（Telegram，4096 字元上限）
# ══════════════════════════════════════════════════════════════════════════════

class TestNotifyTelegram:

    def test_short_message_single_request(self, controller):
        ctrl, _, _ = controller
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            ctrl.notify_telegram('短訊息')
        mock_post.assert_called_once()

    def test_long_message_split_into_multiple_requests(self, controller):
        ctrl, _, _ = controller
        line = 'C' * 200 + '\n'
        msg = line * 25   # 25 * 201 = 5025 > 4096
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            ctrl.notify_telegram(msg)
        assert mock_post.call_count >= 2

    def test_each_chunk_within_4096_chars(self, controller):
        ctrl, _, _ = controller
        line = 'D' * 200 + '\n'
        msg = line * 30   # > 4096
        chunks_sent = []
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            mock_post.side_effect = lambda url, **kw: (
                chunks_sent.append(kw['json']['text']) or MagicMock(status_code=200)
            )
            ctrl.notify_telegram(msg)
        assert all(len(c) <= 4096 for c in chunks_sent)

    def test_network_error_no_exception_raised(self, controller):
        ctrl, _, _ = controller
        with patch('requests.post', side_effect=requests.exceptions.ConnectionError('timeout')):
            ctrl.notify_telegram('測試訊息')  # 不應拋出例外
