import time
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class MTTRTracker:
    """
    Tracks Mean Time to Remediate (MTTR) - The Defense Paradigm metric.
    Answers: How fast can the agent respond to an incident?
    """
    start_time: float = field(default_factory=time.time)
    phase_times: Dict[str, float] = field(default_factory=dict)
    _phase_start: Optional[float] = None
    _current_phase: Optional[str] = None

    def start_phase(self, phase_name: str):
        """Mark the start of a phase (e.g., 'orient', 'plan', 'code', 'critic')."""
        if self._current_phase:
            self.end_phase()
        self._phase_start = time.time()
        self._current_phase = phase_name

    def end_phase(self):
        """Mark the end of the current phase."""
        if self._phase_start and self._current_phase:
            elapsed = time.time() - self._phase_start
            self.phase_times[self._current_phase] = elapsed
            self._current_phase = None
            self._phase_start = None

    def total_time(self) -> float:
        """Total elapsed time from start."""
        return time.time() - self.start_time

    def get_mttr_score(self, target_seconds=60) -> int:
        """
        Calculate MTTR score (0-100).
        Score = 100 if total_time <= target, decreases linearly to 0 at 10x target.
        """
        total = self.total_time()
        if total <= target_seconds:
            return 100
        elif total >= target_seconds * 10:
            return 0
        else:
            # Linear decay from 100 to 0
            return int(100 - ((total - target_seconds) / (target_seconds * 9)) * 100)

    def summary(self) -> dict:
        return {
            "total_seconds": round(self.total_time(), 2),
            "phase_breakdown": {k: round(v, 2) for k, v in self.phase_times.items()},
            "mttr_score": self.get_mttr_score()
        }
