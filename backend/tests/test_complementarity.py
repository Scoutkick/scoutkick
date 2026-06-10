import unittest
from unittest.mock import MagicMock
import numpy as np
from backend.src.services.complementarity import (
    _get_playstyle_vec,
    complementarity_score,
    best_alliance_partners,
)


def _make_storage(teams):
    storage = MagicMock()
    def load_side_effect(t):
        if t in teams:
            return {"mean": np.array(teams[t] + [0.0] * (32 - len(teams[t])))}
        return None
    storage.load_team.side_effect = load_side_effect
    storage.load_all_teams.return_value = {k: {"mean": np.array(v + [0.0] * (32 - len(v)))} for k, v in teams.items()}
    return storage


TEAM_101 = [80.0, 30.0, 40.0, 10.0]
TEAM_102 = [60.0, 10.0, 30.0, 20.0]
TEAM_103 = [100.0, 5.0, 25.0, 20.0]


class TestGetPlaystyleVec(unittest.TestCase):
    def test_returns_normalized_vector(self):
        storage = _make_storage({101: TEAM_101})
        vec = _get_playstyle_vec(storage, 101, "2025")
        self.assertIsNotNone(vec)
        self.assertAlmostEqual(float(np.sum(vec)), 1.0, places=5)

    def test_returns_none_for_missing_team(self):
        storage = _make_storage({})
        vec = _get_playstyle_vec(storage, 999, "2025")
        self.assertIsNone(vec)

    def test_2019_season_uses_3_dims(self):
        storage = _make_storage({101: TEAM_101})
        vec = _get_playstyle_vec(storage, 101, "2019")
        self.assertEqual(len(vec), 3)

    def test_2025_season_uses_9_dims(self):
        storage = _make_storage({101: TEAM_101 + [0.5, 0.5, 0.5, 0.0, 0.0, 0.0]})
        vec = _get_playstyle_vec(storage, 101, "2025")
        self.assertEqual(len(vec), 9)

    def test_zero_total_returns_none(self):
        storage = _make_storage({1: [0.0, 0.0, 0.0, 0.0]})
        vec = _get_playstyle_vec(storage, 1, "2019")
        self.assertIsNone(vec)


class TestComplementarityScore(unittest.TestCase):
    def test_complementarity_between_two_teams(self):
        storage = _make_storage({101: TEAM_101, 102: TEAM_102})
        result = complementarity_score(storage, 101, 102, "2025")
        self.assertIsNotNone(result)
        self.assertIn("complementarity", result)
        self.assertIn("coverage", result)
        self.assertIn("diversity", result)
        self.assertIn("bottleneck_dim", result)
        self.assertGreater(result["complementarity"], 0)

    def test_missing_team_returns_none(self):
        storage = _make_storage({101: TEAM_101})
        result = complementarity_score(storage, 101, 999, "2025")
        self.assertIsNone(result)

    def test_both_missing_returns_none(self):
        storage = _make_storage({})
        result = complementarity_score(storage, 999, 888, "2025")
        self.assertIsNone(result)

    def test_self_complementarity(self):
        storage = _make_storage({101: TEAM_101})
        result = complementarity_score(storage, 101, 101, "2025")
        self.assertIsNotNone(result)
        self.assertEqual(result["diversity"], 0.0)

    def test_different_teams_have_diversity(self):
        storage = _make_storage({101: TEAM_101, 102: TEAM_102})
        result = complementarity_score(storage, 101, 102, "2025")
        self.assertGreater(result["diversity"], 0)

    def test_bottleneck_is_weakest_dimension(self):
        storage = _make_storage({101: TEAM_101, 103: TEAM_103})
        result = complementarity_score(storage, 101, 103, "2025")
        self.assertIsNotNone(result["bottleneck_dim"])

    def test_playstyles_included_in_result(self):
        storage = _make_storage({101: TEAM_101, 102: TEAM_102})
        result = complementarity_score(storage, 101, 102, "2025")
        self.assertIn("team1_playstyle", result)
        self.assertIn("team2_playstyle", result)
        self.assertIn("combined_coverage", result)


class TestBestAlliancePartners(unittest.TestCase):
    def test_returns_list_of_partners(self):
        teams = {101: TEAM_101, 102: TEAM_102, 103: TEAM_103}
        storage = _make_storage(teams)
        partners = best_alliance_partners(storage, 101, "2025", top_n=2)
        self.assertEqual(len(partners), 2)
        for p in partners:
            self.assertIn("team", p)
            self.assertIn("complementarity", p)
            self.assertIn("coverage", p)
            self.assertIn("epa", p)

    def test_excludes_self_from_partners(self):
        teams = {101: TEAM_101}
        storage = _make_storage(teams)
        partners = best_alliance_partners(storage, 101, "2025")
        self.assertEqual(len(partners), 0)

    def test_returns_sorted_by_score(self):
        teams = {101: TEAM_101, 102: TEAM_102, 103: TEAM_103}
        storage = _make_storage(teams)
        partners = best_alliance_partners(storage, 101, "2025", top_n=5)
        scores = [p["complementarity"] for p in partners]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_missing_target_returns_empty(self):
        storage = _make_storage({})
        partners = best_alliance_partners(storage, 999, "2025")
        self.assertEqual(len(partners), 0)


if __name__ == "__main__":
    unittest.main()
