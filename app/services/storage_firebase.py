import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

logger = logging.getLogger(__name__)

_SCOPES = [
    'https://www.googleapis.com/auth/firebase.database',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/datastore',
    'https://www.googleapis.com/auth/devstorage.full_control',
]


class StorageFirebase:
    PROJECT_ID   = 'jojocat-wow-f72a5'
    DATABASE_URL = 'https://jojocat-wow-f72a5-default-rtdb.asia-southeast1.firebasedatabase.app'
    STORAGE_BUCKET = 'jojocat-wow-f72a5.appspot.com'
    CRED_PATH    = 'app/configs/firebase-cred.json'

    _session: AuthorizedSession | None = None

    @classmethod
    def _get_session(cls) -> AuthorizedSession:
        if cls._session is None:
            creds = service_account.Credentials.from_service_account_file(
                cls.CRED_PATH, scopes=_SCOPES
            )
            cls._session = AuthorizedSession(creds)
        return cls._session

    # ── Realtime Database ────────────────────────────────────────────────────

    @staticmethod
    def _rtdb_url(node_ref: str) -> str:
        path = node_ref.strip('/')
        return f"{StorageFirebase.DATABASE_URL}/{path}.json"

    def updateNodeByDict(node_ref: str, data: dict) -> None:
        url = StorageFirebase._rtdb_url(node_ref)
        r = StorageFirebase._get_session().put(url, json=data, timeout=30)
        if r.status_code != 200:
            logger.error("RT DB 寫入失敗 %s：%s %s", node_ref, r.status_code, r.text)
        else:
            logger.info("RT DB 寫入完成：%s", node_ref)

    def updateNodeByJson(node_ref: str, json_file: str) -> None:
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("讀取 JSON 檔失敗 %s：%s", json_file, e)
            return
        StorageFirebase.updateNodeByDict(node_ref, data)

    def deleteNode(node_ref: str) -> None:
        url = StorageFirebase._rtdb_url(node_ref)
        r = StorageFirebase._get_session().delete(url, timeout=30)
        if r.status_code != 200:
            logger.error("RT DB 刪除失敗 %s：%s", node_ref, r.status_code)
        else:
            logger.info("RT DB 刪除完成：%s", node_ref)

    # ── Cloud Firestore ──────────────────────────────────────────────────────

    @staticmethod
    def _fs_base() -> str:
        pid = StorageFirebase.PROJECT_ID
        return f"https://firestore.googleapis.com/v1/projects/{pid}/databases/(default)/documents"

    @staticmethod
    def _to_fs_value(value) -> dict:
        """Python 值 → Firestore REST 值格式（遞迴）。"""
        if value is None:
            return {'nullValue': None}
        if isinstance(value, bool):
            return {'booleanValue': value}
        if isinstance(value, int):
            return {'integerValue': str(value)}
        if isinstance(value, float):
            return {'doubleValue': value}
        if isinstance(value, str):
            return {'stringValue': value}
        if isinstance(value, list):
            return {'arrayValue': {'values': [StorageFirebase._to_fs_value(v) for v in value]}}
        if isinstance(value, dict):
            return {'mapValue': {'fields': {k: StorageFirebase._to_fs_value(v) for k, v in value.items()}}}
        return {'stringValue': str(value)}

    @staticmethod
    def _from_fs_value(fs_val: dict):
        """Firestore REST 值格式 → Python 值（遞迴）。"""
        if 'nullValue'     in fs_val: return None
        if 'booleanValue'  in fs_val: return fs_val['booleanValue']
        if 'integerValue'  in fs_val: return int(fs_val['integerValue'])
        if 'doubleValue'   in fs_val: return fs_val['doubleValue']
        if 'stringValue'   in fs_val: return fs_val['stringValue']
        if 'arrayValue'    in fs_val:
            return [StorageFirebase._from_fs_value(v) for v in fs_val['arrayValue'].get('values', [])]
        if 'mapValue'      in fs_val:
            return {k: StorageFirebase._from_fs_value(v) for k, v in fs_val['mapValue'].get('fields', {}).items()}
        return None

    def updateCollection(collection_name: str, document_id: str, data_dict: dict) -> None:
        url = f"{StorageFirebase._fs_base()}/{collection_name}/{document_id}"
        body = {'fields': {'data': StorageFirebase._to_fs_value(data_dict)}}
        r = StorageFirebase._get_session().patch(url, json=body, timeout=30)
        if r.status_code not in (200, 201):
            logger.error("Firestore 寫入失敗 %s/%s：%s", collection_name, document_id, r.status_code)

    def getCollectionDocIdList(collection_name: str) -> list[str]:
        url = f"{StorageFirebase._fs_base()}/{collection_name}"
        r = StorageFirebase._get_session().get(url, timeout=30)
        if r.status_code != 200:
            logger.error("Firestore 列表失敗 %s：%s", collection_name, r.status_code)
            return []
        docs = r.json().get('documents', [])
        return [d['name'].split('/')[-1] for d in docs]

    def getDocuments(collection_name: str) -> list[dict]:
        recent_dates = {
            (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(28)
        }
        url = f"{StorageFirebase._fs_base()}/{collection_name}"
        r = StorageFirebase._get_session().get(url, timeout=30)
        if r.status_code != 200:
            logger.error("Firestore 讀取失敗 %s：%s", collection_name, r.status_code)
            return []
        results = []
        for doc in r.json().get('documents', []):
            doc_id = doc['name'].split('/')[-1]
            if doc_id not in recent_dates:
                continue
            try:
                data = StorageFirebase._from_fs_value(doc['fields']['data'])
                results.append({doc_id: data})
            except (KeyError, TypeError) as e:
                logger.warning("Firestore 文件格式不符，跳過 %s：%s", doc_id, e)
        return results

    def deleteDocument(collection_name: str, document_id: str) -> None:
        url = f"{StorageFirebase._fs_base()}/{collection_name}/{document_id}"
        r = StorageFirebase._get_session().delete(url, timeout=30)
        if r.status_code != 200:
            logger.error("Firestore 刪除失敗 %s/%s：%s", collection_name, document_id, r.status_code)
        else:
            logger.info("Document %s deleted successfully.", document_id)

    # ── Cloud Storage (GCS JSON API) ─────────────────────────────────────────

    @staticmethod
    def _gcs_obj_url(filename: str) -> str:
        bucket = StorageFirebase.STORAGE_BUCKET
        encoded = quote(filename, safe='')
        return f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{encoded}"

    def uploadJsonByDict(filename: str, dict_data: dict) -> None:
        bucket = StorageFirebase.STORAGE_BUCKET
        upload_url = (
            f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
            f"?uploadType=media&name={quote(filename, safe='')}"
        )
        payload = json.dumps(dict_data).encode('utf-8')
        r = StorageFirebase._get_session().post(
            upload_url, data=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60,
        )
        if r.status_code not in (200, 201):
            logger.error("Storage 上傳失敗 %s：%s", filename, r.status_code)
        else:
            logger.info("JSON 檔案已上傳至 Firebase Storage：%s", filename)

    def getStorageFileList(path: str) -> list[str]:
        bucket = StorageFirebase.STORAGE_BUCKET
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o"
        r = StorageFirebase._get_session().get(url, params={'prefix': path}, timeout=30)
        if r.status_code != 200:
            logger.error("Storage 列表失敗 %s：%s", path, r.status_code)
            return []
        return [item['name'] for item in r.json().get('items', [])]

    def getStorageJsonFileContent(filename: str) -> dict | None:
        url = StorageFirebase._gcs_obj_url(filename) + '?alt=media'
        r = StorageFirebase._get_session().get(url, timeout=60)
        if r.status_code != 200:
            logger.error("Storage 下載失敗 %s：%s", filename, r.status_code)
            return None
        try:
            return r.json()
        except Exception as e:
            logger.error("Storage 回應 JSON 解析失敗 %s：%s", filename, e)
            return None

    def deleteStorageFile(filename: str) -> None:
        url = StorageFirebase._gcs_obj_url(filename)
        r = StorageFirebase._get_session().delete(url, timeout=30)
        if r.status_code not in (200, 204):
            logger.error("Storage 刪除失敗 %s：%s", filename, r.status_code)
        else:
            logger.info("已成功刪除檔案：%s", filename)
