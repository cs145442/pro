import requests
import os
from typing import List, Dict

class ZoektClient:
    """
    Interface for the Google Zoekt (Regex Code Search) engine.
    Used for instant trigram search over massive repos.
    """
    def __init__(self, base_url=None):
        self.base_url = base_url or os.getenv("ZOEKT_URL", "http://localhost:6070")
        import logging
        self.logger = logging.getLogger(__name__)

    def search(self, query: str, num_results=10) -> List[Dict]:
        """
        Executes a regex search.
        """
        payload = {
            "q": query,
            "num": num_results
        }
        try:
            # Note: This is an example schema matching standard Zoekt JSON API
            resp = requests.post(f"{self.base_url}/api/search", json=payload, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            
            # Debug: Print response structure
            self.logger.debug(f"Zoekt response keys: {list(data.keys())}")
            
            # Zoe kt response structure: {"Result": {"Files": [...], "Stats": {...}}}
            result = data.get("Result", {})
            
            if isinstance(result, dict):
                # Extract files from Result.Files
                files = result.get("Files", []) or []  # Handle None case
                self.logger.debug(f"Zoekt returned {len(files)} file objects from Result.Files")
                if files and len(files) > 0:
                    self.logger.debug(f"First file keys: {list(files[0].keys()) if isinstance(files[0], dict) else 'not a dict'}")
                return files
            elif isinstance(result, list):
                # Fallback for older API returning a list directly
                # Fallback for older API returning a list directly
                self.logger.debug(f"Result is a list with {len(result)} items")
                return result
            else:
                # If Files is at top level (unlikely but handle it)
                files = data.get("Files", [])
                self.logger.debug(f"Fallback to top-level Files: {len(files)} items")
                return files
        except requests.RequestException as e:
            self.logger.error(f"Zoekt Search Failed: {e}")
            return []

    def find_symbol(self, symbol_name: str):
        """Helper to find definitions of a specific symbol"""
        return self.search(f"sym:{symbol_name}")
