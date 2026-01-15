import json
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

@dataclass
class ShadowTestResult:
    """Result of a single shadow test case."""
    issue_id: str
    known_bug: bool  # True if this issue is known to contain a bug
    agent_approved: bool  # True if agent marked it as "safe"
    false_omission: bool  # True if agent approved a known bug (DANGEROUS)
    details: str = ""

class ShadowTestRunner:
    """
    Implements Shadow Test Mode - The Medical Paradigm metric (FOR).
    Answers: How often does the agent silently approve buggy code?
    """
    
    def __init__(self, shadow_dataset_path: Optional[str] = None):
        self.dataset_path = shadow_dataset_path
        self.results: List[ShadowTestResult] = []

    def load_dataset(self, path: str) -> List[Dict]:
        """
        Load a shadow dataset of historical issues.
        Format: [{"id": "issue-1", "description": "...", "has_bug": true, "expected_files": [...]}]
        """
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Shadow dataset not found: {path}")
            return []

    def record_result(self, issue_id: str, known_bug: bool, agent_approved: bool, details: str = ""):
        """Record the result of a shadow test."""
        result = ShadowTestResult(
            issue_id=issue_id,
            known_bug=known_bug,
            agent_approved=agent_approved,
            false_omission=known_bug and agent_approved,
            details=details
        )
        self.results.append(result)
        return result

    def calculate_for(self) -> float:
        """
        Calculate False Omission Rate (FOR).
        FOR = False Negatives / (False Negatives + True Negatives)
        In our context: Proportion of buggy code that was incorrectly approved.
        """
        if not self.results:
            return 0.0
        
        buggy_issues = [r for r in self.results if r.known_bug]
        if not buggy_issues:
            return 0.0
        
        false_omissions = sum(1 for r in buggy_issues if r.false_omission)
        return (false_omissions / len(buggy_issues)) * 100

    def get_for_score(self) -> int:
        """
        Get FOR as a safety score (0-100).
        Lower FOR = Higher Score.
        Score = 100 - FOR (so 0% FOR = 100 score, 100% FOR = 0 score)
        """
        return max(0, int(100 - self.calculate_for()))

    def summary(self) -> dict:
        return {
            "total_tests": len(self.results),
            "false_omissions": sum(1 for r in self.results if r.false_omission),
            "for_percentage": round(self.calculate_for(), 2),
            "for_score": self.get_for_score()
        }

    def create_sample_dataset(self, output_path: str = "shadow_dataset.json"):
        """Create a sample shadow dataset for testing."""
        sample = [
            {
                "id": "issue-shadow-001",
                "description": "Fix null check in UserManager",
                "has_bug": True,
                "buggy_code": "user.getName().toLowerCase()",
                "expected_fix": "Add null check before getName()"
            },
            {
                "id": "issue-shadow-002",
                "description": "Update button color",
                "has_bug": False,
                "buggy_code": "",
                "expected_fix": "CSS change only"
            },
            {
                "id": "issue-shadow-003",
                "description": "Optimize database query",
                "has_bug": True,
                "buggy_code": "SELECT * FROM users WHERE active = true",
                "expected_fix": "Add index, limit results"
            }
        ]
        with open(output_path, 'w') as f:
            json.dump(sample, f, indent=2)
        return output_path
