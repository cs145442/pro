"""
Technical Debt Tracker - Financial Paradigm metric.

Tracks Refactoring-to-Feature ratio over time to prevent technical bankruptcy.
Stores longitudinal data in SQLite for trend analysis.

Purpose: Ensure sustainable development pace with adequate refactoring.
Threshold: 20-30% of work should be refactoring (per README)
"""

import sqlite3
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import re
import logging

logger = logging.getLogger(__name__)

class TechnicalDebtTracker:
    """
    Tracks Technical Debt Ratio (TDR) across runs.
    
    TDR = (refactoring_commits / total_commits) * 100
    
    Classifies work as:
    - 'refactoring': Code cleanup, reorganization, optimization
    - 'feature': New functionality, bug fixes
    
    Stores in SQLite for longitudinal analysis (30-day rolling average).
    """
    
    def __init__(self, db_path: str = "/data/metrics.db"):
        """
        Initialize tracker with SQLite database.
        
        Args:
            db_path: Path to SQLite database (default: /data/metrics.db for Docker volume)
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create database tables if they don't exist."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Work history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                work_type TEXT NOT NULL,  -- 'refactoring' or 'feature'
                ces_score INTEGER,
                loc_changed INTEGER,
                description TEXT
            )
        ''')
        
        # TDR snapshot table (for caching rolling averages)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tdr_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                total_commits INTEGER,
                refactor_commits INTEGER,
                feature_commits INTEGER,
                tdr_ratio REAL,
                period_days INTEGER DEFAULT 30
            )
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info(f"TDR database initialized at {self.db_path}")
    
    def classify_work_type(
        self, 
        issue_description: str, 
        diff: str = "",
        plan: List[str] = None
    ) -> str:
        """
        Classify work as 'refactoring' or 'feature'.
        
        Uses keyword matching on issue description, diff, and plan.
        
        Args:
            issue_description: The issue/task description
            diff: Generated code diff (optional)
            plan: Agent's plan steps (optional)
        
        Returns:
            'refactoring' or 'feature'
        """
        # Refactoring keywords
        refactor_keywords = [
            'refactor', 'cleanup', 'clean up', 'reorganize', 'rename',
            'extract method', 'extract class', 'simplify', 'optimize structure',
            'remove duplication', 'improve readability', 'restructure',
            'consolidate', 'split', 'modularize', 'decouple'
        ]
        
        # Feature/bugfix keywords
        feature_keywords = [
            'add', 'new feature', 'implement', 'create', 'introduce',
            'support for', 'enable', 'fix bug', 'bug fix', 'resolve',
            'enhance', 'improve performance', 'optimize speed',
            'update', 'upgrade', 'patch'
        ]
        
        description_lower = issue_description.lower()
        
        # Count keyword matches
        refactor_matches = sum(1 for kw in refactor_keywords if kw in description_lower)
        feature_matches = sum(1 for kw in feature_keywords if kw in description_lower)
        
        # Check plan for refactoring signals
        if plan:
            plan_text = ' '.join(plan).lower()
            if 'refactor' in plan_text or 'cleanup' in plan_text:
                refactor_matches += 2  # Weight plan heavily
        
        # Check diff patterns
        if diff:
            # If mostly deleting code (cleanup)
            additions = diff.count('\n+')
            deletions = diff.count('\n-')
            if deletions > additions * 1.5:  # More deletions = likely cleanup
                refactor_matches += 1
            
            # If only test files modified (likely refactoring)
            test_pattern = r'\+\+\+ b/(test|spec)/'
            if re.search(test_pattern, diff) and not re.search(r'\+\+\+ b/src/', diff):
                refactor_matches += 1
        
        # Decision
        if refactor_matches > feature_matches:
            return 'refactoring'
        else:
            return 'feature'
    
    def record_work(
        self,
        issue_id: str,
        work_type: str,
        ces_score: int,
        loc_changed: int,
        description: str = ""
    ):
        """
        Record a completed work item.
        
        Args:
            issue_id: Unique identifier for the work
            work_type: 'refactoring' or 'feature'
            ces_score: Final CES score achieved
            loc_changed: Lines of code changed
            description: Optional description
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO work_history (issue_id, work_type, ces_score, loc_changed, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (issue_id, work_type, ces_score, loc_changed, description))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Recorded {work_type} work: {issue_id}")
    
    def calculate_tdr(self, period_days: int = 30) -> Dict[str, any]:
        """
        Calculate Technical Debt Ratio for the specified period.
        
        Args:
            period_days: Number of days to look back (default: 30)
        
        Returns:
            {
                "tdr_ratio": float (0-100),
                "total_commits": int,
                "refactor_commits": int,
                "feature_commits": int,
                "period_days": int,
                "recommendation": str
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get work history for the period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        
        cursor.execute('''
            SELECT work_type, COUNT(*) 
            FROM work_history 
            WHERE timestamp >= ?
            GROUP BY work_type
        ''', (cutoff_date,))
        
        results = cursor.fetchall()
        conn.close()
        
        # Count by type
        refactor_commits = 0
        feature_commits = 0
        
        for work_type, count in results:
            if work_type == 'refactoring':
                refactor_commits = count
            elif work_type == 'feature':
                feature_commits = count
        
        total_commits = refactor_commits + feature_commits
        
        if total_commits == 0:
            # No data yet
            return {
                "tdr_ratio": 0.0,
                "total_commits": 0,
                "refactor_commits": 0,
                "feature_commits": 0,
                "period_days": period_days,
                "recommendation": "Insufficient data to calculate TDR"
            }
        
        tdr_ratio = (refactor_commits / total_commits * 100)
        
        # Store snapshot
        self._save_snapshot(total_commits, refactor_commits, feature_commits, tdr_ratio, period_days)
        
        # Generate recommendation
        recommendation = self._get_recommendation(tdr_ratio)
        
        return {
            "tdr_ratio": round(tdr_ratio, 2),
            "total_commits": total_commits,
            "refactor_commits": refactor_commits,
            "feature_commits": feature_commits,
            "period_days": period_days,
            "recommendation": recommendation
        }
    
    def _save_snapshot(
        self,
        total: int,
        refactor: int,
        feature: int,
        tdr: float,
        period: int
    ):
        """Save TDR snapshot for trend analysis."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tdr_snapshot (total_commits, refactor_commits, feature_commits, tdr_ratio, period_days)
            VALUES (?, ?, ?, ?, ?)
        ''', (total, refactor, feature, tdr, period))
        
        conn.commit()
        conn.close()
    
    def _get_recommendation(self, tdr_ratio: float) -> str:
        """Generate recommendation based on TDR."""
        if tdr_ratio < 10:
            return "CRITICAL: Too little refactoring (< 10%). Technical debt accumulating rapidly."
        elif tdr_ratio < 20:
            return "WARNING: Below recommended threshold. Increase refactoring work."
        elif 20 <= tdr_ratio <= 30:
            return "HEALTHY: TDR within recommended range (20-30%)."
        elif 30 < tdr_ratio <= 40:
            return "ACCEPTABLE: Slightly high refactoring, but sustainable."
        else:
            return "CAUTION: Very high refactoring ratio (> 40%). May indicate systemic issues."
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """
        Get recent work history.
        
        Args:
            limit: Number of recent items to return
        
        Returns:
            List of work items with metadata
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT issue_id, timestamp, work_type, ces_score, loc_changed, description
            FROM work_history
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "issue_id": row[0],
                "timestamp": row[1],
                "work_type": row[2],
                "ces_score": row[3],
                "loc_changed": row[4],
                "description": row[5]
            }
            for row in rows
        ]
    
    def get_summary_string(self) -> str:
        """Generate human-readable TDR summary."""
        tdr_data = self.calculate_tdr()
        
        summary = f"Technical Debt Ratio (TDR): {tdr_data['tdr_ratio']:.1f}%\n"
        summary += f"Last {tdr_data['period_days']} days: "
        summary += f"{tdr_data['total_commits']} commits "
        summary += f"({tdr_data['refactor_commits']} refactoring, {tdr_data['feature_commits']} features)\n"
        summary += f"Recommendation: {tdr_data['recommendation']}"
        
        return summary
