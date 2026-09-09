#!/usr/bin/env python3
"""
Скрипт для обновления данных IMDb
"""

import argparse
import subprocess
import sys
import os

def update_imdb_data():
    """Обновить данные IMDb"""
    print("Обновление данных IMDb...")
    
    cmd = [sys.executable, "update_data.py"]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Обновление данных завершено успешно")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при обновлении данных: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False

def update_titles():
    """Обновить названия фильмов"""
    print("Обновление названий фильмов...")
    
    cmd = [sys.executable, "update_titles.py"]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Обновление названий завершено успешно")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при обновлении названий: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False

def validate_data():
    """Проверить данные"""
    print("Проверка данных...")
    
    cmd = [sys.executable, "validate_data.py"]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Проверка данных завершена успешно")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при проверке данных: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Управление данными WikiMovieRec")
    parser.add_argument("--imdb", action="store_true", help="Обновить данные IMDb")
    parser.add_argument("--titles", action="store_true", help="Обновить названия фильмов")
    parser.add_argument("--validate", action="store_true", help="Проверить данные")
    parser.add_argument("--all", action="store_true", help="Выполнить все операции")
    
    args = parser.parse_args()
    
    success = True
    
    if args.all or args.imdb:
        if not update_imdb_data():
            success = False
    
    if args.all or args.titles:
        if not update_titles():
            success = False
    
    if args.all or args.validate:
        if not validate_data():
            success = False
    
    if not (args.imdb or args.titles or args.validate or args.all):
        parser.print_help()
        return
    
    if success:
        print("\nВсе операции выполнены успешно!")
    else:
        print("\nНекоторые операции завершились с ошибками")
        sys.exit(1)

if __name__ == "__main__":
    main()