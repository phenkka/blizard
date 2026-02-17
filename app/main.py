"""
WORLDBINDER Backend API
FastAPI сервер с безопасной аутентификацией Phantom
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
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

# Настройки
class Settings(BaseSettings):
    # База данных
    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "blizard"
    db_user: str = "admin"
    db_password: str = "12345"
    
    # JWT
    jwt_secret: str = "your_jwt_secret_key_change_in_production_make_it_long_and_random"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    
    # Безопасность
    frontend_url: str = "http://localhost:3000"
    rate_limit_requests: int = 100
    rate_limit_window: int = 900  # 15 минут
    
    # Solana
    solana_cluster: str = "mainnet-beta"
    
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
    publicKey: str = Field(..., min_length=44, max_length=44)

class ChallengeResponse(BaseModel):
    """Ответ с challenge для подписи"""
    nonce: str
    message: str
    timestamp: str

class UserProfile(BaseModel):
    """Профиль пользователя"""
    username: Optional[str] = Field(None, min_length=2, max_length=20, pattern=r'^[a-zA-Z0-9_-]+$')
    avatarUrl: Optional[str] = Field(None, max_length=5000000)
    
    @validator('username')
    def validate_username(cls, v):
        if v is None:
            return v
        # Только буквы, цифры, подчеркивание и дефис
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, underscores and hyphens')
        # Не может начинаться с цифры или спецсимвола
        if not v[0].isalpha():
            raise ValueError('Username must start with a letter')
        return v
    
    @validator('avatarUrl')
    def validate_avatar(cls, v):
        if v is None:
            return v
        # Проверка что это base64 изображение
        if not v.startswith('data:image/'):
            raise ValueError('Avatar must be a valid base64 image')
        # Проверка размера (примерно 2МБ после base64 = ~2.7МБ в base64)
        if len(v) > 2800000:  # ~2MB image = ~2.8MB base64
            raise ValueError('Avatar size exceeds 2MB limit')
        return v

class NFTData(BaseModel):
    """Данные NFT"""
    mintAddress: str = Field(..., min_length=44, max_length=44)
    name: str = Field(..., min_length=1, max_length=200)
    imageUrl: str = Field(..., max_length=500)
    rarity: str = Field("Common", pattern="^(Common|Rare|Epic|Legendary)$")

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

# База данных
class Database:
    def __init__(self):
        self.pool = None
        self.connect()
    
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
            self.pool.rollback()
            logger.error(f"Database query error: {e}")
            raise
    
    def __del__(self):
        if self.pool:
            self.pool.close()
    
    def close(self):
        if self.pool:
            self.pool.close()

db = Database()

# Утилиты безопасности
class SecurityUtils:
    @staticmethod
    def create_jwt_token(data: dict) -> str:
        """Создание JWT токена"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
        to_encode.update({"exp": expire})
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
                detail="Token expired"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    @staticmethod
    def verify_solana_signature(public_key: str, signature: str, message: str) -> bool:
        """Верификация подписи Solana"""
        try:
            logger.info(f"Verifying signature: publicKey={public_key[:10]}..., signature={signature[:20]}..., message_length={len(message)}")
            
            # Декодирование из base64 во временный вариант
            import base64
            sig_bytes = base64.b64decode(signature)
            
            # Декодирование публичного ключа
            pk_bytes = base58.b58decode(public_key)
            message_bytes = message.encode('utf-8')
            
            logger.info(f"Decoded: pk_len={len(pk_bytes)}, sig_len={len(sig_bytes)}, msg_len={len(message_bytes)}")
            
            # Проверка длины
            if len(pk_bytes) != 32 or len(sig_bytes) != 64:
                logger.warning(f"Invalid lengths: pk={len(pk_bytes)}, sig={len(sig_bytes)}")
                return False
            
            # Создание VerifyKey из публичного ключа
            verify_key = VerifyKey(pk_bytes)
            
            # Верификация подписи
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
        return f"Sign this message to authenticate with WORLDBINDER.\n\nPublic Key: {public_key}\nNonce: {nonce}\nTimestamp: {timestamp}"

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
    client_ip = request.client.host
    
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests"}
        )
    
    response = await call_next(request)
    return response

# JWT Bearer
security = HTTPBearer()

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

# Обработчик ошибок валидации
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": exc.errors()
        }
    )

# Middleware
app.middleware("http")(rate_limit_middleware)

# CORS - разрешить запросы с фронтенда
allowed_origins = [
    settings.frontend_url,
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Зависимости
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Получение текущего пользователя из JWT токена"""
    token = credentials.credentials
    payload = SecurityUtils.verify_jwt_token(token)
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
async def verify_signature(auth_data: PhantomAuthRequest, request: Request):
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
        
        # Создание JWT токена
        token = SecurityUtils.create_jwt_token({
            "userId": user['id'],
            "walletAddress": user['wallet_address']
        })
        
        logger.info(f"User {auth_data.publicKey} authenticated successfully")
        
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
        user_result = db.execute_query(user_query, (current_user["walletAddress"],), fetch="one")
        
        if not user_result:
            # Создание нового пользователя
            insert_query = """
                INSERT INTO users (wallet_address, created_at, last_login)
                VALUES (%s, %s, %s)
                RETURNING id, wallet_address, username, avatar_url, created_at, last_login
            """
            user_result = db.execute_query(
                insert_query, 
                (current_user["walletAddress"], datetime.utcnow(), datetime.utcnow()),
                fetch="one"
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
        
    except Exception as e:
        logger.error(f"Profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get profile"
        )

@app.patch("/api/user/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfile,
    current_user: dict = Depends(get_current_user)
):
    """Обновление профиля пользователя"""
    try:
        logger.info(f"Updating profile for user: {current_user['walletAddress']}")
        
        db = Database()
        db.connect()
        
        # Проверка на уникальность имени пользователя
        if profile_data.username:
            check_query = """
                SELECT id FROM users 
                WHERE username = %s AND wallet_address != %s
            """
            existing = db.execute_query(
                check_query,
                (profile_data.username, current_user["walletAddress"]),
                fetch="one"
            )
            
            if existing:
                db.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
        
        update_query = """
            UPDATE users 
            SET username = %s, avatar_url = %s, updated_at = %s
            WHERE wallet_address = %s
            RETURNING id, wallet_address, username, avatar_url, created_at, last_login
        """
        
        result = db.execute_query(
            update_query,
            (profile_data.username, profile_data.avatarUrl, datetime.utcnow(), current_user["walletAddress"]),
            fetch="one"
        )
        
        if not result:
            db.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        db.close()
        
        logger.info(f"Profile updated successfully for user: {current_user['walletAddress']}")
        
        return UserResponse(
            id=result["id"],
            wallet_address=result["wallet_address"],
            username=result["username"],
            avatar_url=result["avatar_url"],
            created_at=result["created_at"],
            last_login=result["last_login"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
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
        user_result = db.execute_query(user_query, (current_user["walletAddress"],), fetch="one")
        
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
        
        db.close()
        
        return {"leaderboard": [dict(entry) for entry in leaderboard]}
        
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get leaderboard"
        )

# Конфигурация для фронтенда (перед монтированием статики)
@app.get("/api/config")
async def get_frontend_config():
    """Отдача конфигурации для фронтенда"""
    return {
        "DEBUG_MODE": settings.debug_mode,
        "API_BASE_URL": "/api"
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
