import unittest
import os
import tempfile
import json
import numpy as np
from unittest.mock import patch

from backend.src.services.pipeline_service import EPAPipeline
from backend.src.storage import create_storage


def _make_match(mid: int, event: str, etype: str,
                red: list, blue: list,
                red_score: float, blue_score: float,
                tl: str = "Quals") -> dict:
    def _scores(total, auto=10, dc=20, dcBase=5,
                movementRp=True, goalRp=True, patternRp=True,
                autoClassified=5, dcClassified=10, dcDepot=1):
        return {
            "totalPointsNp": total, "autoPoints": auto, "dcPoints": dc,
            "dcBasePoints": dcBase, "movementRp": movementRp,
            "goalRp": goalRp, "patternRp": patternRp,
            "autoArtifactClassifiedPoints": autoClassified,
            "dcArtifactClassifiedPoints": dcClassified,
            "dcDepotPoints": dcDepot,
        }
    return {
        "match_id": mid, "event": event, "event_type": etype,
        "tournament_level": tl,
        "red_teams": red, "blue_teams": blue,
        "red_scores": _scores(red_score, auto=round(red_score * 0.25),
                              dc=round(red_score * 0.5)),
        "blue_scores": _scores(blue_score, auto=round(blue_score * 0.25),
                               dc=round(blue_score * 0.5)),
    }


FAKE_MATCHES = [
    # Event QUAL1 - consistent winner (red 101+102 dominate)
    _make_match(1, "QUAL1", "Qualifier", [101, 102], [201, 202], 120, 30),
    _make_match(2, "QUAL1", "Qualifier", [101, 102], [203, 204], 110, 40),
    _make_match(3, "QUAL1", "Qualifier", [103, 104], [201, 202], 50, 60),
    _make_match(4, "QUAL1", "Qualifier", [103, 104], [203, 204], 55, 65),
    _make_match(5, "QUAL1", "Qualifier", [101, 103], [201, 204], 100, 45),
    # Event CMP1 - elimination matches with high scores
    _make_match(6, "CMP1", "Championship", [101, 102], [103, 104], 130, 70, tl="Semis"),
    _make_match(7, "CMP1", "Championship", [101, 102], [103, 104], 125, 80, tl="Finals"),
    _make_match(8, "CMP1", "Championship", [201, 202], [203, 204], 90, 85, tl="Semis"),
    # Event QUAL2 - blue team dominance
    _make_match(9, "QUAL2", "Qualifier", [301, 302], [401, 402], 40, 100),
    _make_match(10, "QUAL2", "Qualifier", [301, 302], [403, 404], 35, 95),
    _make_match(11, "QUAL2", "Qualifier", [303, 304], [401, 402], 60, 105),
    _make_match(12, "QUAL2", "Qualifier", [101, 301], [401, 201], 90, 85),
    # Event QUAL3 - close matches
    _make_match(13, "QUAL3", "Qualifier", [101, 401], [102, 402], 70, 72),
    _make_match(14, "QUAL3", "Qualifier", [103, 403], [104, 404], 65, 68),
]


class TestPipelineIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def tearDown(self):
        os.unlink(self.db_path)

    def _run_pipeline(self, season="2025", calibrate=False):
        with patch("backend.src.services.pipeline_service.get_matches") as mock_get:
            mock_get.return_value = FAKE_MATCHES
            pipeline = EPAPipeline(season, db_path=self.db_path, calibrate=calibrate)
            engine = pipeline.run()
            return pipeline, engine

    def test_pipeline_returns_engine(self):
        _, engine = self._run_pipeline()
        self.assertIsNotNone(engine)
        self.assertGreater(len(engine.epas), 0)

    def test_pipeline_trains_all_teams(self):
        _, engine = self._run_pipeline()
        expected_teams = {101, 102, 103, 104, 201, 202, 203, 204,
                          301, 302, 303, 304, 401, 402, 403, 404}
        trained = set(engine.epas.keys())
        self.assertEqual(trained, expected_teams)

    def test_strong_team_has_higher_epa(self):
        _, engine = self._run_pipeline()
        epa_101 = engine.get_team(101).mean[0]
        epa_402 = engine.get_team(402).mean[0]
        self.assertGreater(epa_101, epa_402,
                           "Team 101 (won all matches) should rate higher than Team 402 (lost)")

    def test_storage_has_teams(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        teams = storage.load_all_teams()
        self.assertGreaterEqual(len(teams), 14)

    def test_storage_has_team_matches(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        matches = storage.load_team_matches(101)
        self.assertGreaterEqual(len(matches), 4)

    def test_storage_has_team_events(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        events = storage.load_team_events()
        self.assertGreaterEqual(len(events), 14)

    def test_storage_has_season_meta(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        meta = storage.load_season_meta()
        self.assertIsNotNone(meta)
        self.assertIn("score_sd", meta)
        self.assertIn("num_matches", meta)
        self.assertEqual(meta["num_matches"], len(FAKE_MATCHES))

    def test_norm_epa_saved(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        teams = storage.load_all_teams()
        for t in teams.values():
            self.assertIn("norm_epa", t)
            self.assertIsNotNone(t["norm_epa"])

    def test_epa_pre_post_on_matches(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        matches = storage.load_team_matches(101)
        for m in matches:
            self.assertIn("epa_pre", m)
            self.assertIn("epa_post", m)
            self.assertIn("win_prob", m)

    def test_win_probability_recorded(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        matches = storage.load_team_matches(101)
        for m in matches:
            self.assertGreaterEqual(m["win_prob"], 0.0)
            self.assertLessEqual(m["win_prob"], 1.0)

    def test_elim_matches_marked(self):
        self._run_pipeline()
        storage = create_storage("2025", self.db_path)
        matches = storage.load_team_matches(101)
        elims = [m for m in matches if m["is_elim"]]
        self.assertGreater(len(elims), 0)

    def test_pipeline_resume_skips_processed(self):
        _, engine1 = self._run_pipeline()
        epa_101_first = engine1.get_team(101).mean[0]

        with patch("backend.src.services.pipeline_service.get_matches") as mock_get:
            mock_get.return_value = FAKE_MATCHES
            pipeline2 = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
            engine2 = pipeline2.run()
            epa_101_second = engine2.get_team(101).mean[0]

        self.assertEqual(epa_101_first, epa_101_second,
                         "Resuming should not change EPAs for already-processed matches")

    def test_team_with_few_matches_lower_confidence(self):
        _, engine = self._run_pipeline()
        count_101 = engine.counts.get(101, 0)
        count_402 = engine.counts.get(402, 0)
        self.assertGreater(count_101, count_402)


class TestPipelineWithCalibration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def tearDown(self):
        os.unlink(self.db_path)

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_calibrated_pipeline_runs(self, mock_get):
        mock_get.return_value = FAKE_MATCHES
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=True)
        engine = pipeline.run()
        self.assertIsNotNone(engine)
        self.assertGreater(len(engine.epas), 0)

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_calibrated_score_sd_reasonable(self, mock_get):
        mock_get.return_value = FAKE_MATCHES
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=True)
        engine = pipeline.run()
        self.assertGreater(engine.score_sd, 0)
        self.assertLess(engine.score_sd, 200)


class TestPipelineCrossSeason(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def tearDown(self):
        os.unlink(self.db_path)

    def _run_season(self, season, matches):
        with patch("backend.src.services.pipeline_service.get_matches") as mock_get:
            mock_get.return_value = matches
            pipeline = EPAPipeline(season, db_path=self.db_path, calibrate=False)
            engine = pipeline.run()
            return engine

    def test_init_with_prior_season_data(self):
        prior_matches = [_make_match(1, "QUAL1", "Qualifier", [101, 102], [201, 202], 80, 60)]
        self._run_season("2024", prior_matches)

        from backend.src.storage.sqlite_storage import SQLiteStorage
        priors = SQLiteStorage.get_prior_seasons("2025", look_back=4)
        self.assertIn("2024", priors)

        with patch("backend.src.services.pipeline_service.get_matches") as mock_get:
            mock_get.return_value = [_make_match(2, "QUAL2", "Qualifier", [101, 102], [201, 202], 90, 50)]
            pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
            engine = pipeline.run()
            self.assertIsNotNone(engine)


class TestPipelineEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name

    def tearDown(self):
        os.unlink(self.db_path)

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_empty_matches(self, mock_get):
        mock_get.return_value = []
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
        engine = pipeline.run()
        self.assertIsNone(engine)

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_single_match(self, mock_get):
        mock_get.return_value = [
            _make_match(1, "ONLY", "Qualifier", [101, 102], [201, 202], 100, 50)
        ]
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
        engine = pipeline.run()
        self.assertIsNotNone(engine)
        self.assertEqual(len(engine.epas), 4)
        self.assertGreater(engine.get_team(101).mean[0], engine.get_team(201).mean[0])

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_perfect_tie(self, mock_get):
        mock_get.return_value = [
            _make_match(1, "EVEN", "Qualifier", [101, 102], [201, 202], 100, 100),
            _make_match(2, "EVEN", "Qualifier", [101, 102], [201, 202], 100, 100),
        ]
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
        engine = pipeline.run()
        epa_red = engine.get_team(101).mean[0]
        epa_blue = engine.get_team(201).mean[0]
        self.assertAlmostEqual(epa_red, epa_blue, delta=1.0)

    @patch("backend.src.services.pipeline_service.get_matches")
    def test_large_score_disparity(self, mock_get):
        mock_get.return_value = [
            _make_match(1, "BLOW", "Qualifier", [101, 102], [201, 202], 200, 10),
        ]
        pipeline = EPAPipeline("2025", db_path=self.db_path, calibrate=False)
        engine = pipeline.run()
        epa_101 = engine.get_team(101).mean[0]
        epa_201 = engine.get_team(201).mean[0]
        self.assertGreater(epa_101 - epa_201, 10)


if __name__ == "__main__":
    unittest.main()
