from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PaginatedResponse:
    value: list[Any]
    count: int


class ScoutKickError(Exception):
    pass


class ScoutKick:
    """Zero-dependency Python client for the ScoutKick EPA API."""

    def __init__(self, base_url: str = "https://scoutkick.onrender.com", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── internals ──

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            qs = urllib.parse.urlencode(
                [(k, v) for k, v in params.items() if v is not None], doseq=True
            )
            url = f"{url}?{qs}"
        try:
            resp = urllib.request.urlopen(url, timeout=self.timeout)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = _try_decode_error(e)
            raise ScoutKickError(f"HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise ScoutKickError(f"Connection failed: {e.reason}") from None

    def _paginated(self, path: str, params: dict[str, Any] | None = None) -> PaginatedResponse:
        data = self._get(path, params)
        return PaginatedResponse(value=data["value"], count=data["count"])

    # ── Health ──

    def health(self) -> dict:
        """Get server health status."""
        return self._get("/v1/health")

    # ── Seasons ──

    def get_seasons(self) -> PaginatedResponse:
        """List all seasons that have pipeline data stored."""
        return self._paginated("/v1/seasons")

    def get_season(self, season: str) -> dict:
        """Get metadata for a specific season."""
        return self._get(f"/v1/season/{season}")

    # ── Teams ──

    def get_teams(
        self,
        season: str = "2025",
        metric: str = "norm_epa",
        ascending: bool = False,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> PaginatedResponse:
        """List all teams in a season, sorted by a metric."""
        return self._paginated("/v1/teams", {
            "season": season, "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset, "search": search,
        })

    def get_team(self, team: int, season: str = "2025") -> dict:
        """Get full EPA breakdown for a single team, including match history."""
        return self._get(f"/v1/team/{team}", {"season": season})

    def get_team_events(
        self,
        team: int,
        season: str = "2025",
        event_type: str | None = None,
        metric: str = "epa_mean",
        ascending: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse:
        """Get all events a team participated in, with per-event EPA stats."""
        return self._paginated(f"/v1/team/{team}/events", {
            "season": season, "event_type": event_type,
            "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset,
        })

    def get_team_matches(
        self,
        team: int,
        season: str = "2025",
        event: str | None = None,
        elim: bool | None = None,
        metric: str = "match_id",
        ascending: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse:
        """Get all matches for a team with pre/post EPA and win probability."""
        return self._paginated(f"/v1/team/{team}/matches", {
            "season": season, "event": event, "elim": elim,
            "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset,
        })

    def get_team_info(self, team: int) -> dict:
        """Get team metadata from FTC Scout (name, location, website)."""
        return self._get(f"/v1/team/{team}/info")

    def get_team_playstyle(
        self, team: int, season: str = "2025", n_clusters: int = 8
    ) -> dict:
        """Get playstyle cluster classification for a team."""
        return self._get(f"/v1/team/{team}/playstyle", {
            "season": season, "n_clusters": n_clusters,
        })

    def get_team_trajectory(self, team: int, season: str = "2025") -> dict:
        """Get EPA growth trajectory for a team across their matches."""
        return self._get(f"/v1/team/{team}/trajectory", {"season": season})

    # ── Events ──

    def get_events(
        self,
        season: str = "2025",
        event_type: str | None = None,
        metric: str = "epa_max",
        ascending: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResponse:
        """List all events in a season with aggregate EPA stats."""
        return self._paginated("/v1/events", {
            "season": season, "event_type": event_type,
            "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset,
        })

    def get_event(self, event_code: str, season: str = "2025") -> dict:
        """Get all teams and their EPA stats for a specific event."""
        return self._get(f"/v1/event/{event_code}", {"season": season})

    def get_event_matches(
        self,
        event_code: str,
        season: str = "2025",
        elim: bool | None = None,
        metric: str = "match_id",
        ascending: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedResponse:
        """Get all matches for an event with per-team EPA deltas."""
        return self._paginated(f"/v1/event/{event_code}/matches", {
            "season": season, "elim": elim,
            "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset,
        })

    def get_events_info(
        self, season: str = "2025", event_type: str | None = None
    ) -> PaginatedResponse:
        """List all events with FTC Scout metadata and ScoutKick EPA data."""
        return self._paginated("/v1/events/info", {
            "season": season, "event_type": event_type,
        })

    def get_event_info(self, event_code: str, season: str = "2025") -> dict:
        """Get extended event metadata merged with EPA data."""
        return self._get(f"/v1/event/{event_code}/info", {"season": season})

    # ── Matches ──

    def get_matches(
        self,
        season: str = "2025",
        event: str | None = None,
        elim: bool | None = None,
        team: int | None = None,
        metric: str = "processed_at",
        ascending: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> PaginatedResponse:
        """List matches with pre/post EPA and win probability."""
        return self._paginated("/v1/matches", {
            "season": season, "event": event, "elim": elim, "team": team,
            "metric": metric, "ascending": ascending,
            "limit": limit, "offset": offset,
        })

    def get_match(self, event_code: str, match_id: str, season: str = "2025") -> dict:
        """Get detailed EPA data for all teams in a specific match."""
        return self._get(f"/v1/match/{event_code}/{match_id}", {"season": season})

    # ── Predict ──

    def predict(
        self,
        red: list[int],
        blue: list[int],
        season: str = "2025",
    ) -> dict:
        """Predict match outcome between two alliances.

        Args:
            red: Two team numbers on the red alliance.
            blue: Two team numbers on the blue alliance.
            season: Season year.

        Returns:
            Dict with team data, win probabilities, and predicted scores.
        """
        return self._get("/v1/predict", {
            "red": ",".join(str(t) for t in red),
            "blue": ",".join(str(t) for t in blue),
            "season": season,
        })

    def compare(self, teams: list[int], season: str = "2025") -> dict:
        """Compare multiple teams side by side.

        Args:
            teams: Two or more team numbers to compare.
            season: Season year.

        Returns:
            Dict with component breakdown for each team.
        """
        return self._get("/v1/compare", {
            "teams": ",".join(str(t) for t in teams),
            "season": season,
        })

    # ── Pipeline ──

    def run_pipeline(self, season: str | None = None) -> dict:
        """Trigger the EPA pipeline for one or all seasons.

        Args:
            season: Specific season to run, or None for all cached seasons.

        Returns:
            Dict with status and list of seasons being processed.
        """
        if season:
            return self._post(f"/v1/data/run/{season}")
        return self._post("/v1/data/run")

    def get_pipeline_status(self) -> dict:
        """Get current pipeline state (running / done / pending)."""
        return self._get("/v1/data/status")

    # ── Clusters & Complementarity ──

    def get_clusters(self, season: str = "2025", n_clusters: int = 8) -> dict:
        """Compute playstyle clusters for all teams."""
        return self._get("/v1/clusters", {
            "season": season, "n_clusters": n_clusters,
        })

    def get_complementarity(
        self, team1: int, team2: int, season: str = "2025"
    ) -> dict:
        """Compute complementarity score between two teams."""
        return self._get("/v1/complementarity", {
            "team1": team1, "team2": team2, "season": season,
        })

    def get_alliance_partners(
        self, team: int, season: str = "2025", top_n: int = 10
    ) -> dict:
        """Find best alliance partners for a team based on playstyle."""
        return self._get(f"/v1/complementarity/{team}/partners", {
            "season": season, "top_n": top_n,
        })

    def get_trajectory_clusters(
        self, season: str = "2025", n_clusters: int = 4
    ) -> dict:
        """Compute growth trajectory clusters based on EPA evolution."""
        return self._get("/v1/trajectory/clusters", {
            "season": season, "n_clusters": n_clusters,
        })

    # ── Site (frontend bundles) ──

    def get_site_teams_all(self) -> list[dict]:
        """Lightweight list of all teams with name (for autocomplete)."""
        return self._get("/v1/site/teams/all")

    def get_site_events_all(self, season: str = "2025") -> list[dict]:
        """Lightweight list of events with name, start, end dates."""
        return self._get("/v1/site/events/all", {"season": season})

    def get_site_team(self, team: int, season: str = "2025") -> dict:
        """Bundled team page: info + EPA + ranks + matches + season meta."""
        return self._get(f"/v1/site/team/{team}", {"season": season})

    def get_site_event(self, event_code: str, season: str = "2025") -> dict:
        """Bundled event page: standings + qual/elim matches + season meta."""
        return self._get(f"/v1/site/event/{event_code}", {"season": season})

    def get_site_match(
        self, event_code: str, match_id: str, season: str = "2025"
    ) -> dict:
        """Bundled match page: per-team EPA + event name + season meta."""
        return self._get(
            f"/v1/site/match/{event_code}/{match_id}", {"season": season}
        )

    # ── helpers ──

    def _post(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, method="POST")
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = _try_decode_error(e)
            raise ScoutKickError(f"HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise ScoutKickError(f"Connection failed: {e.reason}") from None


def _try_decode_error(e: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(e.read().decode())
        return body.get("detail", str(body))
    except Exception:
        return e.reason or str(e)
