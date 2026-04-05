import requests
import json

class BattleNet:
    CRED_PATH = 'app/configs/battle-net-cred.json'
    
    def getToken():
        with open(__class__.CRED_PATH, "r") as f:
            data = json.load(f)
        client_id = data['client_id']
        client_secret = data['client_secret']
        
        access_token = None
        url = 'https://us.battle.net/oauth/token'
        credentials = (client_id, client_secret)
        post_fields = {'grant_type':'client_credentials'}
        r = requests.post(url,auth=credentials,params=post_fields)
        if r.status_code == 200:
            access_token = r.json()['access_token']
        return access_token