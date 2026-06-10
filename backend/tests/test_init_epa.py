import unittest
import numpy as np
from backend.src.core.config import get_season_config
from backend.src.core.math import SkewNormal
from backend.src.services.init_epa import get_init_epa, compute_norm_epa, _zscore_norm_epa


class TestZScoreNormEPA(unittest.TestCase):
    def test_basic_zscore(self):
        epas = {1: SkewNormal(np.array([80.0] + [0.0] * 31), np.ones(32) * 100),
                2: SkewNormal(np.array([120.0] + [0.0] * 31), np.ones(32) * 100)}
        result = _zscore_norm_epa(epas)
        self.assertAlmostEqual(result[1], 1500 - 250, delta=1)
        self.assertAlmostEqual(result[2], 1500 + 250, delta=1)

    def test_all_same_epa_returns_norm_mean(self):
        epas = {1: SkewNormal(np.zeros(32), np.ones(32) * 100)}
        result = _zscore_norm_epa(epas)
        self.assertEqual(result[1], 1500.0)

    def test_single_team_returns_norm_mean(self):
        epas = {1: SkewNormal(np.array([50.0] + [0.0] * 31), np.ones(32) * 100)}
        result = _zscore_norm_epa(epas)
        self.assertEqual(result[1], 1500.0)

    def test_multiple_teams_follow_normal(self):
        epas = {}
        for i in range(10):
            sn = SkewNormal(np.array([float(100 + i * 10)] + [0.0] * 31), np.ones(32) * 100)
            epas[i] = sn
        result = _zscore_norm_epa(epas)
        means = list(result.values())
        self.assertAlmostEqual(float(np.mean(means)), 1500.0, delta=50)
        self.assertGreater(float(np.std(means)), 0)


class TestComputeNormEPA(unittest.TestCase):
    def test_few_teams_falls_back_to_zscore(self):
        epas = {1: SkewNormal(np.array([80.0] + [0.0] * 31), np.ones(32) * 100)}
        result = compute_norm_epa(epas)
        self.assertEqual(result[1], 1500.0)

    def test_many_teams_uses_exponnorm(self):
        epas = {}
        rng = np.random.default_rng(42)
        for i in range(20):
            val = float(rng.normal(100, 30))
            sn = SkewNormal(np.array([val] + [0.0] * 31), np.ones(32) * 100)
            epas[i] = sn
        result = compute_norm_epa(epas)
        self.assertEqual(len(result), 20)
        for v in result.values():
            self.assertGreater(v, 500)
            self.assertLess(v, 2500)


class TestGetInitEPA(unittest.TestCase):
    def setUp(self):
        self.config = get_season_config("2025")
        self.comp_means = np.array([100.0, 30.0, 50.0, 20.0] + [0.0] * 28)
        self.score_sd = 50.0
        self.score_mean = 100.0

    def test_returns_skewnormal(self):
        sn = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean)
        self.assertIsInstance(sn, SkewNormal)
        self.assertEqual(len(sn.mean), 32)

    def test_mean_has_reasonable_values(self):
        sn = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean)
        self.assertGreater(sn.mean[0], 0)
        self.assertLess(sn.mean[0], 200)

    def test_total_variance_is_positive(self):
        sn = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean)
        self.assertGreater(sn.var[0], 0)

    def test_no_prior_is_rookie_init(self):
        sn = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean)
        sn2 = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean,
                           prior_norm_epa_1=None, prior_norm_epa_2=None)
        np.testing.assert_array_almost_equal(sn.mean, sn2.mean)

    def test_prior_raises_epa(self):
        sn_rookie = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean)
        sn_vet = get_init_epa(self.config, self.comp_means, self.score_sd, self.score_mean,
                              prior_norm_epa_1=1600.0, prior_norm_epa_2=1550.0)
        self.assertGreater(sn_vet.mean[0], sn_rookie.mean[0])

    def test_zero_score_mean_uses_default_sd_frac(self):
        sn = get_init_epa(self.config, self.comp_means, self.score_sd, score_mean=0)
        self.assertIsInstance(sn, SkewNormal)

    def test_rp_indices_get_inv_sigmoid(self):
        config_2025 = get_season_config("2025")
        comp = np.array([100.0, 30.0, 50.0, 20.0, 0.5, 0.5, 0.5] + [0.0] * 25)
        sn = get_init_epa(config_2025, comp, self.score_sd, self.score_mean)
        self.assertIsNotNone(sn.mean[4])

    def test_2019_config_no_rp(self):
        config = get_season_config("2019")
        comp = np.array([50.0, 15.0, 25.0, 10.0] + [0.0] * 28)
        sn = get_init_epa(config, comp, self.score_sd, self.score_mean)
        self.assertIsInstance(sn, SkewNormal)

    def test_custom_mean_reversion_with_priors(self):
        sn_default = get_init_epa(
            self.config, self.comp_means, self.score_sd, self.score_mean,
            prior_norm_epa_1=1600.0, prior_norm_epa_2=1550.0,
        )
        sn_no_rev = get_init_epa(
            self.config, self.comp_means, self.score_sd, self.score_mean,
            prior_norm_epa_1=1600.0, prior_norm_epa_2=1550.0,
            mean_reversion=0.0,
        )
        self.assertNotAlmostEqual(float(sn_default.mean[0]), float(sn_no_rev.mean[0]))


if __name__ == "__main__":
    unittest.main()
