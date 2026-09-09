# -*- coding: utf-8 -*-
"""Local smoke test for the FastAPI server (run against 127.0.0.1:8000)."""
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def show(title: str, data: dict, key: str = "similar"):
    print(f"\n=== {title} ===")
    for x in data.get(key, [])[:5]:
        print(f"  {x.get('name')} | {x.get('ru_name')} | "
              f"{x.get('similarity')} | {x.get('genres')} | {x.get('rating')}")


def main():
    # 1. Health
    h = get("/api/health")
    print("HEALTH:", h)
    assert h["status"] == "ok", "model not loaded"

    # 2. English query
    show("EN: Saving Private Ryan",
         get("/api/similar?movie=" + urllib.parse.quote("Saving Private Ryan") + "&top_k=5"))

    # 3. Russian query
    show("RU: Титаник",
         get("/api/similar?movie=" + urllib.parse.quote("Титаник") + "&top_k=5"))

    # 4. Russian query with year
    show("RU: Титаник (1997)",
         get("/api/similar?movie=" + urllib.parse.quote("Титаник (1997)") + "&top_k=5"))

    # 5. Search endpoint
    s = get("/api/search?q=" + urllib.parse.quote("Титаник"))
    print("\n=== SEARCH: Титаник ===")
    for m in s.get("matches", [])[:5]:
        print(f"  {m.get('name')} | {m.get('ru_name')} | {m.get('year')} | score={m.get('score')}")

    # 6. Genres
    g = get("/api/genres")
    print("\nGENRES:", g)

    print("\nALL OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        sys.exit(1)
