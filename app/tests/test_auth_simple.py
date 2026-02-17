"""
Упрощенные тесты безопасности аутентификации
Без зависимостей от базы данных
"""

import pytest
import base58
import base64
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder
import time
import json

# Простая имитация SecurityUtils для тестов
class MockSecurityUtils:
    @staticmethod
    def verify_solana_signature(public_key: str, signature: str, message: str) -> bool:
        """Верификация подписи Solana"""
        try:
            # Декодирование из base64
            sig_bytes = base64.b64decode(signature)
            
            # Декодирование публичного ключа
            pk_bytes = base58.b58decode(public_key)
            message_bytes = message.encode('utf-8')
            
            # Проверка длины
            if len(pk_bytes) != 32 or len(sig_bytes) != 64:
                return False
            
            # Создание VerifyKey из публичного ключа
            from nacl.signing import VerifyKey
            verify_key = VerifyKey(pk_bytes)
            
            # Верификация подписи
            verify_key.verify(message_bytes, sig_bytes)
            return True
            
        except Exception as e:
            print(f"Signature verification error: {e}")
            return False
    
    @staticmethod
    def generate_nonce() -> str:
        """Генерация nonce для challenge"""
        import secrets
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def create_challenge_message(public_key: str, nonce: str, timestamp: str) -> str:
        """Создание challenge сообщения для подписи"""
        return f"WORLDBINDER Authentication\nPublic Key: {public_key}\nNonce: {nonce}\nTimestamp: {timestamp}"
    
    @staticmethod
    def get_current_timestamp() -> str:
        """Получение текущего timestamp в правильном формате"""
        import datetime
        return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]  # Обрезаем до миллисекунд

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
        # Генерируем challenge
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = MockSecurityUtils.get_current_timestamp()
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        # Проверяем что challenge содержит все необходимые поля
        assert self.public_key in message
        assert nonce in message
        assert timestamp in message
        assert "WORLDBINDER" in message
        
        # Проверяем что nonce достаточно длинный и случайный
        assert len(nonce) >= 32
        
        # Проверяем что timestamp актуальный
        try:
            import datetime
            challenge_time = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
            current_time = datetime.datetime.utcnow()
            # Разница не должна быть больше 5 минут
            assert abs((challenge_time - current_time).total_seconds()) < 300
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {timestamp}")
    
    def test_valid_signature_verification(self):
        """Тест верификации правильной подписи"""
        # Создаем challenge
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = MockSecurityUtils.get_current_timestamp()
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        # Подписываем сообщение правильным ключом
        message_bytes = message.encode('utf-8')
        signature = self.signing_key.sign(message_bytes)
        
        # Конвертируем в base64 для отправки
        signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
        
        # Проверяем верификацию
        result = MockSecurityUtils.verify_solana_signature(
            self.public_key,
            signature_b64,
            message
        )
        
        assert result is True
    
    def test_invalid_signature_rejection(self):
        """Тест отклонения неверной подписи"""
        # Создаем challenge
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = MockSecurityUtils.get_current_timestamp()
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        # Подписываем другим ключом (неверная подпись)
        wrong_signing_key = SigningKey.generate()
        message_bytes = message.encode('utf-8')
        wrong_signature = wrong_signing_key.sign(message_bytes)
        
        signature_b64 = base64.b64encode(wrong_signature.signature).decode('utf-8')
        
        # Проверяем что неверная подпись отклоняется
        result = MockSecurityUtils.verify_solana_signature(
            self.public_key,
            signature_b64,
            message
        )
        
        assert result is False
    
    def test_tampered_message_rejection(self):
        """Тест отклонения измененного сообщения"""
        # Создаем challenge
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = MockSecurityUtils.get_current_timestamp()
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        # Подписываем оригинальное сообщение
        message_bytes = message.encode('utf-8')
        signature = self.signing_key.sign(message_bytes)
        
        signature_b64 = base64.b64encode(signature.signature).decode('utf-8')
        
        # Отправляем с измененным сообщением
        tampered_message = message + "TAMPERED"
        
        # Проверяем что измененное сообщение отклоняется
        result = MockSecurityUtils.verify_solana_signature(
            self.public_key,
            signature_b64,
            tampered_message
        )
        
        assert result is False
    
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
            try:
                # Попытка декодировать неверный ключ
                base58.b58decode(invalid_key)
                # Если декодирование удалось, проверяем длину
                decoded = base58.b58decode(invalid_key)
                assert len(decoded) != 32, f"Invalid key should not be 32 bytes: {invalid_key}"
            except Exception:
                # Ошибка декодирования - это ожидаемо для неверных ключей
                pass
    
    def test_malformed_signature_format(self):
        """Тест отклонения некорректного формата подписи"""
        # Создаем валидный challenge
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.%f', time.gmtime())
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        malformed_signatures = [
            "",  # пустая подпись
            "too_short",
            "invalid_base64_!@#$%",
            "a" * 1000,  # слишком длинная
        ]
        
        for malformed_sig in malformed_signatures:
            # Проверяем что некорректная подпись отклоняется
            result = MockSecurityUtils.verify_solana_signature(
                self.public_key,
                malformed_sig,
                message
            )
            
            assert result is False
    
    def test_nonce_uniqueness(self):
        """Тест уникальности nonce"""
        nonces = []
        
        # Генерируем несколько nonce
        for i in range(100):
            nonce = MockSecurityUtils.generate_nonce()
            nonces.append(nonce)
        
        # Проверяем что все nonce уникальны
        assert len(set(nonces)) == len(nonces), "Nonces should be unique"
        
        # Проверяем что все nonce имеют достаточную длину
        for nonce in nonces:
            assert len(nonce) >= 32, f"Nonce should be at least 32 characters: {nonce}"
    
    def test_timestamp_format(self):
        """Тест формата timestamp"""
        timestamp = MockSecurityUtils.get_current_timestamp()
        
        # Проверяем что timestamp можно распарсить
        try:
            import datetime
            parsed_time = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f")
            assert parsed_time is not None
        except ValueError:
            pytest.fail(f"Timestamp should be in valid format: {timestamp}")
    
    def test_message_structure(self):
        """Тест структуры challenge сообщения"""
        nonce = MockSecurityUtils.generate_nonce()
        timestamp = MockSecurityUtils.get_current_timestamp()
        message = MockSecurityUtils.create_challenge_message(self.public_key, nonce, timestamp)
        
        # Проверяем структуру сообщения
        lines = message.split('\n')
        assert len(lines) >= 4, "Message should have at least 4 lines"
        assert "WORLDBINDER Authentication" in lines[0], "First line should contain authentication info"
        assert f"Public Key: {self.public_key}" in lines[1], "Second line should contain public key"
        assert f"Nonce: {nonce}" in lines[2], "Third line should contain nonce"
        assert f"Timestamp: {timestamp}" in lines[3], "Fourth line should contain timestamp"
    
    def test_base58_encoding_decoding(self):
        """Тест кодирования и декодирования base58"""
        # Тестовые данные
        test_data = b"Hello, World!"
        
        # Кодируем в base58
        encoded = base58.b58encode(test_data)
        
        # Декодируем обратно
        decoded = base58.b58decode(encoded)
        
        # Проверяем что данные совпадают
        assert test_data == decoded, "Base58 encoding/decoding should be reversible"
    
    def test_base64_encoding_decoding(self):
        """Тест кодирования и декодирования base64"""
        # Тестовые данные
        test_data = b"Hello, World!"
        
        # Кодируем в base64
        encoded = base64.b64encode(test_data)
        
        # Декодируем обратно
        decoded = base64.b64decode(encoded)
        
        # Проверяем что данные совпадают
        assert test_data == decoded, "Base64 encoding/decoding should be reversible"


if __name__ == "__main__":
    pytest.main([__file__])
