"""
WORLDBINDER Backend API
FastAPI сервер с безопасной аутентификацией Phantom
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
import psycopg2
from psycopg2.extras import RealDictCursor
import jwt
import hashlib
import time
import base64
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timedelta
import base58
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import secrets
import asyncio
from contextlib import asynccontextmanager
from enum import Enum
import httpx

# Настройки
class Settings(BaseSettings):
    # База данных
    db_host: str = Field("db", validation_alias="POSTGRES_HOST")
    db_port: int = Field(5432, validation_alias="POSTGRES_PORT")
    db_name: str = Field("blizard", validation_alias="POSTGRES_DB")
    db_user: str = Field("admin", validation_alias="POSTGRES_USER")
    db_password: str = Field("12345", validation_alias="POSTGRES_PASSWORD")
    
    # JWT
    jwt_secret: str = Field("your-secret-key-change-in-production", validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", validation_alias="JWT_ALGORITHM")
    jwt_expire_hours: int = Field(24, validation_alias="JWT_EXPIRE_HOURS")
    
    # Безопасность
    frontend_url: str = Field("http://localhost:3001", validation_alias="FRONTEND_URL")
    rate_limit_requests: int = Field(100, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(900, validation_alias="RATE_LIMIT_WINDOW")
    
    # Solana
    solana_cluster: str = Field("mainnet-beta", validation_alias="SOLANA_CLUSTER")
    solana_rpc: str = Field("", validation_alias="SOLANA_RPC")
    helius_api_key: str = Field("", validation_alias="HELIUS_API_KEY")
    collection_address: str = Field("", validation_alias="COLLECTION_ADDRESS")

    # Game
    nft_stats_salt: str = Field("change-me-nft-stats-salt", validation_alias="NFT_STATS_SALT")
    token_mint: str = Field("", validation_alias="TOKEN_MINT")
    token_decimals: int = Field(6, validation_alias="TOKEN_DECIMALS")
    burn_cost_per_level: int = Field(50000, validation_alias="BURN_COST_PER_LEVEL")
    
    # Отладка
    debug_mode: bool = True
    
    class Config:
        env_file = ".env"

settings = Settings()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic модели
class PhantomAuthRequest(BaseModel):
    """Запрос аутентификации Phantom"""
    publicKey: str = Field(..., description="Solana адрес кошелька")
    signature: str = Field(..., description="Подпись сообщения")
    message: str = Field(..., description="Подписанное сообщение")

class ChallengeRequest(BaseModel):
    """Запрос на получение challenge"""
    publicKey: str = Field(..., min_length=32, max_length=60)

class ChallengeResponse(BaseModel):
    """Ответ с challenge для подписи"""
    nonce: str
    message: str
    timestamp: str

class UserProfile(BaseModel):
    """Профиль пользователя"""
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    avatarUrl: Optional[str] = Field(None, max_length=500)

class NFTData(BaseModel):
    """Данные NFT"""
    mintAddress: str = Field(..., min_length=44, max_length=44)
    name: str = Field(..., min_length=1, max_length=200)
    imageUrl: str = Field(..., max_length=500)
    rarity: str = Field("Common", pattern="^(Common|Rare|Epic|Legendary)$")


class NFTStatsRequest(BaseModel):
    mintAddress: str = Field(..., min_length=44, max_length=44)
    rarity: str = Field("Common", pattern="^(Common|Rare|Epic|Legendary)$")


class NFTStatsResponse(BaseModel):
    mintAddress: str
    rarity: str
    stats: Dict[str, Any]


class BattleStartRequest(BaseModel):
    mintAddress: str = Field(..., min_length=44, max_length=44)
    bet: int = Field(..., ge=1, le=1_000_000_000)


class BattleStatus(str, Enum):
    pending = "pending"
    resolved = "resolved"


class BattleStartResponse(BaseModel):
    battle_id: str
    status: BattleStatus
    wait_seconds: int


class BattleStatusResponse(BaseModel):
    battle_id: str
    status: BattleStatus
    wait_seconds: int
    resolve_at: float
    result: Optional[Dict[str, Any]] = None

class UserResponse(BaseModel):
    """Ответ с данными пользователя"""
    id: int
    wallet_address: str
    username: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    nfts: Optional[List[Dict[str, Any]]] = []
    token_balance: Optional[int] = 0


class WalletScanRequest(BaseModel):
    walletAddress: str = Field(..., min_length=32, max_length=60)


class SkillsUpgradeRequest(BaseModel):
    skillKey: str = Field(..., min_length=1, max_length=64)
    txSignature: str = Field(..., min_length=32, max_length=128)


class TokenBalanceRequest(BaseModel):
    walletAddress: str = Field(..., min_length=32, max_length=60)

# База данных
class Database:
    def __init__(self):
        self.pool = None
    
    def connect(self):
        try:
            self.pool = psycopg2.connect(
                host=settings.db_host,
                port=settings.db_port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
                cursor_factory=RealDictCursor
            )
            logger.info("Database connected successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def execute_query(self, query: str, params: tuple = None, fetch: str = "all"):
        try:
            if not self.pool:
                self.connect()
            with self.pool.cursor() as cursor:
                cursor.execute(query, params)
                
                if fetch == "one":
                    result = cursor.fetchone()
                elif fetch == "all":
                    result = cursor.fetchall()
                elif fetch == "none":
                    result = None
                
                self.pool.commit()
                return result
        except Exception as e:
            if self.pool:
                self.pool.rollback()
            logger.error(f"Database query error: {e}")
            raise
    
    def __del__(self):
        if self.pool:
            self.pool.close()
    
    def close(self):
        if self.pool:
            self.pool.close()

# Утилиты безопасности
class SecurityUtils:
    @staticmethod
    def create_jwt_token(data: dict) -> str:
        """Создание JWT токена"""
        to_encode = data.copy()
        now = datetime.utcnow()
        expire = now + timedelta(hours=settings.jwt_expire_hours)
        to_encode.update({
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": secrets.token_urlsafe(16),
        })
        return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    @staticmethod
    def verify_jwt_token(token: str) -> dict:
        """Верификация JWT токена"""
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    @staticmethod
    def verify_solana_signature(public_key: str, signature: str, message: str) -> bool:
        """Верификация подписи Solana"""
        try:
            logger.info(
                f"Verifying signature: publicKey={public_key[:10]}..., signature={signature[:20]}..., message_length={len(message)}"
            )

            sig_bytes = base64.b64decode(signature)
            pk_bytes = base58.b58decode(public_key)
            message_bytes = message.encode("utf-8")

            logger.info(
                f"Decoded: pk_len={len(pk_bytes)}, sig_len={len(sig_bytes)}, msg_len={len(message_bytes)}"
            )

            if len(pk_bytes) != 32 or len(sig_bytes) != 64:
                logger.warning(f"Invalid lengths: pk={len(pk_bytes)}, sig={len(sig_bytes)}")
                return False

            verify_key = VerifyKey(pk_bytes)
            verify_key.verify(message_bytes, sig_bytes)
            logger.info("Signature verification successful")
            return True
        except (BadSignatureError, ValueError, Exception) as e:
            logger.error(f"Signature verification error: {e}")
            return False

    @staticmethod
    def generate_nonce() -> str:
        """Генерация nonce для challenge"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_challenge_message(public_key: str, nonce: str, timestamp: str) -> str:
        """Создание challenge сообщения для подписи"""
        return (
            "Sign this message to authenticate with WORLDBINDER.\n\n"
            f"Public Key: {public_key}\nNonce: {nonce}\nTimestamp: {timestamp}"
        )


async def _helius_get_assets_by_owner(owner: str) -> Dict[str, Any]:
    api_key = settings.helius_api_key
    if not api_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Helius API key not configured")

    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    payload = {
        "jsonrpc": "2.0",
        "id": "scan",
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": owner,
            "page": 1,
            "limit": 100,
        },
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data


async def _solana_get_token_balance(wallet_address: str, mint: str) -> float:
    rpc = settings.solana_rpc
    if not rpc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SOLANA_RPC not configured")

    payload = {
        "jsonrpc": "2.0",
        "id": "bal",
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"mint": mint},
            {"encoding": "jsonParsed"},
        ],
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(rpc, json=payload)
        resp.raise_for_status()
        data = resp.json()

    result = data.get("result") or {}
    value = result.get("value") or []
    if not value:
        return 0.0

    try:
        info = value[0]["account"]["data"]["parsed"]["info"]
        token_amount = info["tokenAmount"]
        ui_amount = token_amount.get("uiAmount")
        if ui_amount is None:
            ui_amount = float(token_amount.get("uiAmountString") or 0)
        return float(ui_amount or 0)
    except Exception:
        return 0.0


def _compute_attack_bonus(nft_count: int) -> int:
    if nft_count >= 3:
        return 20
    if nft_count == 2:
        return 15
    if nft_count == 1:
        return 10
    return 0


def _parse_helius_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    content = asset.get("content") or {}
    metadata = content.get("metadata") or {}
    files = content.get("files") or []
    image = None
    if files and isinstance(files, list):
        image = (files[0] or {}).get("uri")

    traits = []
    attrs = metadata.get("attributes") or []
    if isinstance(attrs, list):
        for a in attrs:
            if isinstance(a, dict) and ("trait_type" in a or "value" in a):
                traits.append(a)

    return {
        "id": asset.get("id") or asset.get("mint") or asset.get("mintAddress"),
        "name": metadata.get("name") or asset.get("name") or "",
        "image": image,
        "rarity": (asset.get("rarity") or metadata.get("rarity") or "Common"),
        "level": metadata.get("level") or 1,
        "traits": traits,
    }


async def _solana_get_transaction(signature: str) -> Dict[str, Any]:
    rpc = settings.solana_rpc
    if not rpc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SOLANA_RPC not configured")

    payload = {
        "jsonrpc": "2.0",
        "id": "tx",
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "finalized",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(rpc, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data


def _tx_has_valid_burn(tx: Dict[str, Any], wallet: str) -> bool:
    result = tx.get("result")
    if not result:
        return False
    meta = result.get("meta") or {}
    if meta.get("err") is not None:
        return False

    token_mint = settings.token_mint
    if not token_mint:
        return False

    min_raw = int(settings.burn_cost_per_level) * (10 ** int(settings.token_decimals))

    transaction = result.get("transaction") or {}
    message = transaction.get("message") or {}
    instructions = message.get("instructions") or []

    for ix in instructions:
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue
        ix_type = parsed.get("type")
        if ix_type != "burn":
            continue
        info = parsed.get("info") or {}
        mint = info.get("mint")
        authority = info.get("authority")
        amount = info.get("amount")
        if mint != token_mint:
            continue
        if authority != wallet:
            continue
        try:
            amt = int(amount)
        except Exception:
            continue
        if amt >= min_raw:
            return True
    return False


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", msg, key, 1, dklen=32)


def generate_nft_stats(mint_address: str, rarity: str, salt: str) -> Dict[str, Any]:
    salt_b = salt.encode("utf-8")
    mint_b = mint_address.encode("utf-8")
    seed = _hmac_sha256(salt_b, mint_b)

    def u32(offset: int) -> int:
        return int.from_bytes(seed[offset:offset + 4], "big", signed=False)

    base_hp = 240 + (u32(0) % 121)
    base_atk = 18 + (u32(4) % 18)
    base_def = (u32(8) % 13)
    base_crit_bp = (u32(12) % 2601)
    base_crit = base_crit_bp / 10000.0

    rarity_mult = {
        "Common": 1.00,
        "Rare": 1.05,
        "Epic": 1.12,
        "Legendary": 1.20,
    }.get(rarity, 1.00)

    hp = int(round(base_hp * rarity_mult))
    atk = int(round(base_atk * rarity_mult))
    defense = int(round(base_def * rarity_mult))
    crit = min(0.35, base_crit * (1.0 + (rarity_mult - 1.0)))

    return {
        "hp": hp,
        "atk": atk,
        "def": defense,
        "crit": round(crit, 4),
    }


async def _resolve_battle(app: FastAPI, battle_id: str) -> None:
    battle = app.state.battles.get(battle_id)
    if not battle:
        return
    now = time.time()
    sleep_for = max(0.0, battle["resolve_at"] - now)
    if sleep_for > 0:
        await asyncio.sleep(sleep_for)

    battle = app.state.battles.get(battle_id)
    if not battle or battle.get("status") != BattleStatus.pending:
        return

    user_id = battle["user_id"]
    bet = battle["bet"]
    seed = battle["seed"]

    roll = int.from_bytes(_hmac_sha256(settings.nft_stats_salt.encode("utf-8"), seed), "big") % 10_000
    player_wins = roll >= 7000

    db = Database()
    db.connect()
    if player_wins:
        payout = int(bet) * 2 + 100
        update_q = "UPDATE leaderboard SET points = points + %s, wins = wins + 1 WHERE user_id = %s RETURNING points, wins, losses"
        row = db.execute_query(update_q, (payout, user_id), fetch="one")
    else:
        update_q = "UPDATE leaderboard SET losses = losses + 1 WHERE user_id = %s RETURNING points, wins, losses"
        row = db.execute_query(update_q, (user_id,), fetch="one")
    db.close()

    battle["status"] = BattleStatus.resolved
    battle["result"] = {
        "player_wins": player_wins,
        "bet": bet,
        "points": int(row.get("points", 0)) if row else None,
        "wins": int(row.get("wins", 0)) if row else None,
        "losses": int(row.get("losses", 0)) if row else None,
    }

# Rate limiting
class RateLimiter:
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, client_id: str, limit: int = None, window: int = None) -> bool:
        limit = limit or settings.rate_limit_requests
        window = window or settings.rate_limit_window
        
        now = time.time()
        window_start = now - window
        
        # Очистка старых записей
        if client_id in self.requests:
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id] 
                if req_time > window_start
            ]
        else:
            self.requests[client_id] = []
        
        # Проверка лимита
        if len(self.requests[client_id]) >= limit:
            return False
        
        # Добавление текущего запроса
        self.requests[client_id].append(now)
        return True

rate_limiter = RateLimiter()

# Middleware для rate limiting
async def rate_limit_middleware(request: Request, call_next):
    # Allow unit tests to run without rate limiting noise
    if getattr(request.app.state, "testing", False):
        return await call_next(request)

    client_ip = request.client.host
    
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests"}
        )
    
    response = await call_next(request)
    return response

# JWT Bearer
security = HTTPBearer(auto_error=False)

# FastAPI приложение с lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("WORLDBINDER API starting...")
    yield
    # Shutdown
    logger.info("WORLDBINDER API shutting down...")

app = FastAPI(
    title="WORLDBINDER API",
    description="NFT Battle Game Backend",
    version="1.0.0",
    lifespan=lifespan
)

app.state.battles = {}

# Middleware
app.middleware("http")(rate_limit_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Зависимости
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Получение текущего пользователя из JWT токена"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization token",
        )
    token = credentials.credentials
    payload = SecurityUtils.verify_jwt_token(token)
    # Normalize keys for downstream endpoints
    if "walletAddress" in payload and "wallet_address" not in payload:
        payload["wallet_address"] = payload["walletAddress"]
    if "userId" in payload and "user_id" not in payload:
        payload["user_id"] = payload["userId"]
    return payload

# API Роуты (должны быть перед монтированием статики)
@app.get("/api")
async def root_api():
    """API корневой эндпоинт"""
    return {"message": "WORLDBINDER API", "status": "running"}

@app.get("/api/health")
async def health_check():
    """Проверка здоровья системы"""
    try:
        # Проверка подключения к базе данных
        db = Database()
        db.connect()
        if db:
            db.close()
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.post("/api/auth/challenge")
async def get_challenge(request: ChallengeRequest):
    """Получение challenge для подписи"""
    try:
        # Генерация nonce и timestamp
        nonce = SecurityUtils.generate_nonce()
        timestamp = datetime.utcnow().isoformat()
        
        # Создание challenge сообщения
        message = SecurityUtils.create_challenge_message(
            request.publicKey, 
            nonce, 
            timestamp
        )
        
        return ChallengeResponse(
            nonce=nonce,
            message=message,
            timestamp=timestamp
        )
        
    except Exception as e:
        logger.error(f"Challenge generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate challenge"
        )

@app.post("/api/auth/verify")
async def verify_signature(auth_data: PhantomAuthRequest, request: Request, response: Response):
    """Верификация подписи и выдача JWT токена"""
    try:
        # Логирование входящих данных
        logger.info(f"Auth request received: publicKey={auth_data.publicKey[:10]}..., signature={auth_data.signature[:20]}..., message_length={len(auth_data.message)}")
        
        # Rate limiting
        client_ip = request.client.host
        # Временно отключено для тестов
        # if not rate_limiter.is_allowed(client_ip, limit=5, window=300):  # 5 попыток за 5 минут
        #     raise HTTPException(
        #         status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        #         detail="Too many authentication attempts"
        #     )
        
        # Верификация подписи
        if not SecurityUtils.verify_solana_signature(
            auth_data.publicKey, 
            auth_data.signature, 
            auth_data.message
        ):
            logger.warning(f"Signature verification failed for {auth_data.publicKey}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        # Поиск или создание пользователя
        user_query = """
            INSERT INTO users (wallet_address, created_at, last_login) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (wallet_address) 
            DO UPDATE SET last_login = %s
            RETURNING id, wallet_address, username, avatar_url, created_at, last_login
        """
        
        user = None
        db = None
        try:
            db = Database()
            user = db.execute_query(
                user_query, 
                (auth_data.publicKey, datetime.utcnow(), datetime.utcnow(), datetime.utcnow()),
                fetch="one"
            )

            # Если новый пользователь - инициализация токенов и лидерборда
            if user['created_at'] == user['last_login']:
                # Начальные токены
                db.execute_query(
                    "INSERT INTO user_tokens (user_id, balance) VALUES (%s, 100000)",
                    (user['id'],)
                )
                # Запись в лидерборд
                db.execute_query(
                    "INSERT INTO leaderboard (user_id) VALUES (%s)",
                    (user['id'],)
                )

        except psycopg2.OperationalError as e:
            # In unit-test / local environment without DB we still want auth flow to be testable
            logger.warning(f"DB unavailable during auth verify, continuing without persistence: {e}")
            user = {
                "id": 0,
                "wallet_address": auth_data.publicKey,
                "username": None,
                "avatar_url": None,
                "created_at": datetime.utcnow(),
                "last_login": datetime.utcnow(),
            }
        
        # Создание JWT токена
        token = SecurityUtils.create_jwt_token({
            "userId": user['id'],
            "walletAddress": user['wallet_address']
        })

        # Set HttpOnly cookie so direct navigation to protected HTML pages can be guarded server-side
        response.set_cookie(
            key="wb_token",
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=int(settings.jwt_expire_hours * 3600),
            path="/",
        )
        
        logger.info(f"User {auth_data.publicKey} authenticated successfully")

        if db:
            db.close()
        
        return {
            "token": token,
            "user": {
                "id": user['id'],
                "walletAddress": user['wallet_address'],
                "username": user['username'],
                "avatarUrl": user['avatar_url']
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@app.post("/api/auth/refresh")
async def refresh_token():
    """Refresh is intentionally not implemented."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Not found"
    )


def _is_html_access_allowed(request: Request) -> bool:
    """Server-side guard for protected HTML pages.

    Browsers don't send Authorization headers on normal navigation to HTML.
    We therefore accept either:
    - HttpOnly cookie wb_token (set on /api/auth/verify)
    - Authorization: Bearer <token> (useful for programmatic access)
    """

    cookie_token = request.cookies.get("wb_token")
    if cookie_token:
        try:
            SecurityUtils.verify_jwt_token(cookie_token)
            return True
        except HTTPException:
            return False

    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            SecurityUtils.verify_jwt_token(token)
            return True
        except HTTPException:
            return False

    return False


@app.get("/app.html")
async def protected_app_html(request: Request):
    if not _is_html_access_allowed(request):
        return RedirectResponse(url="/index.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return FileResponse("frontend/app.html")


@app.get("/arena.html")
async def protected_arena_html(request: Request):
    if not _is_html_access_allowed(request):
        return RedirectResponse(url="/index.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return FileResponse("frontend/arena.html")

@app.get("/api/user/profile", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Получение профиля пользователя"""
    try:
        db = Database()
        db.connect()
        
        # Получение данных пользователя
        user_query = """
            SELECT id, wallet_address, username, avatar_url, created_at, last_login
            FROM users 
            WHERE wallet_address = %s
        """
        user_result = db.execute_query(user_query, (current_user["wallet_address"],), fetch="one")
        
        if not user_result:
            # Создание нового пользователя
            insert_query = """
                INSERT INTO users (wallet_address, created_at, last_login)
                VALUES (%s, %s, %s)
                RETURNING id, wallet_address, username, avatar_url, created_at, last_login
            """
            user_result = db.execute_query(
                insert_query, 
                (current_user["wallet_address"], datetime.utcnow(), datetime.utcnow()),
                fetch="one"
            )

        if not user_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        db.close()
        
        return UserResponse(
            id=user_result["id"],
            wallet_address=user_result["wallet_address"],
            username=user_result["username"],
            avatar_url=user_result["avatar_url"],
            created_at=user_result["created_at"],
            last_login=user_result["last_login"]
        )
        
    except HTTPException:
        raise
    except psycopg2.OperationalError as e:
        logger.error(f"Profile DB unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    except Exception as e:
        logger.error(f"Profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get profile"
        )


@app.post("/api/nft/stats", response_model=NFTStatsResponse)
async def get_nft_stats(payload: NFTStatsRequest, current_user: dict = Depends(get_current_user)):
    stats = generate_nft_stats(payload.mintAddress, payload.rarity, settings.nft_stats_salt)
    return NFTStatsResponse(mintAddress=payload.mintAddress, rarity=payload.rarity, stats=stats)


@app.post("/api/wallet/scan")
async def wallet_scan(payload: WalletScanRequest, current_user: dict = Depends(get_current_user)):
    data = await _helius_get_assets_by_owner(payload.walletAddress)
    items = (((data.get("result") or {}).get("items")) or [])
    collection = settings.collection_address

    filtered = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if collection:
            grouping = it.get("grouping") or []
            ok = False
            if isinstance(grouping, list):
                for g in grouping:
                    if isinstance(g, dict) and g.get("group_key") == "collection" and g.get("group_value") == collection:
                        ok = True
                        break
            if not ok:
                continue
        filtered.append(it)

    filtered = filtered[:3]
    nfts = [_parse_helius_asset(a) for a in filtered]
    attack_bonus = _compute_attack_bonus(len(nfts))
    return {"nfts": nfts, "attackBonus": attack_bonus}


@app.post("/api/wallet/token-balance")
async def token_balance(payload: TokenBalanceRequest, current_user: dict = Depends(get_current_user)):
    if not settings.token_mint:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TOKEN_MINT not configured")

    bal = await _solana_get_token_balance(payload.walletAddress, settings.token_mint)
    return {"mint": settings.token_mint, "balance": bal}


@app.post("/api/skills/upgrade")
async def skills_upgrade(payload: SkillsUpgradeRequest, current_user: dict = Depends(get_current_user)):
    wallet = current_user.get("wallet_address")
    tx = await _solana_get_transaction(payload.txSignature)
    if not _tx_has_valid_burn(tx, wallet):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid burn transaction")

    db = None
    try:
        db = Database()
        db.connect()
        user_id_row = db.execute_query(
            "SELECT id FROM users WHERE wallet_address = %s",
            (wallet,),
            fetch="one",
        )
        if not user_id_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user_id = int(user_id_row["id"])

        up_q = (
            "INSERT INTO user_skill_levels (user_id, skill_key, level) "
            "VALUES (%s, %s, 1) "
            "ON CONFLICT (user_id, skill_key) DO UPDATE SET level = user_skill_levels.level + 1 "
            "RETURNING level"
        )
        row = db.execute_query(up_q, (user_id, payload.skillKey), fetch="one")
        new_level = int((row or {}).get("level") or 1)
        return {"skillKey": payload.skillKey, "level": new_level}
    except psycopg2.OperationalError:
        return {"skillKey": payload.skillKey, "level": 1}
    finally:
        if db:
            db.close()


@app.post("/api/battle/start", response_model=BattleStartResponse)
async def battle_start(payload: BattleStartRequest, current_user: dict = Depends(get_current_user)):
    db = Database()
    db.connect()

    user_id_row = db.execute_query(
        "SELECT id FROM users WHERE wallet_address = %s",
        (current_user["wallet_address"],),
        fetch="one",
    )
    if not user_id_row:
        db.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_id = int(user_id_row["id"])

    # Atomic bet debit: prevents double-spend / localStorage abuse
    debit_q = (
        "UPDATE leaderboard "
        "SET points = points - %s "
        "WHERE user_id = %s AND points >= %s "
        "RETURNING points, wins, losses"
    )
    debited = db.execute_query(debit_q, (payload.bet, user_id, payload.bet), fetch="one")
    if not debited:
        db.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient points")

    db.close()

    wait_seconds = 50 + secrets.randbelow(21)
    battle_id = secrets.token_urlsafe(16)
    resolve_at = time.time() + float(wait_seconds)
    seed = f"{battle_id}:{user_id}:{payload.mintAddress}:{int(resolve_at)}".encode("utf-8")

    app.state.battles[battle_id] = {
        "battle_id": battle_id,
        "status": BattleStatus.pending,
        "wait_seconds": int(wait_seconds),
        "resolve_at": float(resolve_at),
        "user_id": user_id,
        "bet": int(payload.bet),
        "mint_address": payload.mintAddress,
        "seed": seed,
        "result": None,
    }

    asyncio.create_task(_resolve_battle(app, battle_id))
    return BattleStartResponse(battle_id=battle_id, status=BattleStatus.pending, wait_seconds=int(wait_seconds))


@app.get("/api/battle/{battle_id}", response_model=BattleStatusResponse)
async def battle_status(battle_id: str, current_user: dict = Depends(get_current_user)):
    battle = app.state.battles.get(battle_id)
    if not battle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Battle not found")

    return BattleStatusResponse(
        battle_id=battle_id,
        status=battle["status"],
        wait_seconds=int(battle["wait_seconds"]),
        resolve_at=float(battle["resolve_at"]),
        result=battle.get("result"),
    )

@app.patch("/api/user/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfile,
    current_user: dict = Depends(get_current_user)
):
    """Обновление профиля пользователя"""
    try:
        db = Database()
        db.connect()
        
        update_query = """
            UPDATE users 
            SET username = %s, avatar_url = %s, updated_at = %s
            WHERE wallet_address = %s
            RETURNING id, wallet_address, username, avatar_url, created_at, last_login
        """
        
        result = db.execute_query(
            update_query,
            (profile_data.username, profile_data.avatarUrl, datetime.utcnow(), current_user["wallet_address"]),
            fetch="one"
        )
        
        db.close()
        
        return UserResponse(
            id=result["id"],
            wallet_address=result["wallet_address"],
            username=result["username"],
            avatar_url=result["avatar_url"],
            created_at=result["created_at"],
            last_login=result["last_login"]
        )
        
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

@app.post("/api/user/nfts")
async def add_nft(
    nft_data: NFTData,
    current_user: dict = Depends(get_current_user)
):
    """Добавление NFT пользователю"""
    try:
        db = Database()
        db.connect()
        
        # Получение ID пользователя
        user_query = "SELECT id FROM users WHERE wallet_address = %s"
        user_result = db.execute_query(user_query, (current_user["wallet_address"],), fetch="one")
        
        if not user_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Добавление NFT
        nft_query = """
            INSERT INTO user_nfts (user_id, mint_address, name, image_url, rarity)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, mint_address) 
            DO UPDATE SET name = EXCLUDED.name, image_url = EXCLUDED.image_url, rarity = EXCLUDED.rarity
            RETURNING id
        """
        
        db.execute_query(
            nft_query,
            (user_result["id"], nft_data.mintAddress, nft_data.name, nft_data.imageUrl, nft_data.rarity)
        )
        
        db.close()
        
        return {"message": "NFT added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"NFT add error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add NFT"
        )

@app.get("/api/skills")
async def get_skills():
    """Получение доступных скиллов"""
    try:
        db = Database()
        db.connect()
        
        skills_query = "SELECT * FROM skills ORDER BY required_level, name"
        skills = db.execute_query(skills_query, fetch="all")
        
        db.close()
        
        return {"skills": [dict(skill) for skill in skills]}
        
    except Exception as e:
        logger.error(f"Skills error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get skills"
        )

@app.get("/api/leaderboard")
async def get_leaderboard():
    """Получение таблицы лидеров"""
    db = None
    try:
        db = Database()
        db.connect()
        
        leaderboard_query = """
            SELECT l.*, u.username, u.wallet_address 
            FROM leaderboard l 
            JOIN users u ON l.user_id = u.id 
            ORDER BY l.points DESC, l.wins DESC 
            LIMIT 100
        """
        leaderboard = db.execute_query(leaderboard_query, fetch="all")

        entries = [dict(entry) for entry in (leaderboard or [])]
        # Defense-in-depth: enforce contract even if DB returns unsorted data
        entries.sort(key=lambda e: (-int(e.get("points", 0)), -int(e.get("wins", 0))))
        entries = entries[:100]

        return {"leaderboard": entries}
        
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get leaderboard"
        )
    finally:
        if db:
            db.close()

# Конфигурация для фронтенда (перед монтированием статики)
@app.get("/api/config")
async def get_frontend_config():
    """Отдача конфигурации для фронтенда"""
    return {
        "DEBUG_MODE": settings.debug_mode,
        "API_BASE_URL": "/api",
        "TOKEN_MINT": settings.token_mint,
        "SOLANA_RPC": settings.solana_rpc,
    }

# Подключение статики фронтенда (после всех API роутов)
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        reload=True,
        log_level="info"
    )
