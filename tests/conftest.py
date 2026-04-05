"""共用 fixtures：臨時環境、DB schema、假資料。"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.controllers.auction_controller import AuctionController


# ── 假資料 ────────────────────────────────────────────────────────────────────

SETTINGS = {
    'item_id_threshold':    238365,
    'tracked_item_classes': ['交易技能', '物品附魔', '寶石', '消耗品'],
    'custom_tracked_items': [123918],
    'history_days':         28,
    'price_compare_days':   7,
    'price_drop_threshold': -10,
    'min_gold_threshold':   10000,
    'notify_batch_size':    20,
}

FAKE_AUCTIONS = [
    {'id': 1, 'quantity': 5, 'unit_price': 50000, 'time_left': 'VERY_LONG', 'item': {'id': 238365}},
    {'id': 2, 'quantity': 3, 'unit_price': 80000, 'time_left': 'VERY_LONG', 'item': {'id': 238366}},
    {'id': 3, 'quantity': 1, 'unit_price': 15000, 'time_left': 'LONG',      'item': {'id': 123918}},
]

FAKE_COMMODITIES = {'auctions': FAKE_AUCTIONS}


# ── DB helpers ────────────────────────────────────────────────────────────────

def create_schema(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER, name TEXT, level INTEGER, required_level INTEGER,
                quality_type TEXT, quality_name TEXT,
                item_class_name TEXT, item_class_id INTEGER,
                item_subclass_name TEXT, item_subclass_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS auction_statistics (
                item_id INTEGER, min REAL, max REAL, median REAL, qty INTEGER, date TEXT
            );
            CREATE TABLE IF NOT EXISTS auction_statistics_realtime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER, min REAL, max REAL, median REAL, qty INTEGER, date TEXT
            );
        """)


def insert_item(db_path: str, item_id: int, name: str,
                item_class_name: str = '寶石', item_class_id: int = 8,
                item_subclass_id: int = 0) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO items VALUES (?,?,1,1,'UNCOMMON','罕見',?,?,?,?)",
            (item_id, name, item_class_name, item_class_id, '寶石', item_subclass_id),
        )


def insert_history(db_path: str, item_id: int, min_price: float, date: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO auction_statistics VALUES (?,?,?,?,10,?)",
            (item_id, min_price, min_price * 1.2, min_price * 1.1, date),
        )


def insert_realtime(db_path: str, item_id: int, min_price: float) -> None:
    today = datetime.now().strftime('%Y-%m-%d')
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO auction_statistics_realtime VALUES (NULL,?,?,?,?,5,?)",
            (item_id, min_price, min_price * 1.1, min_price * 1.05, today),
        )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """臨時目錄 + 設定檔 + DB + auction 目錄，並 patch 路徑常數。"""
    settings_file = tmp_path / 'settings.json'
    settings_file.write_text(json.dumps(SETTINGS), encoding='utf-8')

    db_path = str(tmp_path / 'test.sqlite')
    create_schema(db_path)

    (tmp_path / 'data' / 'auction' / 'archived').mkdir(parents=True)

    monkeypatch.setattr(AuctionController, 'SETTINGS_PATH', str(settings_file))
    monkeypatch.setattr(AuctionController, 'DB_PATH', db_path)
    monkeypatch.chdir(tmp_path)

    return tmp_path, db_path


@pytest.fixture
def controller(tmp_env):
    """建立 AuctionController，外部 API 呼叫全部 mock。"""
    tmp_path, db_path = tmp_env
    with patch('app.services.battle_net.BattleNet.getToken', return_value='fake_token'), \
         patch('app.repositories.wow_game_data.WowGameData.fetchCommoditiesData',
               return_value=FAKE_COMMODITIES):
        ctrl = AuctionController()
    return ctrl, db_path, tmp_path
