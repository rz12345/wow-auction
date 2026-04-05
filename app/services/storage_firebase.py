import firebase_admin
import json
import logging
from firebase_admin import credentials,storage,db,firestore
from datetime import datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

class StorageFirebase:
    DATABASE_URL = 'https://jojocat-wow-f72a5-default-rtdb.asia-southeast1.firebasedatabase.app/'
    STORAGE_URL = 'jojocat-wow-f72a5.appspot.com'
    CRED_PATH = 'app/configs/firebase-cred.json'
    
    def deleteNode(node_ref):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'databaseURL': __class__.DATABASE_URL
        })
        db.reference(node_ref).delete()
        firebase_admin.delete_app(firebase_admin.get_app())

    # Firebase realtiem database
    def updateNodeByJson(node_ref,json_file):
        with open(json_file, "r") as f:
            file_contents = json.load(f)
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'databaseURL': __class__.DATABASE_URL
        })
        db.reference(node_ref).set(file_contents)
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # Firebase realtiem database
    def updateNodeByDict(node_ref,data):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'databaseURL': __class__.DATABASE_URL
        })
        db.reference(node_ref).set(data)
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # Firebase Cloud Firestore
    def updateCollection(collection_name,document_id,data_dict):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH))
        db = firestore.client()
        doc_ref = db.collection(collection_name).document(document_id)
        doc_ref.set({'data': data_dict})
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # Firebase Cloud Firestore
    def getCollectionDocIdList(collection_name):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH))
        db = firestore.client()
        doc_ref = db.collection(collection_name)
        docs = doc_ref.stream()
        document_ids = [doc.id for doc in docs]
        firebase_admin.delete_app(firebase_admin.get_app())
        return document_ids
    
    # Firebase Cloud Firestore
    def getDocuments(collection_name):
        # 取得當前日期
        current_date = datetime.now()

        # 生成最近28天的日期列表
        recent_dates = [(current_date - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(28)]
        
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH))
        db = firestore.client()
        doc_ref = db.collection(collection_name)
        docs = doc_ref.stream()
        docs = [{doc.id:doc.to_dict()['data']} for doc in docs if str(doc.id) in recent_dates]
        firebase_admin.delete_app(firebase_admin.get_app())
        
        return docs
    
    def deleteDocument(collection_name, document_id):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH))
        db = firestore.client()
        doc_ref = db.collection(collection_name).document(document_id)
        doc_ref.delete()
        logger.info("Document %s deleted successfully.", document_id)
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # FirebaseStorage
    def uploadJsonByDict(filename,dict_data):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'storageBucket': __class__.STORAGE_URL
        })
        token = uuid4()
        metadata = {"firebaseStorageDownloadTokens": token}
        bucket = storage.bucket()
        blob = bucket.blob(filename)
        blob.metadata = metadata
        json_data = json.dumps(dict_data)
        blob.upload_from_string(json_data, content_type = 'application/json')
        logger.info("JSON 檔案已上傳至 Firebase Storage：%s", filename)
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # FirebaseStorage
    def getStorageFileList(path):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'storageBucket': __class__.STORAGE_URL
        })
        bucket = storage.bucket()
        blobs = bucket.list_blobs(prefix=path)
        
        file_list = []
        for blob in blobs:
            file_list.append(blob.name)

        firebase_admin.delete_app(firebase_admin.get_app())
        return file_list
    
    # FirebaseStorage
    def getStorageJsonFileContent(filename):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'storageBucket': __class__.STORAGE_URL
        })
        bucket = storage.bucket()
        blob = bucket.blob(filename)
        json_data = blob.download_as_text()
        data = json.loads(json_data)        
        firebase_admin.delete_app(firebase_admin.get_app())
        return data
    
    # FirebaseStorage
    def deleteStorageFile(filename):
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'storageBucket': __class__.STORAGE_URL
        })
        bucket = storage.bucket()
        blob = bucket.blob(filename)
        blob.delete()
        logger.info("已成功刪除檔案：%s", filename)
        firebase_admin.delete_app(firebase_admin.get_app())
        
    # FirebaseStorage
    def getStorageUsage():
        firebase_admin.initialize_app(credentials.Certificate(__class__.CRED_PATH), {
            'storageBucket': __class__.STORAGE_URL
        })
        bucket = storage.bucket()

        # 查詢已傳送的頻寬和已儲存的位元組數
        storage_info = bucket.get_storage_class()

        logger.info("已傳送的頻寬（已使用的頻寬）：%s", storage_info["total"]["sent"])
        logger.info("已儲存的位元組數（已使用的儲存容量）：%s", storage_info["total"]["stored"])
        firebase_admin.delete_app(firebase_admin.get_app())
        return storage_info
        