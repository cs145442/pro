"""
Tool Usage Tracker - Behavioral Paradigm metric.

Tracks all tool invocations (Zoekt, GraphRAG, Sandbox, LLM, Critics) to calculate
Tool Use Success Rate (TUSR).

Purpose: Identify tool reliability issues and agent efficiency in using available tools.
Threshold: TUSR ≥ 80% (industry best practice)
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ToolUsageTracker:
    """
    Tracks all tool invocations and calculates Tool Use Success Rate (TUSR).
    
    TUSR = (successful_invocations / total_invocations) * 100
    
    Instruments all tools in the orchestrator:
    - Zoekt (code search)
    - GraphRAG (dependency search)
    - Sandbox (compile, run)
    - LLM calls (plan, code generation)
    - Critics (safety, compliance, etc.)
    """
    
    def __init__(self):
        self.invocations: List[Dict] = []
        self.start_time = datetime.now()
    
    def log_invocation(
        self, 
        tool_name: str, 
        success: bool, 
        error_message: Optional[str] = None,
        details: Optional[str] = None
    ):
        """
        Log a tool invocation.
        
        Args:
            tool_name: Name of the tool (e.g., "zoekt", "graph_rag", "semgrep")
            success: Whether the invocation succeeded
            error_message: Error message if failed
            details: Optional additional context
        """
        self.invocations.append({
            "tool": tool_name,
            "success": success,
            "error": error_message,
            "details": details,
            "timestamp": datetime.now()
        })
        
        # Log for debugging
        if success:
            logger.debug(f"Tool '{tool_name}' succeeded")
        else:
            logger.warning(f"Tool '{tool_name}' failed: {error_message}")
    
    def calculate_tusr(self) -> Dict[str, any]:
        """
        Calculate Tool Use Success Rate and related metrics.
        
        Returns:
            {
                "tusr": int (0-100),
                "total": int,
                "successful": int,
                "failed": int,
                "by_tool": Dict[str, Dict],
                "failure_rate": float,
                "most_reliable": str,
                "most_problematic": str
            }
        """
        if not self.invocations:
            return {
                "tusr": 100,  # Optimistic default if no tools used
                "total": 0,
                "successful": 0,
                "failed": 0,
                "by_tool": {},
                "failure_rate": 0.0,
                "most_reliable": None,
                "most_problematic": None
            }
        
        successful = sum(1 for inv in self.invocations if inv['success'])
        total = len(self.invocations)
        failed = total - successful
        
        tusr = int((successful / total * 100)) if total > 0 else 100
        failure_rate = round((failed / total * 100), 2) if total > 0 else 0.0
        
        # Breakdown by tool
        by_tool = self._breakdown_by_tool()
        
        # Identify most reliable and problematic tools
        most_reliable = None
        most_problematic = None
        
        if by_tool:
            # Most reliable = highest success rate
            reliable_tools = sorted(
                [(name, stats['success_rate']) for name, stats in by_tool.items()],
                key=lambda x: x[1],
                reverse=True
            )
            if reliable_tools:
                most_reliable = reliable_tools[0][0]
            
            # Most problematic = lowest success rate (if failures exist)
            problematic_tools = sorted(
                [(name, stats['success_rate']) for name, stats in by_tool.items() if stats['failed'] > 0],
                key=lambda x: x[1]
            )
            if problematic_tools:
                most_problematic = problematic_tools[0][0]
        
        return {
            "tusr": tusr,
            "total": total,
            "successful": successful,
            "failed": failed,
            "by_tool": by_tool,
            "failure_rate": failure_rate,
            "most_reliable": most_reliable,
            "most_problematic": most_problematic
        }
    
    def _breakdown_by_tool(self) -> Dict[str, Dict]:
        """
        Break down invocations by tool.
        
        Returns:
            {
                "zoekt": {"total": 5, "successful": 5, "failed": 0, "success_rate": 100.0},
                "semgrep": {"total": 1, "successful": 0, "failed": 1, "success_rate": 0.0},
                ...
            }
        """
        breakdown = {}
        
        for inv in self.invocations:
            tool = inv['tool']
            if tool not in breakdown:
                breakdown[tool] = {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "errors": []
                }
            
            breakdown[tool]['total'] += 1
            if inv['success']:
                breakdown[tool]['successful'] += 1
            else:
                breakdown[tool]['failed'] += 1
                if inv['error']:
                    breakdown[tool]['errors'].append(inv['error'])
        
        # Calculate success rates
        for tool, stats in breakdown.items():
            stats['success_rate'] = round(
                (stats['successful'] / stats['total'] * 100), 
                2
            ) if stats['total'] > 0 else 0.0
        
        return breakdown
    
    def get_failed_invocations(self) -> List[Dict]:
        """Return all failed invocations for debugging."""
        return [inv for inv in self.invocations if not inv['success']]
    
    def get_summary_string(self) -> str:
        """Generate a human-readable summary."""
        tusr_data = self.calculate_tusr()
        
        summary = f"Tool Use Success Rate (TUSR): {tusr_data['tusr']}/100\n"
        summary += f"Total Invocations: {tusr_data['total']} "
        summary += f"(✓ {tusr_data['successful']}, ✗ {tusr_data['failed']})\n"
        
        if tusr_data['by_tool']:
            summary += "\nBreakdown by Tool:\n"
            for tool, stats in sorted(tusr_data['by_tool'].items()):
                summary += f"  {tool}: {stats['successful']}/{stats['total']} ({stats['success_rate']}%)\n"
        
        if tusr_data['most_reliable']:
            summary += f"\nMost Reliable: {tusr_data['most_reliable']}\n"
        
        if tusr_data['most_problematic']:
            summary += f"Most Problematic: {tusr_data['most_problematic']}\n"
        
        return summary.strip()
    
    def reset(self):
        """Reset tracker for a new run."""
        self.invocations = []
        self.start_time = datetime.now()


# Decorator for easy tool tracking (optional helper)
def track_tool_invocation(tracker: ToolUsageTracker, tool_name: str):
    """
    Decorator to automatically track tool invocations.
    
    Usage:
        @track_tool_invocation(self.tool_tracker, "zoekt")
        def search_code(self, query):
            return self.zoekt.search(query)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                tracker.log_invocation(tool_name, True)
                return result
            except Exception as e:
                tracker.log_invocation(tool_name, False, str(e))
                raise
        return wrapper
    return decorator
