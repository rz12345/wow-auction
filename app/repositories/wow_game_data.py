import requests
#import os
import re
import json
import time
#from pathlib import Path

class WowGameData:
    API_REGION = 'https://tw.api.blizzard.com'
    REAMLS_DATA_URI = '/data/wow/connected-realm/index'
    AUCTION_DATA_URI = '/data/wow/connected-realm/{}/auctions'
    COMMODITIES_DATA_URI = '/data/wow/auctions/commodities'
    ITEM_DATA_URI = '/data/wow/item/{}'
    
    #def __init__(self):
        #self.access_token = BattleNet.getToken()
        
    def fetchRealmsData(access_token):
        data = None
        headers = {'Authorization': f'Bearer {access_token}'}
        get_params = {'namespace':'dynamic-tw'}
        r = requests.get(__class__.API_REGION+__class__.REAMLS_DATA_URI, headers=headers, params=get_params)
        if r.status_code == 200:
            data = r.json()
        return data
    
    def fetchRealmsList(access_token):
        realms_data = __class__.fetchRealmsData(access_token)
        realm_sets = {}
        for record in realms_data['connected_realms']:        
            url = record['href']
            realm_id = re.findall(r'\d+', url)[0]
            headers = {'Authorization': f'Bearer {access_token}'}
            get_params = {'namespace':'dynamic-tw'}
            r = requests.get(url, headers=headers, params=get_params)
            if r.status_code == 200:
                data = r.json()
            realm_set = []
            for realm in data['realms']:
                realm_set.append(realm['name']['zh_TW'])
            realm_sets[realm_id] = realm_set
        with open('../data/realm_sets.json', 'w') as f:
            json.dump(realm_sets, f)
        return realm_sets

    def fetchAuctionData(realm_id, access_token):
        data = None  
        headers = {'Authorization': f'Bearer {access_token}'}
        get_params = {'namespace':'dynamic-tw','locale':'zh_TW'}
        r = requests.get(__class__.API_REGION+__class__.AUCTION_DATA_URI.format(realm_id), headers=headers, params=get_params)
        if r.status_code == 200:
            data = r.json()
        return data
    
    def fetchCommoditiesData(access_token):
        data = None
        headers = {'Authorization': f'Bearer {access_token}'}
        get_params = {'namespace':'dynamic-tw','locale':'zh_TW'}
        r = requests.get(__class__.API_REGION+__class__.COMMODITIES_DATA_URI, headers=headers, params=get_params)
        if r.status_code == 200:
            data = r.json()
        return data
    
    def fetchItemInfo(item_id, access_token):
        data = None
        headers = {'Authorization': f'Bearer {access_token}'}
        get_params = {'namespace':'static-tw','locale':'zh_TW'}
        r = requests.get(__class__.API_REGION+__class__.ITEM_DATA_URI.format(item_id), headers=headers, params=get_params)
        if r.status_code == 200:
            data = r.json()
        time.sleep(1)
        return data