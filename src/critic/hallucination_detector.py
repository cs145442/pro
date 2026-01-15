import re
from typing import List, Tuple

class HallucinationDetector:
    """
    Implements Hallucination Detection - The Legal Paradigm metric.
    Answers: Did the agent invent non-existent libraries or APIs?
    """
    
    # Common real packages for validation (expandable)
    KNOWN_JAVA_PACKAGES = {
        "java.util", "java.io", "java.lang", "java.net", "java.nio",
        "android.os", "android.app", "android.content", "android.view",
        "android.widget", "android.util", "android.graphics",
        "com.google.gson", "org.json", "okhttp3", "retrofit2",
        "androidx.core", "androidx.appcompat", "androidx.fragment"
    }
    
    KNOWN_PYTHON_PACKAGES = {
        "os", "sys", "json", "re", "typing", "dataclasses", "asyncio",
        "requests", "flask", "django", "fastapi", "pydantic",
        "langchain", "langgraph", "openai", "anthropic", "neo4j"
    }

    def detect_imports(self, code: str) -> List[str]:
        """Extract all import statements from code."""
        imports = []
        # Java imports
        java_pattern = r'import\s+([\w.]+);'
        imports.extend(re.findall(java_pattern, code))
        # Python imports
        python_pattern = r'(?:from\s+(\w+)|import\s+(\w+))'
        for match in re.findall(python_pattern, code):
            imports.extend([m for m in match if m])
        return imports

    def check_hallucinations(self, code: str, language: str = "java") -> Tuple[List[str], int]:
        """
        Check code for hallucinated imports.
        Returns: (list of suspicious imports, faithfulness score 0-100)
        """
        imports = self.detect_imports(code)
        known = self.KNOWN_JAVA_PACKAGES if language == "java" else self.KNOWN_PYTHON_PACKAGES
        
        suspicious = []
        for imp in imports:
            # Get root package (e.g., "com.fake.lib" -> "com.fake")
            root = ".".join(imp.split(".")[:2]) if "." in imp else imp
            # Check if it's in known packages or looks suspicious
            if root not in known and not any(imp.startswith(k) for k in known):
                # Heuristic: unknown packages with odd names are suspicious
                if self._looks_suspicious(imp):
                    suspicious.append(imp)
        
        # Faithfulness score: 100 if no hallucinations, decreases by 20 per hallucination
        faithfulness = max(0, 100 - len(suspicious) * 20)
        return suspicious, faithfulness

    def _looks_suspicious(self, package: str) -> bool:
        """Heuristic to detect obviously fake packages."""
        # Very short uncommon packages
        if len(package) < 3:
            return True
        # Packages with typos (common attack vector)
        typo_indicators = ["utils", "helper", "common", "misc"]
        if any(t in package.lower() and len(package) < 15 for t in typo_indicators):
            return True
        return False
