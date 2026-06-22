import logging
import numpy as np
from backend.src.data.cleaner import BaseCleaner
from backend.src.data.read_ftcscout import get_matches
from backend.src.storage import create_storage

logging.basicConfig(level=logging.WARNING)


def validate_season(season_id: str):
    cleaner = BaseCleaner.get_cleaner(season_id)
    raw = get_matches(cleaner, cache=True)

    outcomes = {}
    for m in raw:
        rs = m["red_scores"].get("totalPointsNp", 0)
        bs = m["blue_scores"].get("totalPointsNp", 0)
        if rs == bs:
            continue
        outcomes[(m["event"], str(m["match_id"]))] = {
            "red_won": rs > bs,
            "red_teams": m["red_teams"],
            "blue_teams": m["blue_teams"],
        }

    storage = create_storage(season_id)
    all_teams = storage.load_all_teams()
    if not all_teams:
        return None

    preds, actuals = [], []
    missed = 0
    for team in all_teams:
        matches = storage.load_team_matches(team)
        for m in matches:
            key = (m["event_code"], m["match_id"])
            outcome = outcomes.get(key)
            if outcome is None:
                missed += 1
                continue
            team_won = (
                (team in outcome["red_teams"] and outcome["red_won"])
                or (team in outcome["blue_teams"] and not outcome["red_won"])
            )
            preds.append(m["win_prob"])
            actuals.append(1.0 if team_won else 0.0)

    preds = np.array(preds)
    actuals = np.array(actuals)
    n = len(preds)
    if n == 0:
        return None

    brier = np.mean((preds - actuals) ** 2)
    log_loss = -np.mean(
        actuals * np.log(np.clip(preds, 1e-15, 1))
        + (1 - actuals) * np.log(np.clip(1 - preds, 1e-15, 1))
    )
    accuracy = np.mean((preds > 0.5).astype(float) == actuals)
    avg_pred = np.mean(preds)
    base_rate = np.mean(actuals)

    print(f"\nSeason {season_id}:")
    print(f"  Matches:        {n}")
    if missed:
        print(f"  Skipped (tie):  {missed}")
    print(f"  Avg prediction: {avg_pred:.4f}")
    print(f"  Base win rate:  {base_rate:.4f}")
    print(f"  Accuracy:       {accuracy:.4f}")
    print(f"  Brier score:    {brier:.4f}  (0=perfect, 0.25=naive)")
    print(f"  Log loss:       {log_loss:.4f}  (0=perfect)")

    bins = np.linspace(0, 1, 11)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_acc = []
    bin_counts = []
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        mask = (preds >= lo) & (preds < hi)
        count = mask.sum()
        bin_counts.append(count)
        bin_acc.append(actuals[mask].mean() if count > 0 else np.nan)

    ece = np.nansum(
        np.array(bin_counts)
        * np.abs(np.array(bin_acc) - bin_centers)
    ) / max(n, 1)
    print(f"  ECE:            {ece:.4f}  (Expected Calibration Error)")

    print(f"\n  Calibration:")
    print(f"  {'Bin':>10s}  {'Count':>6s}  {'Win Rate':>9s}  {'Expected':>9s}")
    for i in range(len(bins) - 1):
        exp = bin_centers[i]
        actual_val = bin_acc[i]
        bar = "#" * int(actual_val * 20) if not np.isnan(actual_val) else "-"
        print(
            f"  {bins[i]:.1f}-{bins[i+1]:.1f}"
            f"  {bin_counts[i]:>6d}"
            f"  {actual_val if not np.isnan(actual_val) else float('nan'):>9.4f}"
            f"  {exp:>9.4f}  {bar}"
        )
    return {"season": season_id, "n": n, "accuracy": accuracy, "brier": brier, "ece": ece}


if __name__ == "__main__":
    results = []
    for s in ["2025"]:
        r = validate_season(s)
        if r:
            results.append(r)
    if results:
        print(f"\n{'='*60}")
        print(f"  Summary")
        print(f"{'='*60}")
        print(f"  {'Season':>6s}  {'Matches':>8s}  {'Accuracy':>9s}  {'Brier':>7s}  {'ECE':>7s}")
        for r in results:
            print(f"  {r['season']:>6s}  {r['n']:>8d}  {r['accuracy']:>9.4f}  {r['brier']:>7.4f}  {r['ece']:>7.4f}")
