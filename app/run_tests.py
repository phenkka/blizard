#!/usr/bin/env python3
"""
Скрипт для запуска всех тестов безопасности
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Запуск команды с выводом результата"""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {description} - УСПЕШНО")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"❌ {description} - ОШИБКА")
            if result.stderr:
                print("Ошибки:")
                print(result.stderr)
            if result.stdout:
                print("Вывод:")
                print(result.stdout)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ {description} - ИСКЛЮЧЕНИЕ: {e}")
        return False

def main():
    """Главная функция"""
    print("🔒 WORLDBINDER Security Tests Suite")
    print("=" * 60)
    
    # Переходим в директорию приложения
    app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)
    
    tests_passed = 0
    total_tests = 0
    
    # Тест 1: Юнит-тесты безопасности бэкенда
    total_tests += 1
    if run_command(
        "python -m pytest tests/test_auth_security.py -v --tb=short",
        "Юнит-тесты безопасности аутентификации"
    ):
        tests_passed += 1
    
    # Тест 2: Тесты безопасности сессий
    total_tests += 1
    if run_command(
        "python -m pytest tests/test_session_security.py -v --tb=short",
        "Тесты безопасности сессий и rate limiting"
    ):
        tests_passed += 1
    
    # Тест 3: Проверка покрытия кода
    total_tests += 1
    if run_command(
        "python -m pytest tests/ --cov=main --cov-report=term-missing --cov-fail-under=80",
        "Проверка покрытия кода тестами"
    ):
        tests_passed += 1
    
    # Тест 4: Проверка зависимостей на уязвимости
    total_tests += 1
    if run_command(
        "pip-audit --requirement requirements.txt",
        "Проверка зависимостей на уязвимости"
    ):
        tests_passed += 1
    
    # Тест 5: Линтинг кода
    total_tests += 1
    if run_command(
        "python -m flake8 main.py --max-line-length=100 --ignore=E203,W503",
        "Линтинг основного кода"
    ):
        tests_passed += 1
    
    # Тест 6: Проверка типов
    total_tests += 1
    if run_command(
        "python -m mypy main.py --ignore-missing-imports",
        "Проверка типов (mypy)"
    ):
        tests_passed += 1
    
    # Итоги
    print(f"\n{'='*60}")
    print(f"📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print(f"{'='*60}")
    print(f"✅ Пройдено: {tests_passed}/{total_tests}")
    print(f"❌ Провалено: {total_tests - tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
        return 1

if __name__ == "__main__":
    sys.exit(main())
