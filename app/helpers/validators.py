import logging

logger = logging.getLogger(__name__)

# ── settings.json 驗證 ────────────────────────────────────────────────────────

_SETTINGS_SCHEMA = {
    'item_id_threshold':    (int,),
    'tracked_item_classes': (list,),
    'custom_tracked_items': (list,),
    'history_days':         (int,),
    'price_compare_days':   (int,),
    'price_drop_threshold': (int, float),
    'min_gold_threshold':   (int, float),
    'notify_batch_size':    (int,),
}

_SETTINGS_RANGES = {
    'item_id_threshold':    (1, None),
    'history_days':         (1, 365),
    'price_compare_days':   (1, 365),
    'price_drop_threshold': (None, 0),
    'min_gold_threshold':   (0, None),
    'notify_batch_size':    (1, 200),
}


def validate_settings(cfg: dict) -> list[str]:
    """驗證 settings.json 欄位型別與數值範圍，回傳錯誤訊息清單（空表示通過）。"""
    errors = []

    for key, types in _SETTINGS_SCHEMA.items():
        if key not in cfg:
            errors.append(f"缺少必要欄位：{key}")
            continue
        if not isinstance(cfg[key], types):
            errors.append(f"{key} 型別錯誤，應為 {types}，實際為 {type(cfg[key])}")

    for key, (lo, hi) in _SETTINGS_RANGES.items():
        if key not in cfg or not isinstance(cfg[key], (int, float)):
            continue
        val = cfg[key]
        if lo is not None and val < lo:
            errors.append(f"{key} 值 {val} 小於最小值 {lo}")
        if hi is not None and val > hi:
            errors.append(f"{key} 值 {val} 大於最大值 {hi}")

    if 'tracked_item_classes' in cfg:
        if not cfg['tracked_item_classes']:
            errors.append("tracked_item_classes 不可為空清單")
        elif not all(isinstance(c, str) for c in cfg['tracked_item_classes']):
            errors.append("tracked_item_classes 所有元素必須為字串")

    if 'custom_tracked_items' in cfg:
        if not all(isinstance(i, int) for i in cfg['custom_tracked_items']):
            errors.append("custom_tracked_items 所有元素必須為整數")

    return errors


# ── Battle.net 拍賣資料驗證 ───────────────────────────────────────────────────

_REQUIRED_AUCTION_FIELDS = {'id', 'quantity', 'unit_price', 'item'}


def validate_auction_record(record: dict) -> bool:
    """驗證單筆拍賣紀錄是否包含必要欄位與合法數值。"""
    if not isinstance(record, dict):
        return False
    if not _REQUIRED_AUCTION_FIELDS.issubset(record):
        return False
    if not isinstance(record.get('item'), dict) or 'id' not in record['item']:
        return False
    if not isinstance(record.get('quantity'), int) or record['quantity'] <= 0:
        return False
    if not isinstance(record.get('unit_price'), int) or record['unit_price'] < 0:
        return False
    return True


def filter_valid_auction_records(records: list) -> list:
    """過濾掉格式不合法的拍賣紀錄，並記錄捨棄數量。"""
    valid = [r for r in records if validate_auction_record(r)]
    dropped = len(records) - len(valid)
    if dropped:
        logger.warning("拍賣資料中有 %d 筆格式不合法，已捨棄", dropped)
    return valid
