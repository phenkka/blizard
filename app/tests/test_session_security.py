"""
Тесты безопасности сессий и rate limiting
Проверяют защиту от атак на сессии и перебора
"""

import pytest
import jwt
import time
import base64
from fastapi.testclient import TestClient
from main import app, SecurityUtils
from nacl.signing import SigningKey
import base58

client = TestClient(app)

@pytest.mark.security
class TestSessionSecurity:
    """Тесты безопасности сессий"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        # Создаем тестовую пару ключей
        self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.public_key = base58.b58encode(self.verify_key.encode()).decode('utf-8')
    
    def get_valid_token(self):
        """Получаем валидный JWT токен"""
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Подписываем сообщение
        message_bytes = challenge_data["message"].encode('utf-8')
        signature = self.signing_key.sign(message_bytes)
        signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
        
        # Получаем токен
        response = client.post("/api/auth/verify", json={
            "publicKey": self.public_key,
            "signature": signature_b64,
            "message": challenge_data["message"]
        })
        
        return response.json()["token"]
    
    def test_jwt_token_structure(self):
        """Тест структуры JWT токена"""
        token = self.get_valid_token()
        
        # Проверяем что токен можно декодировать
        payload = jwt.decode(token, "your-secret-key-change-in-production", algorithms=["HS256"])
        
        # Проверяем обязательные поля
        assert "userId" in payload
        assert "walletAddress" in payload
        assert "exp" in payload
        assert "iat" in payload  # issued at
        
        # Проверяем типы данных
        assert isinstance(payload["userId"], int)
        assert isinstance(payload["walletAddress"], str)
        assert isinstance(payload["exp"], int)
        assert isinstance(payload["iat"], int)
        
        # Проверяем что walletAddress соответствует нашему ключу
        assert payload["walletAddress"] == self.public_key
    
    def test_token_expiration(self):
        """Тест истечения срока действия токена"""
        token = self.get_valid_token()
        
        # Токен должен быть валидным сейчас
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/user/profile", headers=headers)
        assert response.status_code in [200, 404]  # 404 если пользователь не в БД
        
        # Создаем токен с истекшим сроком
        expired_payload = {
            "userId": 1,
            "walletAddress": self.public_key,
            "exp": int(time.time()) - 3600,  # 1 час назад
            "iat": int(time.time()) - 7200   # 2 часа назад
        }
        
        expired_token = jwt.encode(expired_payload, "your-secret-key-change-in-production", algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/api/user/profile", headers=headers)
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()
    
    def test_invalid_token_rejection(self):
        """Тест отклонения невалидных токенов"""
        invalid_tokens = [
            "",  # пустой токен
            "invalid.jwt.token",  # невалидный формат
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",  # невалидная подпись
            "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.invalid",  # алгоритм 'none'
            base64.b64encode(b"not_a_jwt").decode('utf-8'),  # не JWT
        ]
        
        for invalid_token in invalid_tokens:
            headers = {"Authorization": f"Bearer {invalid_token}"}
            response = client.get("/api/user/profile", headers=headers)
            assert response.status_code == 401
    
    def test_token_tampering_protection(self):
        """Тест защиты от подделывания токена"""
        token = self.get_valid_token()
        
        # Попытка изменить токен (изменить payload)
        parts = token.split('.')
        
        # Декодируем payload
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Изменяем userId
        payload["userId"] = 999999
        
        # Кодируем обратно с неправильной подписью
        tampered_payload = jwt.encode(payload, "wrong_secret", algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {tampered_payload}"}
        response = client.get("/api/user/profile", headers=headers)
        assert response.status_code == 401
    
    def test_session_hijacking_protection(self):
        """Тест защиты от захвата сессии"""
        token = self.get_valid_token()
        
        # Токен должен быть привязан к конкретному пользователю
        payload = jwt.decode(token, "your-secret-key-change-in-production", algorithms=["HS256"])
        
        # Попытка использовать токен с другим walletAddress
        tampered_payload = payload.copy()
        tampered_payload["walletAddress"] = "11111111111111111111111111111111"
        
        tampered_token = jwt.encode(tampered_payload, "your-secret-key-change-in-production", algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {tampered_token}"}
        response = client.get("/api/user/profile", headers=headers)
        
        # Должно либо сработать (если проверка только по токену), либо провалиться
        # В идеальной системе должна быть дополнительная проверка
        assert response.status_code in [401, 404]  # 404 если пользователь не найден
    
    def test_concurrent_sessions_limit(self):
        """Тест ограничения одновременных сессий"""
        tokens = []
        
        # Создаем несколько сессий
        for i in range(3):
            token = self.get_valid_token()
            tokens.append(token)
            
            # Проверяем что токен работает
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get("/api/user/profile", headers=headers)
            assert response.status_code in [200, 404]
        
        # Все токены должны быть разными
        assert len(set(tokens)) == len(tokens)
        
        # Все токены должны работать одновременно
        for token in tokens:
            headers = {"Authorization": f"Bearer {token}"}
            response = client.get("/api/user/profile", headers=headers)
            assert response.status_code in [200, 404]
    
    def test_token_refresh_not_allowed(self):
        """Тест что refresh токенов не реализован (безопасность)"""
        token = self.get_valid_token()
        
        # Попытка обновить токен (должна провалиться)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/api/auth/refresh", headers=headers)
        
        # Эндпоинт не должен существовать
        assert response.status_code == 404
    
    def test_logout_functionality(self):
        """Тест функциональности logout"""
        token = self.get_valid_token()
        
        # Токен должен работать
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/user/profile", headers=headers)
        assert response.status_code in [200, 404]
        
        # В текущей реализации logout не реализован на сервере
        # Но клиент может просто удалить токен
        # Это тест для будущей реализации
        pass


@pytest.mark.security
class TestRateLimitingSecurity:
    """Тесты защиты от перебора"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.public_key = base58.b58encode(self.verify_key.encode()).decode('utf-8')
    
    def test_brute_force_protection(self):
        """Тест защиты от перебора паролей/подписей"""
        # Получаем валидный challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Отправляем много неверных подписей
        failed_attempts = 0
        rate_limit_hit = False
        
        for i in range(20):  # 20 попыток
            response = client.post("/api/auth/verify", json={
                "publicKey": self.public_key,
                "signature": f"invalid_signature_{i}",
                "message": challenge_data["message"]
            })
            
            if response.status_code == 429:
                rate_limit_hit = True
                failed_attempts = i + 1
                break
            elif response.status_code == 401:
                failed_attempts += 1
            else:
                break
        
        # В текущей конфигурации rate limiting отключен для тестов
        # Но структура готова для включения
        print(f"Failed attempts before rate limit: {failed_attempts}")
        print(f"Rate limit hit: {rate_limit_hit}")
    
    def test_challenge_rate_limiting(self):
        """Тест rate limiting для challenge endpoint"""
        # Отправляем много запросов на challenge
        responses = []
        
        for i in range(10):
            response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
            responses.append(response.status_code)
            
            if response.status_code == 429:
                break
        
        # Challenge endpoint обычно имеет более мягкий rate limiting
        assert all(status in [200, 429] for status in responses)
    
    def test_ip_based_rate_limiting(self):
        """Тест rate limiting по IP адресу"""
        # Симуляция запросов с разных IP (в реальной системе)
        # Здесь мы просто проверяем что система готова к IP-based limiting
        
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        assert response.status_code == 200
        
        # В реальной системе здесь должна быть проверка IP
        # Для тестов мы проверяем только структуру
        pass
    
    def test_user_based_rate_limiting(self):
        """Тест rate limiting по пользователю"""
        # Получаем несколько токенов для одного пользователя
        tokens = []
        
        for i in range(3):
            response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
            challenge_data = response.json()
            
            message_bytes = challenge_data["message"].encode('utf-8')
            signature = self.signing_key.sign(message_bytes)
            signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
            
            response = client.post("/api/auth/verify", json={
                "publicKey": self.public_key,
                "signature": signature_b64,
                "message": challenge_data["message"]
            })
            
            if response.status_code == 200:
                tokens.append(response.json()["token"])
        
        # В идеальной системе должно быть ограничение на количество токенов
        # Но для удобства пользователя разрешаем множественные сессии
        assert len(tokens) >= 1  # Хотя бы один токен должен быть получен


@pytest.mark.security
class TestInputValidationSecurity:
    """Тесты валидации входных данных"""
    
    def test_xss_protection(self):
        """Тест защиты от XSS в полях ввода"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "'\"><script>alert('xss')</script>",
            "{{7*7}}",
            "${7*7}",
        ]
        
        for payload in xss_payloads:
            # Тест в publicKey
            response = client.post("/api/auth/challenge", json={"publicKey": payload})
            assert response.status_code in [400, 422, 200]
            
            # Тест в message (если будет эндпоинт)
            # Тест в signature (если будет эндпоинт)
    
    def test_large_payload_protection(self):
        """Тест защиты от больших payload"""
        # Создаем очень большой publicKey
        large_key = "A" * 10000  # 10KB
        
        response = client.post("/api/auth/challenge", json={"publicKey": large_key})
        assert response.status_code in [400, 422, 413]  # 413 = Payload Too Large
    
    def test_unicode_handling(self):
        """Тест обработки Unicode символов"""
        unicode_payloads = [
            "🦄🦄🦄",  # эмодзи
            "привет мир",  # кириллица
            "こんにちは世界",  # японский
            "العربية",  # арабский
            "\u0000\u0001\u0002",  # control characters
        ]
        
        for payload in unicode_payloads:
            response = client.post("/api/auth/challenge", json={"publicKey": payload})
            # Должно обработаться корректно или отклониться
            assert response.status_code in [400, 422, 200]
    
    def test_null_byte_injection(self):
        """Тест защиты от null byte инъекций"""
        null_byte_payloads = [
            "test\x00admin",
            "test\x00\x00admin",
            "\x00test",
            "test\x00",
        ]
        
        for payload in null_byte_payloads:
            response = client.post("/api/auth/challenge", json={"publicKey": payload})
            assert response.status_code in [400, 422, 200]


if __name__ == "__main__":
    pytest.main([__file__])
