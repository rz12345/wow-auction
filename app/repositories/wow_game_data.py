import requests
import re
import json
import time
import logging

logger = logging.getLogger(__name__)

class WowGameData:
    API_REGION = 'https://tw.api.blizzard.com'
    REAMLS_DATA_URI = '/data/wow/connected-realm/index'
    AUCTION_DATA_URI = '/data/wow/connected-realm/{}/auctions'
    COMMODITIES_DATA_URI = '/data/wow/auctions/commodities'
    ITEM_DATA_URI = '/data/wow/item/{}'

    def _get(url, headers, params):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.error("API 請求失敗 %s：%s", url, e)
            return None
        if r.status_code != 200:
            logger.error("API 回應非 200 %s：%s", url, r.status_code)
            return None
        try:
            return r.json()
        except requests.exceptions.JSONDecodeError as e:
            logger.error("API 回應 JSON 解析失敗 %s：%s", url, e)
            return None

    def fetchRealmsData(access_token):
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'namespace': 'dynamic-tw'}
        return WowGameData._get(WowGameData.API_REGION + WowGameData.REAMLS_DATA_URI, headers, params)

    def fetchRealmsList(access_token):
        realms_data = WowGameData.fetchRealmsData(access_token)
        if not realms_data or 'connected_realms' not in realms_data:
            logger.error("fetchRealmsList：無法取得 connected_realms 資料")
            return {}

        realm_sets = {}
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'namespace': 'dynamic-tw'}
        for record in realms_data['connected_realms']:
            url = record.get('href')
            if not url:
                continue
            realm_id = re.findall(r'\d+', url)
            if not realm_id:
                continue
            data = WowGameData._get(url, headers, params)
            if not data or 'realms' not in data:
                continue
            realm_sets[realm_id[0]] = [r['name']['zh_TW'] for r in data['realms']]

        with open('../data/realm_sets.json', 'w') as f:
            json.dump(realm_sets, f)
        return realm_sets

    def fetchAuctionData(realm_id, access_token):
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'namespace': 'dynamic-tw', 'locale': 'zh_TW'}
        url = WowGameData.API_REGION + WowGameData.AUCTION_DATA_URI.format(realm_id)
        return WowGameData._get(url, headers, params)

    def fetchCommoditiesData(access_token):
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'namespace': 'dynamic-tw', 'locale': 'zh_TW'}
        url = WowGameData.API_REGION + WowGameData.COMMODITIES_DATA_URI
        return WowGameData._get(url, headers, params)

    def fetchItemInfo(item_id, access_token):
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {'namespace': 'static-tw', 'locale': 'zh_TW'}
        url = WowGameData.API_REGION + WowGameData.ITEM_DATA_URI.format(item_id)
        data = WowGameData._get(url, headers, params)
        time.sleep(1)
        return data
