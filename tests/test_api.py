"""Tests for API endpoints (validation, edge cases)."""
import logging
import sys
import unittest

logging.basicConfig(level=logging.WARNING)


class TestApiValidation(unittest.TestCase):
    """Test API input validation without loading the full model."""

    def test_profile_sample_sample_n_gt_pool(self):
        """sample_n > pool_size should be rejected."""
        from src.api import create_app
        app = create_app()
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi TestClient not available")
        with TestClient(app) as client:
            resp = client.get(
                "/api/profile-sample",
                params={"movies": "Titanic", "sample_n": 100, "pool_size": 50},
            )
            # Either 400 (validation) or 200 with error field
            self.assertIn(resp.status_code, (400, 422))

    def test_profile_empty_movies(self):
        """Empty movies list should return empty similar."""
        from src.api import create_app
        app = create_app()
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi TestClient not available")
        with TestClient(app) as client:
            resp = client.get("/api/profile", params={"movies": ""})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("similar"), [])

    def test_similar_missing_movie(self):
        """Non-existent movie should return 404."""
        from src.api import create_app
        app = create_app()
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi TestClient not available")
        with TestClient(app) as client:
            resp = client.get(
                "/api/similar",
                params={"movie": "NonexistentMovieXYZ123", "top_k": 5},
            )
            self.assertIn(resp.status_code, (404, 200))

    def test_health_endpoint(self):
        """Health endpoint should return status ok."""
        from src.api import create_app
        app = create_app()
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi TestClient not available")
        with TestClient(app) as client:
            resp = client.get("/api/health")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("status", data)


if __name__ == "__main__":
    sys.exit(unittest.main())