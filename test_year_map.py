from src.data_loader import load_all
from src.preprocessor import build_features, merge_with_plots


def main():
    movies_df, metadata_df = load_all(source="imdb")
    movies_df = build_features(movies_df)
    merged = merge_with_plots(movies_df, metadata_df)

    for _, row in merged[
        merged["Title"].str.contains("titanic", case=False, na=False)
    ].iterrows():
        print(
            f"Name: {row['Name']}, Title: {row['Title']}, "
            f"Year: {row.get('Year', 'N/A')}"
        )


if __name__ == "__main__":
    main()