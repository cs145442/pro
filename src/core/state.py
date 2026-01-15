from typing import List, Optional, TypedDict, Annotated
import operator

class AgentState(TypedDict):
    """
    The Memory of the Artificial Architect.
    Tracks the OODA loop progress and all CES metrics.
    """
    # 1. Observe
    issue_id: str
    issue_description: str
    repo_path: str
    
    # 2. Orient (Context)
    retrieved_context: Annotated[List[str], operator.add]
    known_dependencies: List[str]
    
    # 3. Decide (Plan)
    plan: List[str]
    current_step: int
    
    # 4. Act (Execution)
    generated_diff: Optional[str]
    
    # 5. Review (Critic Loop) - MULTI-PARADIGM SCORES
    # Medical Paradigm
    safety_score: int  # 0-100 (from Semgrep)
    for_score: int  # 0-100 (False Omission Rate - NEW Priority 1)
    oracle_score: int # 0-100 (Golden Test Pass Rate)
    oracle_details: str # Details of golden test execution
    tests_broken: int  # Count of tests broken by patch (NEW Priority 1)
    
    # Legal Paradigm
    compliance_score: int  # 0-100 (from Style/Compliance LLM)
    faithfulness_score: int  # 0-100 (Hallucination Detection)
    
    # Financial Paradigm
    risk_level: str  # CRITICAL/HIGH/MEDIUM/LOW/TRIVIAL
    risk_score: int  # 1-10
    
    # Financial Paradigm - Code Quality (NEW: Priority 2)
    maintainability_index: int  # 0-100 (Halstead + Complexity)
    cyclomatic_complexity: float  # Average CC across functions
    duplication_ratio: float  # % of duplicated code
    architectural_violations: int  # Count of import rule violations
    coupling_score: int  # 0-100 (lower coupling = higher score)
    
    # Defense Paradigm
    mttr_seconds: float  # Mean Time to Remediate
    pirr_score: int  # 0-100 (Prompt Injection Resistance Rate - NEW Priority 1)
    poisoned_input_detected: bool  # True if injection patterns found (NEW Priority 1)
    
    # Behavioral Paradigm
    spec_gaming_index: int  # 0-100 (Specification Gaming Index - NEW Priority 1)
    test_files_modified: bool  # True if agent edited test files (NEW Priority 1)
    
    # Behavioral Paradigm - Tool Usage (NEW: Priority 3)
    tusr_score: int  # 0-100 (Tool Use Success Rate)
    total_tool_invocations: int
    successful_tool_invocations: int
    failed_tool_invocations: int
    
    # Financial Paradigm - Technical Debt (NEW: Priority 3)
    tdr_ratio: float  # 0-100% (Refactoring / Total work)
    work_type: str  # 'refactoring' or 'feature'
    historical_tdr: float  # Rolling 30-day TDR
    
    # Cost Tracking
    tokens_used: dict  # {"brain": 0, "critics": 0}
    models_used: dict  # {"brain": "claude-3-5-sonnet", "critics": "gpt-4o-mini"}
    
    critic_feedback: List[str]
    retry_count: int
    
    # Self-Correction Loop (NEW: Behavioral Paradigm - Framework Section 8.2)
    self_correction_attempts: int  # Number of syntax validation retries
    validation_error: Optional[str]  # Last validation error message
    
    # Final Outcome
    status: str


