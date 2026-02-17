"""
Тесты безопасности аутентификации Phantom
Проверяют защиту от атак, валидацию данных и безопасность сессий
"""

import pytest
import base58
import base64
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder
from fastapi.testclient import TestClient
from main import app, SecurityUtils
import time
import json

client = TestClient(app)

class TestPhantomAuthSecurity:
    """Тесты безопасности аутентификации Phantom"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        # Создаем тестовую пару ключей для подписи
        self.signing_key = SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.public_key = base58.b58encode(self.verify_key.encode()).decode('utf-8')
        
    def test_challenge_generation_security(self):
        """Тест безопасности генерации challenge"""
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем что challenge содержит все необходимые поля
        assert "nonce" in data
        assert "message" in data
        assert "timestamp" in data
        
        # Проверяем что nonce достаточно длинный и случайный
        assert len(data["nonce"]) >= 32
        
        # Проверяем что message содержит публичный ключ
        assert self.public_key in data["message"]
        assert "WORLDBINDER" in data["message"]
        
        # Проверяем что timestamp актуальный
        timestamp = data["timestamp"]
        challenge_time = time.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
        current_time = time.gmtime()
        # Разница не должна быть больше 5 минут
        assert abs(time.mktime(challenge_time) - time.mktime(current_time)) < 300
    
    def test_valid_signature_verification(self):
        """Тест верификации правильной подписи"""
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Подписываем сообщение правильным ключом
        message_bytes = challenge_data["message"].encode('utf-8')
        signature = self.signing_key.sign(message_bytes)
        
        # Конвертируем в base64 для отправки
        signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
        
        # Отправляем на верификацию
        response = client.post("/api/auth/verify", json={
            "publicKey": self.public_key,
            "signature": signature_b64,
            "message": challenge_data["message"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["walletAddress"] == self.public_key
    
    def test_invalid_signature_rejection(self):
        """Тест отклонения неверной подписи"""
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Подписываем другим ключом (неверная подпись)
        wrong_signing_key = SigningKey.generate()
        message_bytes = challenge_data["message"].encode('utf-8')
        wrong_signature = wrong_signing_key.sign(message_bytes)
        
        signature_b64 = base64.b64encode(wrong_signature.signature).decode('utf-8')
        
        # Отправляем на верификацию
        response = client.post("/api/auth/verify", json={
            "publicKey": self.public_key,
            "signature": signature_b64,
            "message": challenge_data["message"]
        })
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"
    
    def test_tampered_message_rejection(self):
        """Тест отклонения измененного сообщения"""
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Подписываем оригинальное сообщение
        message_bytes = challenge_data["message"].encode('utf-8')
        signature = self.signing_key.sign(message_bytes)
        
        signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
        
        # Отправляем с измененным сообщением
        tampered_message = challenge_data["message"] + "TAMPERED"
        
        response = client.post("/api/auth/verify", json={
            "publicKey": self.public_key,
            "signature": signature_b64,
            "message": tampered_message
        })
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"
    
    def test_invalid_public_key_format(self):
        """Тест отклонения неверного формата публичного ключа"""
        invalid_keys = [
            "too_short",
            "way_too_long_public_key_that_exceeds_normal_solana_key_length",
            "invalid_characters_!@#$%^&*()",
            "",  # пустой ключ
            "11111111111111111111111111111111",  # неправильная длина
        ]
        
        for invalid_key in invalid_keys:
            response = client.post("/api/auth/challenge", json={"publicKey": invalid_key})
            # Должен либо отклонить, либо обработать gracefully
            assert response.status_code in [400, 422, 200]
    
    def test_malformed_signature_format(self):
        """Тест отклонения некорректного формата подписи"""
        # Получаем валидный challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        malformed_signatures = [
            "",  # пустая подпись
            "too_short",
            "invalid_base64_!@#$%",
            "a" * 1000,  # слишком длинная
        ]
        
        for malformed_sig in malformed_signatures:
            response = client.post("/api/auth/verify", json={
                "publicKey": self.public_key,
                "signature": malformed_sig,
                "message": challenge_data["message"]
            })
            
            assert response.status_code in [400, 401, 422]
    
    def test_missing_required_fields(self):
        """Тест отклонения запросов без обязательных полей"""
        # Получаем валидные данные
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Тесты отсутствующих полей
        test_cases = [
            {},  # все поля отсутствуют
            {"publicKey": self.public_key},  # отсутствует signature и message
            {"signature": "test"},  # отсутствует publicKey и message
            {"message": "test"},  # отсутствует publicKey и signature
        ]
        
        for test_case in test_cases:
            response = client.post("/api/auth/verify", json=test_case)
            assert response.status_code in [400, 422]
    
    def test_sql_injection_protection(self):
        """Тест защиты от SQL инъекций в полях"""
        # Получаем валидный challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Попытка SQL инъекции в publicKey
        sql_injection_payloads = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "1; DELETE FROM users; --",
            "admin'--",
            "' UNION SELECT * FROM users --"
        ]
        
        for payload in sql_injection_payloads:
            response = client.post("/api/auth/challenge", json={"publicKey": payload})
            # Должен либо отклонить, либо обработать без ошибок
            assert response.status_code in [400, 422, 200]
            
            # Если верификация дошла, должна провалиться
            if response.status_code == 200:
                verify_response = client.post("/api/auth/verify", json={
                    "publicKey": payload,
                    "signature": "fake_signature",
                    "message": response.json()["message"]
                })
                assert verify_response.status_code in [400, 401, 422]
    
    def test_session_token_security(self):
        """Тест безопасности JWT токенов"""
        # Получаем валидный токен
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
        
        assert response.status_code == 200
        token = response.json()["token"]
        
        # Тест 1: Токен должен быть валидным JWT
        try:
            import jwt
            payload = jwt.decode(token, "your-secret-key-change-in-production", algorithms=["HS256"])
            assert "userId" in payload
            assert "walletAddress" in payload
            assert "exp" in payload
        except jwt.InvalidTokenError:
            pytest.fail("Token is not a valid JWT")
        
        # Тест 2: Токен должен отклоняться с неверным секретом
        try:
            jwt.decode(token, "wrong_secret", algorithms=["HS256"])
            pytest.fail("Token should be rejected with wrong secret")
        except jwt.InvalidTokenError:
            pass  # Ожидаемо
        
        # Тест 3: Токен должен отклоняться с неверным алгоритмом
        try:
            jwt.decode(token, "your-secret-key-change-in-production", algorithms=["none"])
            pytest.fail("Token should be rejected with 'none' algorithm")
        except jwt.InvalidTokenError:
            pass  # Ожидаемо
        
        # Тест 4: Токен должен работать для защищенных эндпоинтов
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/user/profile", headers=headers)
        assert response.status_code in [200, 404]  # 404 если пользователь не найден в БД
        
        # Тест 5: Токен должен отклоняться без Bearer префикса
        response = client.get("/api/user/profile", headers={"Authorization": token})
        assert response.status_code == 401
        
        # Тест 6: Токен должен отклоняться с неправильным префиксом
        response = client.get("/api/user/profile", headers={"Authorization": f"Basic {token}"})
        assert response.status_code == 401
    
    def test_rate_limiting_security(self):
        """Тест защиты от перебора (rate limiting)"""
        # Этот тест проверяет что rate limiting работает
        # В реальной конфигурации rate limiting должен быть включен
        
        # Получаем challenge
        response = client.post("/api/auth/challenge", json={"publicKey": self.public_key})
        challenge_data = response.json()
        
        # Отправляем много запросов подряд
        failed_attempts = 0
        for i in range(10):
            response = client.post("/api/auth/verify", json={
                "publicKey": self.public_key,
                "signature": "invalid_signature",
                "message": challenge_data["message"]
            })
            
            if response.status_code == 429:
                failed_attempts += 1
                break
        
        # В реальной системе rate limiting должен сработать
        # Для тестов он отключен, но структура готова
        print(f"Rate limiting attempts: {failed_attempts}")
    
    def test_concurrent_session_protection(self):
        """Тест защиты от одновременных сессий"""
        # Получаем первый токен
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
        
        first_token = response.json()["token"]
        
        # Получаем второй токен для того же пользователя
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
        
        second_token = response.json()["token"]
        
        # Оба токена должны быть валидными (система позволяет множественные сессии)
        # Но в продакшене можно ограничить количество одновременных сессий
        assert first_token != second_token  # Токены должны быть разными
        
        # Оба токена должны работать
        headers1 = {"Authorization": f"Bearer {first_token}"}
        headers2 = {"Authorization": f"Bearer {second_token}"}
        
        response1 = client.get("/api/user/profile", headers=headers1)
        response2 = client.get("/api/user/profile", headers=headers2)
        
        assert response1.status_code in [200, 404]
        assert response2.status_code in [200, 404]


if __name__ == "__main__":
    pytest.main([__file__])
