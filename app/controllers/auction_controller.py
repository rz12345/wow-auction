from app.services.battle_net import BattleNet
from app.services.storage_firebase import StorageFirebase
from app.repositories.wow_game_data import WowGameData
from app.helpers.validators import validate_settings, filter_valid_auction_records
import re
import sqlite3
import pandas as pd
import os
import json
import logging
from datetime import datetime, timedelta, timezone
import requests
from pathlib import Path
import py7zr

logger = logging.getLogger(__name__)

class AuctionController:
    DB_PATH = 'data/db.sqlite'
    DISCORD_CRED_PATH = 'app/configs/discord-webhook.json'
    TELEGRAM_CRED_PATH = 'app/configs/telegram-bot.json'
    SETTINGS_PATH = 'app/configs/settings.json'

    def __init__(self):
        try:
            with open(self.SETTINGS_PATH, 'r') as f:
                cfg = json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"找不到設定檔：{self.SETTINGS_PATH}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"設定檔格式錯誤：{e}")

        errors = validate_settings(cfg)
        if errors:
            raise RuntimeError(f"設定檔驗證失敗：{errors}")

        self.item_id_threshold    = cfg['item_id_threshold']
        self.tracked_item_classes = cfg['tracked_item_classes']
        self.custom_tracked_items = cfg['custom_tracked_items']
        self.history_days         = cfg['history_days']
        self.price_compare_days   = cfg['price_compare_days']
        self.price_drop_threshold = cfg['price_drop_threshold']
        self.min_gold_threshold   = cfg['min_gold_threshold']
        self.notify_batch_size    = cfg['notify_batch_size']

        self.access_token = BattleNet.getToken()
        if not self.access_token:
            raise RuntimeError("無法取得 Battle.net access token，請確認憑證設定")

        self.timestamp = int(datetime.now().timestamp())
        self.data = WowGameData.fetchCommoditiesData(self.access_token)
        if self.data is None:
            raise RuntimeError("無法取得拍賣場資料，請確認 Battle.net API 狀態")

    def get_item_list(self):
        """
        获取需要追踪的物品列表
        包括达到ID阈值的特定类别物品和自定义追踪物品
        """
        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(f'''
                SELECT * FROM items
                WHERE id >= {self.item_id_threshold}
                AND item_class_name IN ({','.join(['?']*len(self.tracked_item_classes))})
            ''', self.tracked_item_classes)
            item_list = [row[0] for row in cur.fetchall()]

        focus_items = item_list + self.custom_tracked_items
        return focus_items

    def statics_auction_records(self, df, date):
        """
        统计拍卖记录
        计算每个物品的最低价、最高价、中位数价格和总数量
        """
        items_list = self.get_item_list()
        df_stat = df[df['item.id'].isin(items_list)].groupby(['item.id']).agg({
            'unit_price': ['min', 'max', 'median'], 
            'quantity': 'sum'
        })
        df_stat = df_stat.droplevel(0, axis=1)
        df_stat.reset_index(inplace=True)
        df_stat.columns = ['item_id', 'min', 'max', 'median', 'qty']
        df_stat['date'] = date
        return df_stat

    def update_statics(self):
        """
        更新统计数据
        处理过去28天的拍卖数据，计算统计信息并存储到数据库
        """
        directory = 'data/auction/'
        files = os.listdir(directory)
        date_file_mapping = {}
        for file in files:
            if file.endswith('.json'):
                timestamp_str = file.split('-')[1].split('.')[0]
                timestamp = int(timestamp_str)
                date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
                date_file_mapping.setdefault(date, []).append(file)

        sorted_dates = sorted(date_file_mapping.keys())
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=self.history_days)).strftime('%Y-%m-%d')

        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor()
            for date in sorted_dates:
                if date < start_date or date > end_date:
                    continue
                    
                cur.execute('SELECT * FROM auction_statistics WHERE date = ?', [date])
                item_list = [row for row in cur.fetchall()]
                if len(item_list) > 0:
                    continue

                df = pd.DataFrame()
                files_for_date = date_file_mapping[date]

                for file in files_for_date:
                    try:
                        with open(directory + file) as f:
                            json_data = json.load(f)
                    except (OSError, json.JSONDecodeError) as e:
                        logger.error("讀取快照失敗，跳過 %s：%s", file, e)
                        continue

                    if not json_data or 'auctions' not in json_data:
                        logger.warning("快照格式不符，跳過 %s", file)
                        continue

                    valid_records = filter_valid_auction_records(json_data['auctions'])
                    if not valid_records:
                        logger.warning("快照無有效拍賣紀錄，跳過 %s", file)
                        continue

                    df_new = pd.json_normalize(valid_records)[['id', 'quantity', 'unit_price', 'time_left', 'item.id']]
                    df = pd.concat([df_new, df], axis=0)
                    df.drop_duplicates(subset='id', keep='last', inplace=True)

                if df.empty:
                    logger.warning("日期 %s 無有效資料，跳過統計", date)
                    continue

                df_stat = self.statics_auction_records(df, date)
                df_stat.to_sql('auction_statistics', conn, if_exists='append', index=False)
                logger.info("統計完成 %s：%s", date, files_for_date)
        
        statics_records = {}
        items_list = self.get_item_list()
        with sqlite3.connect(self.DB_PATH) as conn:        
            cur = conn.cursor()
            for item in items_list:
                query = 'SELECT * FROM auction_statistics WHERE item_id = ? AND date BETWEEN ? AND ?'
                params = [item, start_date, end_date]
                df = pd.read_sql_query(query, conn, params=params)
                
                names = df.columns[2:]
                records = df.iloc[:, 2:].values
                statics_records[item] = []
                for record in records:
                    statics_records[item].append(dict(zip(names, record)))
        
        self.update_firebase_node('/wow/auction', statics_records)

    def update_firebase_node(self, path, data):
        """
        更新Firebase中的节点数据
        """
        StorageFirebase.updateNodeByDict(path, data)

    def fetch_commodities_data(self):
        """
        获取并处理商品数据
        将数据保存到本地，更新物品列表，计算统计信息，并检查便宜商品
        """
        data_dir = 'data/auction/'
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        snapshot_path = f'{data_dir}commodities-{self.timestamp}.json'
        try:
            with open(snapshot_path, 'w') as json_file:
                json.dump(self.data, json_file)
        except OSError as e:
            logger.error("快照寫入失敗 %s：%s", snapshot_path, e)
            return

        if 'auctions' not in self.data:
            logger.error("拍賣資料缺少 auctions 欄位，終止處理")
            return

        self.update_item_list()

        valid_auctions = filter_valid_auction_records(self.data['auctions'])
        if not valid_auctions:
            logger.error("拍賣資料無有效紀錄，終止處理")
            return

        df = pd.json_normalize(valid_auctions)[['id', 'quantity', 'unit_price', 'time_left', 'item.id']]
        date = datetime.now().strftime('%Y-%m-%d')
        df_stat = self.statics_auction_records(df, date)

        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM auction_statistics_realtime;')
            cur.execute('DELETE FROM sqlite_sequence WHERE name = "auction_statistics_realtime";')
            conn.commit()

            df_stat.to_sql('auction_statistics_realtime', conn, if_exists='append', index=False)

            statics_records = {}
            items_list = self.get_item_list()
            for item in items_list:
                cur.execute('SELECT * FROM auction_statistics_realtime WHERE item_id IN (?)', [item])
                names = [desc[0] for desc in cur.description][2:]
                records = [row[2:] for row in cur.fetchall()]
                statics_records[item] = [dict(zip(names, r)) for r in records]

        self.update_firebase_node('/wow/auction_realtime', statics_records)
        self.check_cheap_goods()

    def update_item_list(self):
        """
        更新物品列表
        检查新物品并添加到数据库，更新Firebase中的物品焦点列表
        """
        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM items')
            archived_item_list = [row[0] for row in cur.fetchall()]        
            valid = filter_valid_auction_records(self.data['auctions'])
            auction_item_list = list({x['item']['id'] for x in valid})
            list_difference = [el for el in auction_item_list if el not in archived_item_list]
            
            for item_id in list_difference:
                item_data = self.fetch_item_info(item_id)
                if item_data is None:
                    logger.warning("取得物品資料失敗，跳過 item_id=%s", item_id)
                    continue
                try:
                    list_data = [
                        item_data['id'],
                        item_data['name'],
                        item_data['level'],
                        item_data['required_level'],
                        item_data['quality']['type'],
                        item_data['quality']['name'],
                        item_data['item_class']['name'],
                        item_data['item_class']['id'],
                        item_data['item_subclass']['name'],
                        item_data['item_subclass']['id'],
                    ]
                except KeyError as e:
                    logger.warning("物品資料缺少欄位 %s，跳過 item_id=%s", e, item_id)
                    continue
                cur.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?)", list_data)
                conn.commit()            
            
            cur.execute(f'''
                SELECT * FROM items
                WHERE (id >= {self.item_id_threshold} OR id IN ({','.join(map(str, self.custom_tracked_items))}))
                AND item_class_name IN ({','.join(['?']*len(self.tracked_item_classes))})
            ''', self.tracked_item_classes)
            item_list_records = {row[0]: {
                'id': row[0],
                'name': row[1],
                'level': row[2],
                'required_level': row[3],
                'quality_type': row[4],
                'quality_name': row[5],
                'item_class_name': row[6],
                'item_class_id': row[7],
                'item_subclass_name': row[8],
                'item_subclass_id': row[9]
            } for row in cur.fetchall()}

        self.update_firebase_node('/wow/item_focus_list', item_list_records)

    def fetch_item_info(self, item_id):
        """
        获取特定物品的信息
        """
        return WowGameData.fetchItemInfo(item_id, self.access_token)

    def check_cheap_goods(self):
        """
        检查便宜的商品
        比较当前价格与过去7天的最低价，找出价格下跌的商品
        """
        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(f'''
            WITH last_seven_min AS (
                SELECT
                    item_id,
                    Min(min) AS min
                FROM
                    auction_statistics
                WHERE
                    date IN (
                        SELECT DISTINCT date
                        FROM auction_statistics
                        ORDER BY date DESC
                        LIMIT {self.price_compare_days}
                    )
                GROUP BY item_id
            )
            SELECT
                DISTINCT r.item_id,
                i.item_class_id,
                i.item_subclass_id,
                i.NAME,
                r.min,
                last_seven_min.min AS last_min_gold,
                CAST(
                    ROUND(
                        (r.min - last_seven_min.min) * 1.0 / last_seven_min.min * 1.0 * 100,
                        2
                    ) AS REAL
                ) AS ratio
            FROM
                auction_statistics_realtime r
                INNER JOIN auction_statistics s ON r.item_id = s.item_id
                INNER JOIN items i ON r.item_id = i.id
                LEFT JOIN last_seven_min ON r.item_id = last_seven_min.item_id
            WHERE
                r.min < last_seven_min.min
                AND ratio <= {self.price_drop_threshold}
                AND last_seven_min.min >= {self.min_gold_threshold}
                AND (
                    i.item_class_id = 0
                    AND i.item_subclass_id IN (1, 3, 5, 9)
                    OR i.item_class_id = 8
                );
            ''')
            records = [row for row in cur.fetchall()]

        msg = ['']
        msg.append('📢商品(三星或無星)比過去 7 天的價格下跌')
        for record in [record for record in records if record[6] < 0]:
            url = f"https://rz12345.github.io/wow-auction/#/{record[1]}/{record[2]}/{record[0]}"
            item_name = self.query_item_quality(record[0], record[3])
            price = f"{round(record[4]/10000, 2)}G"
            ratio = f"{'📈+' if record[6] > 0 else '📉'}{record[6]}%"

            if item_name.count('⭐') not in [3, 0]:
                continue
            msg.append(f"{item_name} / {price} / {ratio}，{url}")
        msg.append('---------------')

        msg.append('📢商品(三星或無星)比過去 7 天的價格上漲')
        for record in [record for record in records if record[6] > 0]:
            url = f"https://rz12345.github.io/wow-auction/#/{record[1]}/{record[2]}/{record[0]}"
            item_name = self.query_item_quality(record[0], record[3])
            price = f"{round(record[4]/10000, 2)}G"
            ratio = f"{'📈+' if record[6] > 0 else '📉'}{record[6]}%"

            if item_name.count('⭐') not in [3, 0]:
                continue

            msg.append(f"{item_name} / {price} / {ratio}，{url}")
        msg.append('---------------')
            
        if len(records) > 0:
            for i in range(0, len(msg), self.notify_batch_size):
                batch = [''] + msg[i:i+self.notify_batch_size]
                text = '\n'.join(batch)
                self.notify_message(text)
                self.notify_telegram(text)
                logger.debug("已發送批次通知：%s", batch)

    def notify_message(self, msg):
        """
        发送Discord Webhook消息
        将价格变动信息通过Discord Webhook发送给用户
        Discord 消息有 2000 字元上限，超過需分段發送
        """
        # 從配置文件讀取 Discord Webhook URL
        with open(self.DISCORD_CRED_PATH, "r") as f:
            data = json.load(f)
        webhook_url = data['webhook_url']
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Discord 消息字元限制
        MAX_DISCORD_LENGTH = 2000
        
        # 如果消息長度超過限制，進行分段
        if len(msg) > MAX_DISCORD_LENGTH:
            # 將消息分割成行
            lines = msg.split('\n')
            chunks = []
            current_chunk = ""
            
            # 按行組合消息，確保每段不超過字元限制
            for line in lines:
                # 如果添加當前行會超過限制，先保存當前塊並創建新塊
                if len(current_chunk) + len(line) + 1 > MAX_DISCORD_LENGTH:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    # 添加分隔符，除非是第一行
                    if current_chunk:
                        current_chunk += "\n"
                    current_chunk += line
            
            # 添加最後一個塊
            if current_chunk:
                chunks.append(current_chunk)
            
            status_codes = []
            for chunk in chunks:
                try:
                    r = requests.post(webhook_url, headers=headers, json={"content": chunk}, timeout=10)
                    status_codes.append(r.status_code)
                    if r.status_code not in (200, 204):
                        logger.error("Discord 發送失敗，狀態碼：%s", r.status_code)
                except requests.exceptions.RequestException as e:
                    logger.error("Discord 請求例外：%s", e)
            return status_codes
        else:
            try:
                r = requests.post(webhook_url, headers=headers, json={"content": msg}, timeout=10)
                if r.status_code not in (200, 204):
                    logger.error("Discord 發送失敗，狀態碼：%s", r.status_code)
                return r.status_code
            except requests.exceptions.RequestException as e:
                logger.error("Discord 請求例外：%s", e)
                return None

    def archive_old_files(self):
        """
        封存超過 28 天的拍賣 JSON 快照至 data/auction/archived/
        每個月的檔案壓縮為一個 auction-{YYYYMM}.7z，壓縮成功後刪除原始檔
        """
        auction_dir = Path('data/auction/')
        archive_dir = auction_dir / 'archived'
        archive_dir.mkdir(parents=True, exist_ok=True)

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=28)

        # 依年月分組需要封存的檔案
        month_files: dict[str, list[Path]] = {}
        for f in auction_dir.glob('commodities-*.json'):
            try:
                ts = int(f.stem.split('-')[1])
            except (IndexError, ValueError):
                continue
            file_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if file_dt >= cutoff:
                continue
            ym = file_dt.strftime('%Y%m')
            month_files.setdefault(ym, []).append(f)

        if not month_files:
            logger.info("archive_old_files: 沒有需要封存的檔案")
            return

        for ym, files in sorted(month_files.items()):
            archive_path = archive_dir / f'auction-{ym}.7z'
            try:
                with py7zr.SevenZipFile(archive_path, mode='a') as z:
                    existing = set(z.getnames()) if archive_path.exists() else set()
                    for f in files:
                        if f.name not in existing:
                            z.write(f, arcname=f.name)
                for f in files:
                    f.unlink()
                logger.info("archive_old_files: %s → %s（%d 個檔案）", ym, archive_path.name, len(files))
            except Exception as e:
                logger.error("archive_old_files: %s 封存失敗 — %s", ym, e)

    def notify_telegram(self, msg):
        """
        發送 Telegram Bot 訊息
        Telegram 單則訊息上限為 4096 字元，超過需分段發送
        """
        with open(self.TELEGRAM_CRED_PATH, "r") as f:
            data = json.load(f)
        bot_token = data['bot_token']
        chat_id = data['chat_id']

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        headers = {"Content-Type": "application/json"}
        MAX_TELEGRAM_LENGTH = 4096

        chunks = []
        if len(msg) > MAX_TELEGRAM_LENGTH:
            lines = msg.split('\n')
            current_chunk = ""
            for line in lines:
                if len(current_chunk) + len(line) + 1 > MAX_TELEGRAM_LENGTH:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk = f"{current_chunk}\n{line}" if current_chunk else line
            if current_chunk:
                chunks.append(current_chunk)
        else:
            chunks = [msg]

        status_codes = []
        for chunk in chunks:
            try:
                r = requests.post(url, headers=headers, json={"chat_id": chat_id, "text": chunk}, timeout=10)
                status_codes.append(r.status_code)
                if r.status_code != 200:
                    logger.error("Telegram 發送失敗，狀態碼：%s，回應：%s", r.status_code, r.text)
            except requests.exceptions.RequestException as e:
                logger.error("Telegram 請求例外：%s", e)
        return status_codes

    def query_item_quality(self, item_id, item_name):
        """
        查询物品质量
        根据物品ID和名称，确定物品的质量等级（用星星表示）
        """
        with sqlite3.connect(self.DB_PATH) as conn:
            cur = conn.cursor() 
            cur.execute(f'''
                SELECT name, id_list
                FROM (
                    SELECT
                        name,
                        GROUP_CONCAT(id) as id_list
                    FROM items
                    WHERE
                        id >= {self.item_id_threshold} AND
                        item_class_name IN ({','.join(['?']*len(self.tracked_item_classes))})
                    GROUP BY name
                    HAVING COUNT(id) = 3
                )
                WHERE
                    id_list LIKE ?
            ''', self.tracked_item_classes + [f'%{item_id}%'])
            records = cur.fetchall()
        
        if records:
            id_list = records[0][1].split(',')
            quality = id_list.index(str(item_id)) + 1
            return f"{item_name} {'⭐' * quality}"
        return item_name