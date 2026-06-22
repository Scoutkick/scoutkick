import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_all")

from backend.src.services.pipeline_service import EPAPipeline

SEASONS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]

def main():
    logger.info("=== Running EPA Pipeline for ALL Seasons ===")
    for s in SEASONS:
        logger.info("═══════════════════════════════════════════")
        logger.info(">>> Season %s <<<", s)
        try:
            pipeline = EPAPipeline(s, calibrate=True)
            engine = pipeline.run()
            if engine:
                epas = list(engine.epas.items())
                if epas:
                    team, sn = epas[0]
                    logger.info("  Sample Team %s: mean_total=%.2f (n=%.0f)", team, sn.mean[0], sn.n)
            logger.info(">>> Season %s complete <<<", s)
        except Exception as e:
            logger.exception("Season %s FAILED: %s", s, e)
    logger.info("=== All seasons complete ===")

if __name__ == "__main__":
    main()
