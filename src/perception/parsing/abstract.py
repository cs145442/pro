from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ParsedResult:
    """
    Standardized result from parsing a file.
    nodes: List of dictionaries representing nodes (Classes, Functions)
    edges: List of dictionaries representing relationships (IMPORTS, CALLS, DEFINES)
    """
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)

class LanguageParser(ABC):
    """
    Abstract Base Class for all language parsers.
    Ensures future parsers (JS, Go) follow the same contract.
    """
    
    @abstractmethod
    def parse(self, content: str, file_path: str) -> ParsedResult:
        """
        Parse the content string and return structured graph elements.
        """
        pass
