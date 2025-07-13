#!/usr/bin/env python3
"""
Тестовый скрипт для проверки определения домена в middleware
"""

import json

import requests


def test_domain_detection():
    """Тестирует определение домена с разными заголовками"""
    
    # Тест 1: Прямой запрос к localhost
    print("=== Тест 1: Прямой запрос к localhost ===")
    try:
        response = requests.get("http://localhost:8000/api/auth/event/status")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Тест 2: Запрос с заголовком Host
    print("=== Тест 2: Запрос с заголовком Host ===")
    try:
        headers = {"Host": "hserun.ru"}
        response = requests.get("http://localhost:8000/api/auth/event/status", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Тест 3: Запрос с заголовком X-Forwarded-Host
    print("=== Тест 3: Запрос с заголовком X-Forwarded-Host ===")
    try:
        headers = {"X-Forwarded-Host": "technoquestcroc.ru"}
        response = requests.get("http://localhost:8000/api/auth/event/status", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    test_domain_detection() 