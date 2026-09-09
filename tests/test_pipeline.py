import logging
import sys
import unittest
import numpy as np

logging.basicConfig(level=logging.WARNING)


class TestDataLoader(unittest.TestCase):
    def test_load_ndjson(self):
        from src.data_loader import load_ndjson
        df = load_ndjson()
        self.assertEqual(len(df), 10000)
        self.assertIn("Name", df.columns)
        self.assertIn("Links", df.columns)

    def test_load_csv(self):
        from src.data_loader import load_csv
        df = load_csv()
        self.assertGreater(len(df), 34000)
        self.assertIn("Title", df.columns)
        self.assertIn("Genre", df.columns)


class TestPreprocessor(unittest.TestCase):
    def test_extract_title(self):
        from src.preprocessor import extract_title
        self.assertEqual(extract_title("Deadpool (film)"), "Deadpool")
        self.assertEqual(extract_title("Harry Potter (film series)"), "Harry Potter")
        self.assertEqual(extract_title("Titanic (1997 film)"), "Titanic")

    def test_parse_rating1(self):
        from src.preprocessor import parse_rating1
        self.assertAlmostEqual(parse_rating1("84%"), 84.0)
        self.assertTrue(np.isnan(parse_rating1(None)))
        self.assertTrue(np.isnan(parse_rating1("not-a-rating")))

    def test_parse_rating2(self):
        from src.preprocessor import parse_rating2
        self.assertAlmostEqual(parse_rating2("6.9/10"), 0.69)
        self.assertTrue(np.isnan(parse_rating2(None)))
        self.assertTrue(np.isnan(parse_rating2("6/0")))

    def test_build_features(self):
        from src.data_loader import load_ndjson
        from src.preprocessor import build_features
        df = load_ndjson()
        processed = build_features(df)
        self.assertIn("Title", processed.columns)
        self.assertIn("MovieLinks", processed.columns)
        self.assertIn("CategoryLinks", processed.columns)
        self.assertIn("Rating3", processed.columns)


class TestClassifier(unittest.TestCase):
    def test_get_classifier(self):
        from src.classifier import get_classifier
        clf = get_classifier("LinearSVC", random_state=42)
        self.assertIsNotNone(clf)

    def test_invalid_classifier(self):
        from src.classifier import get_classifier
        with self.assertRaises(ValueError):
            get_classifier("FakeClassifier")


if __name__ == "__main__":
    sys.exit(unittest.main())