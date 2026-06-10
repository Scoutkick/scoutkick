import unittest
import numpy as np
from backend.src.services.clustering import (
    compute_clusters,
    _extract_playstyle_vectors,
    _auto_label,
    DEFAULT_N_CLUSTERS,
)


def _make_team(mean_vals):
    return {"mean": np.array(mean_vals + [0.0] * (32 - len(mean_vals))), "norm_epa": 1500.0}


SAMPLE_TEAMS = {
    101: _make_team([80.0, 30.0, 40.0, 10.0]),
    102: _make_team([60.0, 10.0, 30.0, 20.0]),
    103: _make_team([100.0, 40.0, 50.0, 10.0]),
    104: _make_team([50.0, 5.0, 25.0, 20.0]),
    105: _make_team([90.0, 25.0, 45.0, 20.0]),
}


class TestExtractPlaystyleVectors(unittest.TestCase):
    def test_extract_returns_vectors_and_teams(self):
        vectors, teams = _extract_playstyle_vectors(SAMPLE_TEAMS, "2025")
        self.assertEqual(len(vectors), len(SAMPLE_TEAMS))
        self.assertEqual(len(teams), len(SAMPLE_TEAMS))
        self.assertEqual(vectors.shape[1], 9)

    def test_excludes_zero_total_teams(self):
        teams = {1: _make_team([0.0, 0.0, 0.0, 0.0])}
        vectors, team_nums = _extract_playstyle_vectors(teams, "2025")
        self.assertEqual(len(vectors), 0)

    def test_2019_season_uses_3_dims(self):
        vectors, teams = _extract_playstyle_vectors(SAMPLE_TEAMS, "2019")
        self.assertEqual(vectors.shape[1], 3)

    def test_unknown_season_falls_back_to_3_dims(self):
        vectors, teams = _extract_playstyle_vectors(SAMPLE_TEAMS, "2099")
        self.assertEqual(vectors.shape[1], 3)

    def test_all_vectors_are_non_negative(self):
        vectors, teams = _extract_playstyle_vectors(SAMPLE_TEAMS, "2025")
        self.assertTrue(np.all(vectors >= 0))


class TestComputeClusters(unittest.TestCase):
    def test_returns_expected_structure(self):
        result = compute_clusters(SAMPLE_TEAMS, "2025")
        self.assertIn("season", result)
        self.assertIn("n_clusters", result)
        self.assertIn("clusters", result)
        self.assertIn("teams", result)
        self.assertIn("dimensions", result)
        self.assertEqual(result["season"], "2025")

    def test_n_clusters_equals_requested(self):
        result = compute_clusters(SAMPLE_TEAMS, "2025", n_clusters=3)
        self.assertEqual(result["n_clusters"], 3)

    def test_all_teams_have_cluster_assignments(self):
        result = compute_clusters(SAMPLE_TEAMS, "2025")
        self.assertEqual(len(result["teams"]), len(SAMPLE_TEAMS))

    def test_cluster_centers_have_correct_dimensions(self):
        result = compute_clusters(SAMPLE_TEAMS, "2025")
        for c in result["clusters"]:
            self.assertEqual(len(c["center"]), 9)

    def test_empty_teams_returns_empty_result(self):
        result = compute_clusters({}, "2025")
        self.assertEqual(result["n_clusters"], 0)
        self.assertEqual(len(result["clusters"]), 0)

    def test_consistent_with_random_state(self):
        r1 = compute_clusters(SAMPLE_TEAMS, "2025", random_state=42)
        r2 = compute_clusters(SAMPLE_TEAMS, "2025", random_state=42)
        self.assertEqual(r1["teams"], r2["teams"])

    def test_top_teams_in_each_cluster(self):
        result = compute_clusters(SAMPLE_TEAMS, "2025")
        for c in result["clusters"]:
            for t in c["top_teams"]:
                self.assertIn(t, SAMPLE_TEAMS)

    def test_default_n_clusters_constant(self):
        self.assertEqual(DEFAULT_N_CLUSTERS, 5)

    def test_2019_season_clusters(self):
        result = compute_clusters(SAMPLE_TEAMS, "2019")
        for c in result["clusters"]:
            self.assertEqual(len(c["center"]), 3)


class TestAutoLabel(unittest.TestCase):
    def test_dominant_label(self):
        center = np.array([0.6, 0.2, 0.2])
        label = _auto_label(center, ["auto", "teleop", "endgame"])
        self.assertIn("Dominant", label)

    def test_heavy_label(self):
        center = np.array([0.45, 0.05, 0.05])
        label = _auto_label(center, ["auto", "teleop", "endgame"])
        self.assertIn("Auto", label)

    def test_balanced_fallback(self):
        center = np.array([0.2, 0.2, 0.2])
        label = _auto_label(center, ["auto", "teleop", "endgame"])
        self.assertTrue("Balanced" in label or "+" in label)

    def test_auto_dominant_with_9_dims(self):
        center = np.zeros(9)
        center[0] = 0.55
        center[1:] = 0.45 / 8
        labels = ["auto", "teleop", "endgame", "rp1", "rp2", "rp3", "auto_cls", "tele_cls", "depot"]
        label = _auto_label(center, labels)
        self.assertIn("Auto", label)

    def test_mixed_low_values(self):
        center = np.array([0.15, 0.15, 0.15])
        label = _auto_label(center, ["auto", "teleop", "endgame"])
        self.assertEqual(label, "Balanced")


if __name__ == "__main__":
    unittest.main()
