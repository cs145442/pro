import subprocess
from typing import List, Dict
import json

class SafetyCritic:
    """
    Wraps the Semgrep CLI to enforce the 'Medical Paradigm' (Safety).
    Detects dangerous patterns (SQLi, Thread.stop, etc).
    """
    def __init__(self, rules_path="config/semgrep_rules.yaml"):
        self.rules_path = rules_path

    def scan_diff(self, file_path: str) -> List[str]:
        """
        Runs semgrep on a specific file.
        Returns a list of violation messages.
        """
        try:
            # Command: semgrep --config=config/rules.yaml --json target_file.py
            result = subprocess.run(
                ["semgrep", "--config", self.rules_path, "--json", file_path],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"Semgrep failed: {result.stderr}")
                return ["Semgrep Execution Failed"]
                
            return self._parse_output(result.stdout)
        except FileNotFoundError:
            return ["Semgrep binary not found in PATH"]

    def _parse_output(self, json_output: str) -> List[str]:
        try:
            data = json.loads(json_output)
            violations = []
            if "results" in data:
                for result in data["results"]:
                    msg = result.get("extra", {}).get("message", "Unknown violation")
                    severity = result.get("extra", {}).get("severity", "WARNING")
                    violations.append(f"[{severity}] {msg} (at line {result.get('start', {}).get('line')})")
            return violations
        except json.JSONDecodeError:
            return ["Failed to parse Semgrep JSON output"]
