"""
Session Guard — tracks daily application counts and session limits to reduce LinkedIn ban risk.
State is persisted in job_applications/session_guard.json so it survives across bot runs.
"""
import json
import random
from datetime import datetime
from pathlib import Path
from src.logging import logger

import config as cfg

GUARD_PATH = Path("job_applications/session_guard.json")


class SessionGuard:
    """
    Tracks daily usage and enforces limits that keep the bot within safe LinkedIn thresholds.

    Key behaviours:
    - Caps total applications at cfg.DAILY_APPLICATION_LIMIT per calendar day
    - Caps bot sessions at cfg.MAX_SESSIONS_PER_DAY per calendar day
    - Generates a random 2-10 min wait that shifts every day (daily seed) AND
      every application (per-call entropy), so LinkedIn never sees a fixed rhythm
    """

    def __init__(self):
        self.today = datetime.now().strftime("%Y-%m-%d")
        self._state = self._load()
        self._ensure_today()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        GUARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        if GUARD_PATH.exists():
            try:
                with open(GUARD_PATH) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        with open(GUARD_PATH, "w") as f:
            json.dump(self._state, f, indent=2)

    def _ensure_today(self):
        if self.today not in self._state:
            self._state[self.today] = {"applications": 0, "sessions": 0}
            self._save()

    # ------------------------------------------------------------------ #
    # Session management                                                   #
    # ------------------------------------------------------------------ #

    def start_session(self) -> bool:
        """
        Called once at the start of each bot run.
        Returns True if the session is allowed, False if limits are already hit today.
        """
        day = self._state[self.today]
        if day["sessions"] >= cfg.MAX_SESSIONS_PER_DAY:
            logger.warning(
                f"Session limit reached: {day['sessions']}/{cfg.MAX_SESSIONS_PER_DAY} sessions today. "
                "Try again tomorrow."
            )
            return False
        if day["applications"] >= cfg.DAILY_APPLICATION_LIMIT:
            logger.warning(
                f"Daily application limit reached: {day['applications']}/{cfg.DAILY_APPLICATION_LIMIT}. "
                "Try again tomorrow."
            )
            return False

        day["sessions"] += 1
        self._save()
        logger.info(
            f"Session {day['sessions']}/{cfg.MAX_SESSIONS_PER_DAY} started. "
            f"Applications today: {day['applications']}/{cfg.DAILY_APPLICATION_LIMIT}"
        )
        return True

    def can_apply(self) -> bool:
        """Returns True if we haven't hit the daily application cap."""
        return self._state[self.today]["applications"] < cfg.DAILY_APPLICATION_LIMIT

    def record_application(self):
        """Increment the daily application counter after a successful application."""
        self._state[self.today]["applications"] += 1
        self._save()
        remaining = self.remaining_today()
        logger.info(f"Application recorded. Remaining today: {remaining}/{cfg.DAILY_APPLICATION_LIMIT}")

    def remaining_today(self) -> int:
        """How many more applications are allowed today."""
        return max(0, cfg.DAILY_APPLICATION_LIMIT - self._state[self.today]["applications"])

    # ------------------------------------------------------------------ #
    # Human-like wait time                                                 #
    # ------------------------------------------------------------------ #

    def next_wait_seconds(self) -> int:
        """
        Return a random wait time between MINIMUM_WAIT_TIME_IN_SECONDS and
        MAXIMUM_WAIT_TIME_IN_SECONDS (2-10 min by default).

        Uses a seed composed of today's date + current application count so:
        - The distribution shifts every calendar day (no fixed rhythm day-to-day)
        - Each application within a session gets a different wait
        - Two separate runs on the same day still get varied delays
        """
        apps_so_far = self._state[self.today]["applications"]
        seed = int(self.today.replace("-", "")) + apps_so_far + random.randint(0, 999)
        rng = random.Random(seed)
        wait = rng.randint(cfg.MINIMUM_WAIT_TIME_IN_SECONDS, cfg.MAXIMUM_WAIT_TIME_IN_SECONDS)
        logger.info(f"Next wait: {wait}s ({wait // 60}m {wait % 60}s)")
        return wait

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def status(self) -> str:
        day = self._state[self.today]
        return (
            f"Today ({self.today}): "
            f"{day['applications']}/{cfg.DAILY_APPLICATION_LIMIT} applications, "
            f"{day['sessions']}/{cfg.MAX_SESSIONS_PER_DAY} sessions"
        )
