import unittest
from unittest.mock import MagicMock
import numpy as np
from backend.src.services.trajectory import (
    _compute_trajectory_features,
    _auto_trajectory_label,
    compute_trajectory_clusters,
)


def _make_storage_with_matches(team_matches):
    storage = MagicMock()
    storage.load_all_teams.return_value = {101: {"mean": np.array([80.0] + [0.0] * 31)}}
    storage.load_team_matches.side_effect = lambda t: team_matches.get(t, [])
    return storage


def _make_match(epa_post, event="E1", mid="1"):
    return {
        "team": 101, "season": "2025", "event_code": event,
        "match_id": mid, "epa_pre": epa_post - 2,
        "epa_post": epa_post, "win_prob": 0.5, "is_elim": 0,
        "processed_at": "2025-01-01",
    }


class TestComputeTrajectoryFeatures(unittest.TestCase):
    def test_less_than_3_matches_returns_none(self):
        storage = _make_storage_with_matches({101: [_make_match(80.0), _make_match(85.0)]})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertIsNone(result)

    def test_empty_matches_returns_none(self):
        storage = _make_storage_with_matches({101: []})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertIsNone(result)

    def test_3_matches_returns_features(self):
        matches = [_make_match(80.0, "E1", "1"),
                   _make_match(85.0, "E1", "2"),
                   _make_match(90.0, "E1", "3")]
        storage = _make_storage_with_matches({101: matches})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertIsNotNone(result)
        self.assertIn("epa_start", result)
        self.assertIn("epa_end", result)
        self.assertIn("epa_slope", result)
        self.assertIn("match_count", result)
        self.assertEqual(result["match_count"], 3)

    def test_increasing_epa_has_positive_slope(self):
        matches = [_make_match(70.0, "E1", "1"),
                   _make_match(80.0, "E1", "2"),
                   _make_match(90.0, "E1", "3")]
        storage = _make_storage_with_matches({101: matches})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertGreater(result["epa_slope"], 0)

    def test_decreasing_epa_has_negative_slope(self):
        matches = [_make_match(90.0, "E1", "1"),
                   _make_match(80.0, "E1", "2"),
                   _make_match(70.0, "E1", "3")]
        storage = _make_storage_with_matches({101: matches})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertLess(result["epa_slope"], 0)

    def test_volatility_with_varying_scores(self):
        matches = [_make_match(80.0), _make_match(90.0), _make_match(70.0)]
        storage = _make_storage_with_matches({101: matches})
        result = _compute_trajectory_features(storage, 101, "2025")
        self.assertGreater(result["epa_volatility"], 0)

    def test_all_returned_keys(self):
        matches = [_make_match(80.0), _make_match(85.0), _make_match(90.0),
                   _make_match(95.0), _make_match(100.0)]
        storage = _make_storage_with_matches({101: matches})
        result = _compute_trajectory_features(storage, 101, "2025")
        expected = {"epa_start", "epa_end", "epa_max", "epa_min", "epa_change",
                    "epa_range", "epa_mean", "epa_std", "epa_slope",
                    "epa_mid_slope", "epa_volatility", "match_count"}
        self.assertEqual(set(result.keys()), expected)


class TestAutoTrajectoryLabel(unittest.TestCase):
    def test_consistent_label(self):
        centroid = np.array([0.0, 1.0, 0.0, 0.9, 0.0, 0.0, 0.0, 0.0])
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertIn("Bloomer", label)

    def test_declining_label(self):
        centroid = np.array([1.0, 0.0, -1.0, -0.7, 0.1, 0.1, 0.0, 0.0])
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertIn("Declining", label)

    def test_consistent_label(self):
        centroid = np.array([0.0, 0.0, 0.0, 0.1, 0.1, 0.1, 0.0, 0.0])
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertIn(label, ("Consistent", "Stable"))

    def test_volatile_improver(self):
        centroid = np.array([0.0, 0.0, 0.0, 0.4, 1.0, 1.0, 0.0, 0.0])
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertIn("Volatile", label)

    def test_inconsistent_label(self):
        centroid = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0])
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertIn("Inconsistent", label)

    def test_flat_centroid_returns_consistent(self):
        centroid = np.zeros(8)
        keys = ["epa_start", "epa_end", "epa_change", "epa_slope", "epa_std",
                "epa_volatility", "epa_range", "match_count"]
        label = _auto_trajectory_label(centroid, keys)
        self.assertEqual(label, "Consistent")


class TestComputeTrajectoryClusters(unittest.TestCase):
    def test_no_teams_with_matches_returns_empty(self):
        storage = MagicMock()
        storage.load_all_teams.return_value = {}
        result = compute_trajectory_clusters(storage, "2025")
        self.assertEqual(len(result["clusters"]), 0)

    def test_single_team_with_matches(self):
        matches = [_make_match(80.0, "E1", str(i)) for i in range(5)]
        storage = _make_storage_with_matches({101: matches})
        result = compute_trajectory_clusters(storage, "2025")
        self.assertGreaterEqual(len(result["clusters"]), 1)

    def test_expected_structure(self):
        matches = [_make_match(80.0, "E1", str(i)) for i in range(5)]
        storage = _make_storage_with_matches({101: matches})
        result = compute_trajectory_clusters(storage, "2025")
        self.assertIn("season", result)
        self.assertIn("clusters", result)
        self.assertIn("teams", result)
        self.assertIn("feature_keys", result)


if __name__ == "__main__":
    unittest.main()
