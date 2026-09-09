import json
import csv
import sys

print("=== NDJSON: wp_movies_10k.ndjson ===")
ndjson_path = 'wp_movies_10k.ndjson'
count = 0
bad = 0
field_counts = {}
with open(ndjson_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        count += 1
        try:
            rec = json.loads(line)
            if isinstance(rec, list):
                n = len(rec)
                field_counts[n] = field_counts.get(n, 0) + 1
            else:
                bad += 1
        except Exception as e:
            bad += 1
print(f"Total records: {count}")
print(f"Bad/invalid: {bad}")
print(f"Field-count distribution: {field_counts}")

print()
print("=== CSV: wiki_movie_plots_deduped.csv ===")
csv_path = 'wiki_movie_plots_deduped.csv'
with open(csv_path, 'r', encoding='utf-8', newline='') as f:
    reader = csv.reader(f)
    header = next(reader)
    print(f"Header: {header}")
    print(f"Num columns: {len(header)}")
    rows = 0
    for _ in reader:
        rows += 1
    print(f"Data rows: {rows}")
