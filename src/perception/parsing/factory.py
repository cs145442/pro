import os
from typing import Optional
from .abstract import LanguageParser
from .python_parser import PythonParser

class ParserFactory:
    """
    Factory to get the correct parser for a file type.
    """
    _parsers = {
        ".py": PythonParser()
    }

    @staticmethod
    def get_parser(file_path: str) -> Optional[LanguageParser]:
        _, ext = os.path.splitext(file_path)
        return ParserFactory._parsers.get(ext)
