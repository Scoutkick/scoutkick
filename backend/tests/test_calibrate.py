import unittest
from unittest.mock import patch
import numpy as np
from backend.src.core.config import FTC_VECTOR_SIZE
from backend.src.services.calibrate import calibrate_score_sd, calibrate_component_means
from backend.src.data.cleaner import BaseCleaner


FAKE_MATCHES = [
    {
        "red_scores": {"totalPointsNp": 120, "autoPoints": 30, "dcPoints": 60},
        "blue_scores": {"totalPointsNp": 80, "autoPoints": 20, "dcPoints": 40},
    },
    {
        "red_scores": {"totalPointsNp": 150, "autoPoints": 40, "dcPoints": 75},
        "blue_scores": {"totalPointsNp": 60, "autoPoints": 10, "dcPoints": 30},
    },
    {
        "red_scores": {"totalPointsNp": 90, "autoPoints": 25, "dcPoints": 45},
        "blue_scores": {"totalPointsNp": 100, "autoPoints": 30, "dcPoints": 50},
    },
]

EMPTY_MATCHES: list = []


class TestCalibrateScoreSD(unittest.TestCase):
    def setUp(self):
        self.cleaner = BaseCleaner.get_cleaner("2025")

    @patch("backend.src.services.calibrate.get_matches")
    def test_calibrate_with_data(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        sd = calibrate_score_sd(self.cleaner, "2025")
        self.assertIsInstance(sd, float)
        self.assertGreater(sd, 0)

    @patch("backend.src.services.calibrate.get_matches")
    def test_calibrate_empty_matches_returns_default(self, mock_get_matches):
        mock_get_matches.return_value = EMPTY_MATCHES
        sd = calibrate_score_sd(self.cleaner, "2025")
        self.assertEqual(sd, 20.0)

    @patch("backend.src.services.calibrate.get_matches")
    def test_calibrate_single_match_has_enough_scores(self, mock_get_matches):
        mock_get_matches.return_value = [FAKE_MATCHES[0]]
        sd = calibrate_score_sd(self.cleaner, "2025")
        self.assertIsInstance(sd, float)
        self.assertGreater(sd, 0)

    @patch("backend.src.services.calibrate.get_matches")
    def test_calibrate_with_max_matches(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        sd = calibrate_score_sd(self.cleaner, "2025", max_matches=2)
        self.assertIsInstance(sd, float)

    @patch("backend.src.services.calibrate.get_matches")
    def test_calibrate_returns_rounded_value(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        sd = calibrate_score_sd(self.cleaner, "2025")
        self.assertEqual(sd, round(sd, 2))


class TestCalibrateComponentMeans(unittest.TestCase):
    def setUp(self):
        self.cleaner = BaseCleaner.get_cleaner("2025")

    @patch("backend.src.services.calibrate.get_matches")
    def test_component_means_with_data(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        means = calibrate_component_means(self.cleaner, "2025")
        self.assertEqual(len(means), FTC_VECTOR_SIZE)
        self.assertGreater(means[0], 0)

    @patch("backend.src.services.calibrate.get_matches")
    def test_component_means_empty_returns_zeros(self, mock_get_matches):
        mock_get_matches.return_value = EMPTY_MATCHES
        means = calibrate_component_means(self.cleaner, "2025")
        self.assertTrue(np.all(means == 0))

    @patch("backend.src.services.calibrate.get_matches")
    def test_component_means_correct_shape(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        means = calibrate_component_means(self.cleaner, "2025")
        self.assertEqual(means.shape, (FTC_VECTOR_SIZE,))

    @patch("backend.src.services.calibrate.get_matches")
    def test_component_means_with_max_matches(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        means = calibrate_component_means(self.cleaner, "2025", max_matches=2)
        self.assertEqual(len(means), FTC_VECTOR_SIZE)

    @patch("backend.src.services.calibrate.get_matches")
    def test_total_mean_is_reasonable(self, mock_get_matches):
        mock_get_matches.return_value = FAKE_MATCHES
        means = calibrate_component_means(self.cleaner, "2025")
        # Average total should be around 100
        self.assertGreater(means[0], 50)
        self.assertLess(means[0], 150)


if __name__ == "__main__":
    unittest.main()
