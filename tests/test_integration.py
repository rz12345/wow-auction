"""整合測試：模擬外部 API，使用真實 SQLite，端對端驗證資料管道。"""
import json
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.controllers.auction_controller import AuctionController
from tests.conftest import (
    FAKE_COMMODITIES, FAKE_AUCTIONS, SETTINGS, TRACKED_ITEMS,
    create_schema, insert_item, insert_history, insert_realtime,
)


# ══════════════════════════════════════════════════════════════════════════════
# 初始化
# ══════════════════════════════════════════════════════════════════════════════

class TestInit:

    def test_missing_settings_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(AuctionController, 'SETTINGS_PATH', str(tmp_path / 'nonexistent.json'))
        monkeypatch.setattr(AuctionController, 'DB_PATH', str(tmp_path / 'db.sqlite'))
        with pytest.raises(RuntimeError, match='找不到設定檔'):
            AuctionController()

    def test_malformed_settings_raises(self, tmp_env):
        tmp_path, _ = tmp_env
        (tmp_path / 'settings.json').write_text('{ bad json', encoding='utf-8')
        with patch('app.services.battle_net.BattleNet.getToken', return_value='tok'), \
             patch('app.repositories.wow_game_data.WowGameData.fetchCommoditiesData',
                   return_value=FAKE_COMMODITIES):
            with pytest.raises(RuntimeError, match='設定檔格式錯誤'):
                AuctionController()

    def test_invalid_settings_type_raises(self, tmp_env):
        tmp_path, _ = tmp_env
        bad = dict(SETTINGS, history_days='not_an_int')
        (tmp_path / 'settings.json').write_text(json.dumps(bad), encoding='utf-8')
        with patch('app.services.battle_net.BattleNet.getToken', return_value='tok'), \
             patch('app.repositories.wow_game_data.WowGameData.fetchCommoditiesData',
                   return_value=FAKE_COMMODITIES):
            with pytest.raises(RuntimeError, match='設定檔驗證失敗'):
                AuctionController()

    def test_none_token_raises(self, tmp_env):
        with patch('app.services.battle_net.BattleNet.getToken', return_value=None), \
             patch('app.repositories.wow_game_data.WowGameData.fetchCommoditiesData',
                   return_value=FAKE_COMMODITIES):
            with pytest.raises(RuntimeError, match='access token'):
                AuctionController()

    def test_none_data_raises(self, tmp_env):
        with patch('app.services.battle_net.BattleNet.getToken', return_value='tok'), \
             patch('app.repositories.wow_game_data.WowGameData.fetchCommoditiesData',
                   return_value=None):
            with pytest.raises(RuntimeError, match='拍賣場資料'):
                AuctionController()

    def test_settings_loaded(self, controller):
        ctrl, db, _ = controller
        assert ctrl.item_id_threshold == TRACKED_ITEMS['item_id_threshold']
        assert ctrl.history_days == SETTINGS['history_days']
        assert ctrl.price_drop_threshold == SETTINGS['price_drop_threshold']
        assert ctrl.access_token == 'fake_token'


# ══════════════════════════════════════════════════════════════════════════════
# fetch_commodities_data
# ══════════════════════════════════════════════════════════════════════════════

class TestFetchCommoditiesData:

    def test_snapshot_json_written(self, controller):
        ctrl, db, tmp_path = controller
        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'), \
             patch.object(ctrl, 'update_item_list'), \
             patch.object(ctrl, 'check_cheap_goods'):
            ctrl.fetch_commodities_data()

        snapshots = list((tmp_path / 'data' / 'auction').glob('commodities-*.json'))
        assert len(snapshots) == 1
        data = json.loads(snapshots[0].read_text())
        assert 'auctions' in data

    def test_realtime_stats_written_to_db(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'TestGem')

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'), \
             patch.object(ctrl, 'update_item_list'), \
             patch.object(ctrl, 'check_cheap_goods'):
            ctrl.fetch_commodities_data()

        with sqlite3.connect(db) as conn:
            rows = conn.execute('SELECT item_id, min FROM auction_statistics_realtime').fetchall()
        assert any(r[0] == 238365 for r in rows)

    def test_invalid_auctions_skipped(self, controller):
        """格式不合法的拍賣紀錄不寫入 DB。"""
        ctrl, db, _ = controller
        bad_data = {'auctions': [
            {'id': 99, 'quantity': -1, 'unit_price': 0, 'item': {'id': 238365}},  # 數量非法
        ]}
        ctrl.data = bad_data

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'), \
             patch.object(ctrl, 'update_item_list'), \
             patch.object(ctrl, 'check_cheap_goods'):
            ctrl.fetch_commodities_data()

        with sqlite3.connect(db) as conn:
            rows = conn.execute('SELECT * FROM auction_statistics_realtime').fetchall()
        assert len(rows) == 0

    def test_firebase_called_with_realtime_node(self, controller):
        ctrl, db, _ = controller
        insert_item(db, 238365, 'TestGem')

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict') as mock_fb, \
             patch.object(ctrl, 'update_item_list'), \
             patch.object(ctrl, 'check_cheap_goods'):
            ctrl.fetch_commodities_data()

        called_paths = [call.args[0] for call in mock_fb.call_args_list]
        assert '/wow/auction_realtime' in called_paths


# ══════════════════════════════════════════════════════════════════════════════
# update_statics
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateStatics:

    def _write_snapshot(self, tmp_path, ts: int, records: list) -> None:
        path = tmp_path / 'data' / 'auction' / f'commodities-{ts}.json'
        path.write_text(json.dumps({'auctions': records}), encoding='utf-8')

    def test_stats_inserted_for_recent_snapshot(self, controller):
        ctrl, db, tmp_path = controller
        ts = int((datetime.now() - timedelta(days=1)).timestamp())
        self._write_snapshot(tmp_path, ts, FAKE_AUCTIONS)
        insert_item(db, 238365, 'Gem')

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'):
            ctrl.update_statics()

        with sqlite3.connect(db) as conn:
            rows = conn.execute('SELECT item_id FROM auction_statistics').fetchall()
        assert any(r[0] == 238365 for r in rows)

    def test_old_snapshots_ignored(self, controller):
        """超出 history_days 的快照不寫入 DB。"""
        ctrl, db, tmp_path = controller
        ts = int((datetime.now() - timedelta(days=40)).timestamp())
        self._write_snapshot(tmp_path, ts, FAKE_AUCTIONS)

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'):
            ctrl.update_statics()

        with sqlite3.connect(db) as conn:
            rows = conn.execute('SELECT * FROM auction_statistics').fetchall()
        assert len(rows) == 0

    def test_corrupt_snapshot_skipped_without_exception(self, controller):
        ctrl, db, tmp_path = controller
        ts = int((datetime.now() - timedelta(days=1)).timestamp())
        (tmp_path / 'data' / 'auction' / f'commodities-{ts}.json').write_text(
            'NOT JSON', encoding='utf-8'
        )
        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'):
            ctrl.update_statics()  # 不應拋出例外

    def test_duplicate_date_not_reinserted(self, controller):
        """相同日期的統計已存在時，不重複寫入。"""
        ctrl, db, tmp_path = controller
        ts = int((datetime.now() - timedelta(days=1)).timestamp())
        date = datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
        self._write_snapshot(tmp_path, ts, FAKE_AUCTIONS)
        insert_item(db, 238365, 'Gem')

        # 先手動插入同一天的資料
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO auction_statistics VALUES (238365,50000,60000,55000,5,?)", (date,)
            )

        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict'):
            ctrl.update_statics()

        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                'SELECT * FROM auction_statistics WHERE date=?', (date,)
            ).fetchall()
        assert len(rows) == 1  # 未重複寫入

    def test_firebase_called_with_auction_node(self, controller):
        ctrl, db, tmp_path = controller
        with patch('app.services.storage_firebase.StorageFirebase.updateNodeByDict') as mock_fb:
            ctrl.update_statics()

        called_paths = [call.args[0] for call in mock_fb.call_args_list]
        assert '/wow/auction' in called_paths


# ══════════════════════════════════════════════════════════════════════════════
# check_cheap_goods
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckCheapGoods:

    def test_notification_sent_on_price_drop(self, controller):
        """歷史均價 100000，即時 80000（降 20%）→ 應觸發通知。"""
        ctrl, db, _ = controller
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        insert_item(db, 238365, 'GemA', item_class_id=8)
        insert_history(db, 238365, 100000, yesterday)
        insert_realtime(db, 238365, 80000)

        with patch.object(ctrl, 'notify_message') as mock_discord, \
             patch.object(ctrl, 'notify_telegram') as mock_tg:
            ctrl.check_cheap_goods()

        mock_discord.assert_called()
        mock_tg.assert_called()

    def test_no_notification_when_price_rises(self, controller):
        """即時價比歷史高 → 不觸發通知。"""
        ctrl, db, _ = controller
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        insert_item(db, 238365, 'GemB', item_class_id=8)
        insert_history(db, 238365, 80000, yesterday)
        insert_realtime(db, 238365, 100000)

        with patch.object(ctrl, 'notify_message') as mock_discord, \
             patch.object(ctrl, 'notify_telegram') as mock_tg:
            ctrl.check_cheap_goods()

        mock_discord.assert_not_called()
        mock_tg.assert_not_called()

    def test_no_notification_when_drop_below_threshold(self, controller):
        """降幅 5%，未達 price_drop_threshold(-10%) → 不觸發。"""
        ctrl, db, _ = controller
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        insert_item(db, 238365, 'GemC', item_class_id=8)
        insert_history(db, 238365, 100000, yesterday)
        insert_realtime(db, 238365, 95000)   # 降 5%

        with patch.object(ctrl, 'notify_message') as mock_discord, \
             patch.object(ctrl, 'notify_telegram') as mock_tg:
            ctrl.check_cheap_goods()

        mock_discord.assert_not_called()
        mock_tg.assert_not_called()

    def test_no_notification_when_below_min_gold(self, controller):
        """歷史均價低於 min_gold_threshold → 不觸發。"""
        ctrl, db, _ = controller
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        insert_item(db, 238365, 'GemD', item_class_id=8)
        insert_history(db, 238365, 5000, yesterday)  # 低於 min_gold_threshold=10000
        insert_realtime(db, 238365, 3000)

        with patch.object(ctrl, 'notify_message') as mock_discord, \
             patch.object(ctrl, 'notify_telegram') as mock_tg:
            ctrl.check_cheap_goods()

        mock_discord.assert_not_called()
        mock_tg.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# archive_old_files
# ══════════════════════════════════════════════════════════════════════════════

class TestArchiveOldFiles:

    def test_old_file_compressed_and_removed(self, controller):
        ctrl, _, tmp_path = controller
        old_ts = int((datetime.now(tz=timezone.utc) - timedelta(days=35)).timestamp())
        old_file = tmp_path / 'data' / 'auction' / f'commodities-{old_ts}.json'
        old_file.write_text('{"auctions":[]}', encoding='utf-8')

        ctrl.archive_old_files()

        assert not old_file.exists()
        archives = list((tmp_path / 'data' / 'auction' / 'archived').glob('*.7z'))
        assert len(archives) == 1

    def test_recent_file_not_archived(self, controller):
        ctrl, _, tmp_path = controller
        recent_ts = int(datetime.now(tz=timezone.utc).timestamp())
        recent_file = tmp_path / 'data' / 'auction' / f'commodities-{recent_ts}.json'
        recent_file.write_text('{"auctions":[]}', encoding='utf-8')

        ctrl.archive_old_files()

        assert recent_file.exists()
        archives = list((tmp_path / 'data' / 'auction' / 'archived').glob('*.7z'))
        assert len(archives) == 0

    def test_multiple_months_separate_archives(self, controller):
        ctrl, _, tmp_path = controller
        auction_dir = tmp_path / 'data' / 'auction'
        # 兩個不同月份的舊檔案
        for days_ago in [35, 65]:
            ts = int((datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).timestamp())
            (auction_dir / f'commodities-{ts}.json').write_text('{"auctions":[]}', encoding='utf-8')

        ctrl.archive_old_files()

        archives = list((auction_dir / 'archived').glob('*.7z'))
        assert len(archives) == 2

    def test_no_files_logs_info(self, controller, caplog):
        ctrl, _, _ = controller
        with caplog.at_level(logging.INFO, logger='app.controllers.auction_controller'):
            ctrl.archive_old_files()
        assert '沒有需要封存' in caplog.text
