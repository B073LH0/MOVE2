# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, logging, requests
from typing import Optional, Dict, Any

try:
    import firebase_admin
    from firebase_admin import credentials, db
    FIREBASE_SDK = True
except Exception:
    FIREBASE_SDK = False

logger = logging.getLogger("neurosense.firebase")

# --- Config ---
DATABASE_URL = os.environ.get("NS_DATABASE_URL", "https://bioapp-496ae-default-rtdb.firebaseio.com/")
WEB_API_KEY  = os.environ.get("NS_WEB_API_KEY", "AIzaSyA5eJ2pIGSuYktxW8J21crogLP2YPA046s")
SERVICE_ACCOUNT_JSON = os.environ.get("NS_SERVICE_ACCOUNT_JSON", "serviceAccountKey.json")
SESSION_PATH = os.path.join(os.path.expanduser("~"), ".sintec_move_session.json")

# ------- Sessão -------
class FirebaseSession:
    def __init__(self):
        self.id_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_email: Optional[str] = None
        self.user_uid: Optional[str] = None
    def is_logged_in(self): return bool(self.id_token and self.user_uid)

firebase_session = FirebaseSession()

def _save_session():
    try:
        data = {
            "refresh_token": firebase_session.refresh_token,
            "user_email": firebase_session.user_email,
            "user_uid": firebase_session.user_uid,
        }
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Não foi possível salvar a sessão: %s", e)

def _load_session_file() -> Dict[str, Any]:
    try:
        if os.path.exists(SESSION_PATH):
            with open(SESSION_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Erro lendo sessão: %s", e)
    return {}

def _clear_session_file():
    try:
        if os.path.exists(SESSION_PATH):
            os.remove(SESSION_PATH)
    except Exception:
        pass

# ------- Admin SDK (RTDB) -------
def init_firebase_admin():
    if not FIREBASE_SDK:
        return
    if getattr(firebase_admin, "_apps", None):
        return
    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        logger.info("SERVICE_ACCOUNT_JSON não encontrado; RTDB admin ficará inativo.")
        return
    cred = credentials.Certificate(SERVICE_ACCOUNT_JSON)
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

def rtdb_get(path: str):
    if FIREBASE_SDK and getattr(firebase_admin, "_apps", None):
        try:
            return db.reference(path).get()
        except Exception as e:
            logger.warning("RTDB get falhou em %s: %s", path, e)
            return None
    return None

# ------- Auth REST -------
def firebase_login_email_password(email: str, password: str) -> Dict[str, Any]:
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload, timeout=15); r.raise_for_status()
    data = r.json()
    firebase_session.id_token = data.get("idToken")
    firebase_session.refresh_token = data.get("refreshToken")
    firebase_session.user_email = data.get("email")
    firebase_session.user_uid = data.get("localId")
    _save_session()
    init_firebase_admin()
    logger.info("Login OK: %s (uid=%s)", firebase_session.user_email, firebase_session.user_uid)
    return data

def firebase_refresh_session() -> bool:
    """Usa o refresh_token salvo para obter novo idToken."""
    data = _load_session_file()
    rt = data.get("refresh_token")
    if not rt:
        return False
    url = f"https://securetoken.googleapis.com/v1/token?key={WEB_API_KEY}"
    payload = {"grant_type": "refresh_token", "refresh_token": rt}
    try:
        r = requests.post(url, data=payload, timeout=15); r.raise_for_status()
        res = r.json()
        firebase_session.id_token = res.get("id_token")
        firebase_session.refresh_token = res.get("refresh_token") or rt
        firebase_session.user_uid = res.get("user_id") or data.get("user_uid")
        firebase_session.user_email = data.get("user_email")
        _save_session()
        init_firebase_admin()
        logger.info("Sessão restaurada (uid=%s)", firebase_session.user_uid)
        return True
    except Exception as e:
        logger.info("Falha ao renovar sessão: %s", e)
        return False

def try_auto_login() -> bool:
    """Chame no início do app; entra automático se houver refresh_token válido."""
    ok = firebase_refresh_session()
    return ok

def firebase_logout():
    firebase_session.id_token = None
    firebase_session.refresh_token = None
    firebase_session.user_email = None
    firebase_session.user_uid = None
    _clear_session_file()
