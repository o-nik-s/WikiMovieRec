from src.imdb_loader import load_title_basics
import os, pandas as pd

df = load_title_basics()
for _, row in df[df["Title"].str.contains("titanic", case=False, na=False)].head(5).iterrows():
    print(f"Title: {row['Title']}, Year: {row['Year']}")