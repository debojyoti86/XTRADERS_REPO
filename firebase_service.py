import os
from firebase_admin import credentials, initialize_app, auth, firestore
from dotenv import load_dotenv
import pyrebase

class FirebaseService:
    def __init__(self):
        load_dotenv()
        
        # Validate required environment variables
        required_vars = [
            'FIREBASE_PROJECT_ID',
            'FIREBASE_PRIVATE_KEY_ID',
            'FIREBASE_PRIVATE_KEY',
            'FIREBASE_CLIENT_EMAIL',
            'FIREBASE_CLIENT_ID',
            'FIREBASE_CLIENT_CERT_URL',
            'FIREBASE_API_KEY'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise EnvironmentError(
                f"Missing required Firebase configuration variables: {', '.join(missing_vars)}\n"
                "Please ensure all required variables are set in your .env file."
            )
        
        # Initialize Firebase Admin SDK
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.getenv('FIREBASE_PROJECT_ID'),
            "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
            "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.getenv('FIREBASE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
        })
        self.admin_app = initialize_app(cred)
        self.db = firestore.client()
        
        # Initialize Pyrebase for client-side operations
        config = {
            "apiKey": os.getenv('FIREBASE_API_KEY'),
            "authDomain": f"{os.getenv('FIREBASE_PROJECT_ID')}.firebaseapp.com",
            "databaseURL": f"https://{os.getenv('FIREBASE_PROJECT_ID')}.firebaseio.com",
            "storageBucket": f"{os.getenv('FIREBASE_PROJECT_ID')}.appspot.com",
            "serviceAccount": cred
        }
        self.firebase = pyrebase.initialize_app(config)
        self.auth = self.firebase.auth()
    
    def sign_up(self, email, password):
        try:
            user = self.auth.create_user_with_email_and_password(email, password)
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def sign_in(self, email, password):
        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_user_data(self, user_id):
        try:
            doc = self.db.collection('users').document(user_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            return None
    
    def update_user_data(self, user_id, data):
        try:
            self.db.collection('users').document(user_id).set(data, merge=True)
            return True
        except Exception as e:
            return False
    
    def save_trade(self, user_id, trade_data):
        try:
            self.db.collection('trades').add({
                'user_id': user_id,
                'timestamp': firestore.SERVER_TIMESTAMP,
                **trade_data
            })
            return True
        except Exception as e:
            return False