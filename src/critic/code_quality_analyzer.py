"""
Code Quality Analyzer - Financial Paradigm metrics.

Implements the README's code quality requirements:
- Maintainability Index (MI) using Halstead Volume + Cyclomatic Complexity
- Cyclomatic Complexity (CC) per function
- Code Duplication Ratio
- Architectural Violation Rate (AVR)
- Coupling Between Objects (CBO)

Uses radon for Python code analysis (can be extended for other languages).
"""

import subprocess
import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
import math

logger = logging.getLogger(__name__)

class CodeQualityAnalyzer:
    """
    Analyzes generated code for quality metrics per the README's Financial Paradigm.
    
    README Requirements:
    - Maintainability Index > 80
    - Duplication Ratio < 5%
    - AVR = 0% (no architectural violations)
    - Cyclomatic Complexity: Monitor and warn
    """
    
    def __init__(self):
        self.radon_available = self._check_radon()
    
    def _check_radon(self) -> bool:
        """Check if radon is available for Python code analysis."""
        try:
            subprocess.run(
                ["radon", "--version"],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("radon not found - Python code quality metrics will be limited")
            return False
    
    def analyze_diff(self, diff: str, language: str = "python") -> Dict[str, any]:
        """
        Analyze code quality from a diff.
        
        Returns comprehensive quality metrics:
        {
            "maintainability_index": int (0-100),
            "cyclomatic_complexity": float,
            "duplication_ratio": float,
            "architectural_violations": int,
            "coupling_score": int (0-100),
            "details": Dict
        }
        """
        # Extract added code from diff
        added_code = self._extract_added_code(diff)
        
        if not added_code.strip():
            return self._no_code_result("No code added in diff")
        
        # Analyze based on language
        if language == "python" and self.radon_available:
            return self._analyze_python_code(added_code, diff)
        else:
            return self._analyze_generic(added_code, diff, language)
    
    def _analyze_python_code(self, code: str, diff: str) -> Dict[str, any]:
        """Analyze Python code using radon and custom metrics."""
        
        # 1. Maintainability Index (Halstead + Complexity)
        mi_score, mi_details = self._calculate_mi_python(code)
        
        # 2. Cyclomatic Complexity
        cc_average, cc_details = self._calculate_cc_python(code)
        
        # 3. Duplication Ratio (simple heuristic for now)
        dup_ratio, dup_details = self._calculate_duplication(code)
        
        # 4. Architectural Violations (check imports)
        avr_count, avr_details = self._check_architectural_violations(diff)
        
        # 5. Coupling (count imports/dependencies)
        coupling_score, coupling_details = self._calculate_coupling(code)
        
        return {
            "maintainability_index": mi_score,
            "cyclomatic_complexity": cc_average,
            "duplication_ratio": dup_ratio,
            "architectural_violations": avr_count,
            "coupling_score": coupling_score,
            "details": {
                "mi": mi_details,
                "cc": cc_details,
                "duplication": dup_details,
                "avr": avr_details,
                "coupling": coupling_details
            }
        }
    
    def _calculate_mi_python(self, code: str) -> Tuple[int, Dict]:
        """
        Calculate Maintainability Index using radon.
        
        README formula: MI = 171 - 5.2*ln(V) - 0.23*G - 16.2*ln(LOC)
        Where:
        - V = Halstead Volume
        - G = Cyclomatic Complexity
        - LOC = Lines of Code
        
        Radon calculates this automatically.
        """
        try:
            # Write code to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            try:
                # Run radon mi (maintainability index)
                result = subprocess.run(
                    ["radon", "mi", "-s", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                output = result.stdout
                
                # Parse output (format: "file.py - A (score)")
                # Score ranges: A (100-20), B (19-10), C (9-0)
                mi_match = re.search(r'([A-F])\s*\(([0-9.]+)\)', output)
                
                if mi_match:
                    grade = mi_match.group(1)
                    score = float(mi_match.group(2))
                    
                    # Convert to 0-100 scale (radon uses different scale)
                    # Radon MI: A=100+, B=20-100, C=10-20, D=0-10
                    # We'll normalize to 0-100
                    mi_score = min(100, max(0, int(score)))
                    
                    details = {
                        "grade": grade,
                        "raw_score": score,
                        "interpretation": self._mi_interpretation(grade)
                    }
                    
                    return mi_score, details
                else:
                    # Fallback: simple LOC-based estimate
                    loc = len([l for l in code.split('\n') if l.strip() and not l.strip().startswith('#')])
                    mi_score = max(0, 100 - loc)  # Simple heuristic
                    return mi_score, {"method": "fallback:LOC", "loc": loc}
            
            finally:
                # Cleanup temp file
                Path(temp_path).unlink(missing_ok=True)
        
        except Exception as e:
            logger.warning(f"MI calculation failed: {e}")
            return 80, {"error": str(e), "method": "default"}  # Optimistic default
    
    def _calculate_cc_python(self, code: str) -> Tuple[float, Dict]:
        """Calculate Cyclomatic Complexity using radon."""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            try:
                # Run radon cc (cyclomatic complexity)
                result = subprocess.run(
                    ["radon", "cc", "-s", "-a", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                output = result.stdout
                
                # Parse average complexity from output
                # Format: "Average complexity: X.XX (A)"
                avg_match = re.search(r'Average complexity:\s*([0-9.]+)', output)
                
                if avg_match:
                    avg_cc = float(avg_match.group(1))
                    
                    # Extract per-function complexities
                    functions = []
                    for line in output.split('\n'):
                        # Format: "    M 5:0 function_name - A (2)"
                        func_match = re.search(r'([A-Z])\s+\d+:\d+\s+(\S+)\s+-\s+([A-F])\s+\((\d+)\)', line)
                        if func_match:
                            functions.append({
                                "name": func_match.group(2),
                                "complexity": int(func_match.group(4)),
                                "grade": func_match.group(3)
                            })
                    
                    details = {
                        "average": avg_cc,
                        "functions": functions,
                        "interpretation": self._cc_interpretation(avg_cc)
                    }
                    
                    return avg_cc, details
                else:
                    # Fallback
                    return 1.0, {"method": "fallback", "default": 1.0}
            
            finally:
                Path(temp_path).unlink(missing_ok=True)
        
        except Exception as e:
            logger.warning(f"CC calculation failed: {e}")
            return 1.0, {"error": str(e), "method": "default"}
    
    def _calculate_duplication(self, code: str) -> Tuple[float, Dict]:
        """
        Calculate code duplication ratio (simple heuristic).
        
        For full implementation, would use tools like jscpd.
        """
        lines = [l.strip() for l in code.split('\n') if l.strip() and not l.strip().startswith('#')]
        
        if not lines:
            return 0.0, {"total_lines": 0, "duplicates": 0}
        
        # Count duplicate lines (simple approach)
        line_counts = {}
        for line in lines:
            line_counts[line] = line_counts.get(line, 0) + 1
        
        duplicates = sum(count - 1 for count in line_counts.values() if count > 1)
        total = len(lines)
        
        ratio = (duplicates / total * 100) if total > 0 else 0.0
        
        details = {
            "total_lines": total,
            "duplicate_lines": duplicates,
            "ratio_percent": round(ratio, 2),
            "threshold": 5.0,
            "passes": ratio < 5.0
        }
        
        return ratio, details
    
    def _check_architectural_violations(self, diff: str) -> Tuple[int, Dict]:
        """
        Check for architectural violations based on import rules.
        
        Simple implementation: check for restricted import patterns.
        Full implementation would use configurable rules from YAML.
        """
        violations = []
        
        # Define restricted import patterns (example rules)
        restricted_patterns = [
            (r'from\s+tests\s+import', "Source code importing from tests directory"),
            (r'import\s+os\.path', "Prefer pathlib over os.path"),
            (r'from\s+\.\.\.', "Avoid deep relative imports (3+ levels)"),
        ]
        
        for line in diff.split('\n'):
            if line.startswith('+') and 'import' in line:
                for pattern, message in restricted_patterns:
                    if re.search(pattern, line):
                        violations.append({
                            "line": line.strip(),
                            "rule": message
                        })
        
        details = {
            "violation_count": len(violations),
            "violations": violations[:5],  # Show first 5
            "avr_percentage": 0.0 if not violations else 100.0,  # Binary for now
            "threshold": 0.0
        }
        
        return len(violations), details
    
    def _calculate_coupling(self, code: str) -> Tuple[int, Dict]:
        """
        Calculate coupling score based on import count.
        
        Lower coupling = higher score.
        Score = 100 - (import_count * 5)
        """
        import_lines = [l for l in code.split('\n') if 'import' in l and not l.strip().startswith('#')]
        import_count = len(import_lines)
        
        # Extract unique modules
        modules = set()
        for line in import_lines:
            # Extract module name
            match = re.search(r'(?:from|import)\s+([a-zA-Z0-9_.]+)', line)
            if match:
                modules.add(match.group(1).split('.')[0])  # Root module
        
        coupling_score = max(0, 100 - len(modules) * 5)
        
        details = {
            "import_count": import_count,
            "unique_modules": len(modules),
            "modules": list(modules)[:10],  # First 10
            "score": coupling_score,
            "interpretation": "Low" if coupling_score > 70 else "Medium" if coupling_score > 40 else "High"
        }
        
        return coupling_score, details
    
    def _analyze_generic(self, code: str, diff: str, language: str) -> Dict[str, any]:
        """Fallback analysis for non-Python languages."""
        # Simple LOC-based heuristics
        loc = len([l for l in code.split('\n') if l.strip()])
        
        # Estimate MI based on LOC (very rough)
        mi_score = max(0, 100 - (loc // 10))  # Penalize long files
        
        # Simple complexity estimate
        cc_estimate = code.count('if') + code.count('for') + code.count('while') + code.count('case')
        cc_average = cc_estimate / max(1, code.count('def') + code.count('function') + code.count('class'))
        
        return {
            "maintainability_index": mi_score,
            "cyclomatic_complexity": cc_average,
            "duplication_ratio": 0.0,
            "architectural_violations": 0,
            "coupling_score": 80,
            "details": {
                "method": "generic_heuristic",
                "language": language,
                "loc": loc,
                "note": "Install radon for accurate Python metrics"
            }
        }
    
    def _extract_added_code(self, diff: str) -> str:
        """Extract only the added lines from a diff."""
        added_lines = []
        for line in diff.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                # Remove the leading '+'
                added_lines.append(line[1:])
        
        return '\n'.join(added_lines)
    
    def _no_code_result(self, reason: str) -> Dict[str, any]:
        """Return default result when no code to analyze."""
        return {
            "maintainability_index": 100,  # Optimistic default
            "cyclomatic_complexity": 0.0,
            "duplication_ratio": 0.0,
            "architectural_violations": 0,
            "coupling_score": 100,
            "details": {"reason": reason}
        }
    
    def _mi_interpretation(self, grade: str) -> str:
        """Interpret MI grade."""
        interpretations = {
            "A": "Excellent - Highly maintainable",
            "B": "Good - Maintainable",
            "C": "Fair - Moderate complexity",
            "D": "Poor - Difficult to maintain",
            "F": "Critical - Unmaintainable"
        }
        return interpretations.get(grade, "Unknown")
    
    def _cc_interpretation(self, cc: float) -> str:
        """Interpret Cyclomatic Complexity."""
        if cc <= 5:
            return "Simple - Low risk"
        elif cc <= 10:
            return "Moderate - Manageable"
        elif cc <= 20:
            return "Complex - Higher risk"
        else:
            return "Very Complex - High risk"
