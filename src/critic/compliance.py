from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import logging

logger = logging.getLogger(__name__)

class ComplianceCritic:
    """
    Enforces the 'Legal Paradigm' (Compliance).
    Uses a fast LLM (GPT-4o-mini) to check for style and license issues.
    """
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Senior Code Reviewer. Your job is NOT to check if code works, but if it follows the rules."),
            ("user", "Review this diff for:\n1. Style violations (CamelCase vs SnakeCase).\n2. License headers.\n3. Restricted imports.\n\nCode:\n{diff}")
        ])

    async def review(self, diff: str) -> str:
        chain = self.prompt | self.llm
        logger.debug(f"[Compliance] Reviewing diff length: {len(diff)}")
        response = await chain.ainvoke({"diff": diff})
        logger.info(f"⚖️ [COMPLIANCE] Model output:\n{response.content}\n--------------------------------------------------")
        return response.content
