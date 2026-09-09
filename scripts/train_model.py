#!/usr/bin/env python3
"""
Скрипт для обучения моделей на сервере
"""

import argparse
import subprocess
import sys
import os

def train_model(preset="fast", backend="keras", source="imdb"):
    """Обучить модель с заданными параметрами"""
    print(f"Обучение модели: preset={preset}, backend={backend}, source={source}")
    
    cmd = [
        sys.executable, "-m", "src.embedding",
        "train",
        f"--preset={preset}",
        f"--backend={backend}",
        f"--source={source}"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Обучение завершено успешно")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при обучении: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Обучение моделей WikiMovieRec")
    parser.add_argument("--preset", choices=["fast", "medium", "deep"], default="fast",
                       help="Пресет модели (fast, medium, deep)")
    parser.add_argument("--backend", choices=["keras", "svd"], default="keras",
                       help="Бэкенд модели (keras, svd)")
    parser.add_argument("--source", choices=["imdb", "wiki"], default="imdb",
                       help="Источник данных (imdb, wiki)")
    parser.add_argument("--all", action="store_true",
                       help="Обучить все модели (fast, medium, deep)")
    
    args = parser.parse_args()
    
    if args.all:
        presets = ["fast", "medium", "deep"]
        for preset in presets:
            print(f"\n{'='*50}")
            print(f"Обучение {preset} модели")
            print(f"{'='*50}")
            if not train_model(preset, args.backend, args.source):
                print(f"Остановка из-за ошибки в {preset} модели")
                sys.exit(1)
    else:
        train_model(args.preset, args.backend, args.source)

if __name__ == "__main__":
    main()