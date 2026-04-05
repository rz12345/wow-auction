import requests
import json
import logging

logger = logging.getLogger(__name__)

class BattleNet:
    CRED_PATH = 'app/configs/battle-net-cred.json'
    TOKEN_URL = 'https://us.battle.net/oauth/token'

    def getToken():
        try:
            with open(BattleNet.CRED_PATH, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("讀取 Battle.net 憑證失敗：%s", e)
            return None

        client_id = data.get('client_id')
        client_secret = data.get('client_secret')
        if not client_id or not client_secret:
            logger.error("Battle.net 憑證缺少 client_id 或 client_secret")
            return None

        try:
            r = requests.post(
                BattleNet.TOKEN_URL,
                auth=(client_id, client_secret),
                params={'grant_type': 'client_credentials'},
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            logger.error("取得 Battle.net token 時發生網路錯誤：%s", e)
            return None

        if r.status_code != 200:
            logger.error("Battle.net token 請求失敗，狀態碼：%s", r.status_code)
            return None

        return r.json().get('access_token')
