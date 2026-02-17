#!/bin/bash

# WORLDBINDER Security Tests - запуск из корня проекта
echo "🔒 WORLDBINDER Security Tests"
echo "============================="

# Переходим в директорию app и запускаем тесты
cd app
./run_tests.sh
