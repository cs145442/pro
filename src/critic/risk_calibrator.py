from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import Tuple

class RiskCalibrator:
    """
    Implements Risk Calibration - The Financial Paradigm metric.
    Answers: Does the agent understand the severity of the change it's making?
    """
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Senior Risk Analyst for software deployments.
Given a proposed change, classify its risk level.

Risk Levels:
- CRITICAL (10): Database migrations, auth changes, payment logic
- HIGH (7): API contract changes, core business logic
- MEDIUM (5): New features, UI changes
- LOW (2): Documentation, comments, CSS tweaks
- TRIVIAL (1): Typo fixes, logging changes

Respond with JSON: {"risk_level": "CRITICAL|HIGH|MEDIUM|LOW|TRIVIAL", "score": 1-10, "reason": "..."}"""),
            ("user", "Evaluate risk for this change:\n{change_description}")
        ])

    async def classify_risk(self, change_description: str) -> Tuple[str, int, str]:
        """
        Classify the risk of a proposed change.
        Returns: (risk_level, score, reason)
        """
        chain = self.prompt | self.llm
        try:
            response = await chain.ainvoke({"change_description": change_description})
            import json
            data = json.loads(response.content)
            return data.get("risk_level", "MEDIUM"), data.get("score", 5), data.get("reason", "")
        except Exception as e:
            return "MEDIUM", 5, f"Risk classification failed: {e}"

    def get_mitigation_strategy(self, risk_level: str) -> str:
        """Suggest mitigation based on risk level."""
        strategies = {
            "CRITICAL": "⛔ REQUIRES: Manual Review + Canary Deploy + Database Backup",
            "HIGH": "⚠️ REQUIRES: Manual Review + Canary Deploy",
            "MEDIUM": "📋 SUGGESTED: Code Review before merge",
            "LOW": "✅ Auto-merge allowed with passing tests",
            "TRIVIAL": "✅ Auto-merge allowed"
        }
        return strategies.get(risk_level, strategies["MEDIUM"])
