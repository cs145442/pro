import os
import requests
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta

class GitHubPRFetcher:
    """
    Automates the creation of 'Shadow Datasets' from GitHub repositories.
    Fetches closed PRs from the last N days to serve as a Historical Test Set.
    """
    
    def __init__(self, repo_url: str, token: Optional[str] = None):
        """
        :param repo_url: e.g., "square/okhttp"
        :param token: GitHub Personal Access Token (optional but recommended for rate limits)
        """
        self.owner, self.repo = self._parse_url(repo_url)
        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
            
    def _parse_url(self, url: str) -> tuple:
        parts = url.rstrip("/").split("/")
        return parts[-2], parts[-1]

    def fetch_recent_prs(self, days: int = 90, limit: int = 20) -> List[Dict]:
        """
        Fetch closed PRs merged in the last 'days'.
        """
        print(f"Fetching PRs for {self.owner}/{self.repo}...")
        
        # Calculate cutoff date
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100
        }
        
        dataset = []
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            prs = response.json()
            
            for pr in prs:
                if len(dataset) >= limit:
                    break
                    
                # Skip unmerged PRs
                if not pr.get("merged_at"):
                    continue
                    
                merged_at = datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
                # Simple check logic; API returns sorted so we can stop if old
                # (For strictness, we'd check against 'since', but listing is safer)
                
                # Fetch details (files changed)
                files_url = pr["url"] + "/files"
                files_resp = requests.get(files_url, headers=self.headers)
                files_data = files_resp.json() if files_resp.ok else []
                files = [f["filename"] for f in files_data]
                
                # Oracle Tests: Identify and download test files from the PR
                oracle_tests = {}
                head_sha = pr["head"]["sha"]
                
                for f in files_data:
                    fname = f["filename"]
                    # Heuristic for test files (covers Python, JS, Go, Java)
                    if "test" in fname.lower() or fname.endswith("_test.go") or fname.endswith("Spec.js"):
                        try:
                            # Download raw content from the PR head
                            raw_url = f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{head_sha}/{fname}"
                            # For private repos, we need to use the API properly, but for public this works.
                            # Better: use the 'raw_url' provided in the file object if available
                            raw_download_url = f.get("raw_url") or raw_url
                            
                            content_resp = requests.get(raw_download_url, headers=self.headers)
                            if content_resp.ok:
                                oracle_tests[fname] = content_resp.text
                        except Exception as e:
                            print(f"Warning: Failed to download oracle test {fname}: {e}")

                # Base SHA is the commit BEFORE the PR was merged
                # For a merged PR, 'base.sha' is usually the branch point. 
                # Ideally we want the merge parent, but base.sha works for simple rebase flows.
                base_sha = pr["base"]["sha"]
                
                dataset.append({
                    "id": f"pr-{pr['number']}",
                    "description": pr["title"] + "\n\n" + (pr["body"] or ""),
                    "has_bug": "fix" in pr["title"].lower(), # Heuristic: 'fix' usually implies a bug
                    "base_commit": base_sha,
                    "pr_url": pr["html_url"],
                    "merged_at": pr["merged_at"],
                    "expected_files": files,
                    "oracle_tests": oracle_tests
                })
                print(f"Found PR #{pr['number']}: {pr['title']} ({len(oracle_tests)} oracle tests)")

        except Exception as e:
            print(f"Error fetching PRs: {e}")
            
        return dataset

    def save_dataset(self, dataset: List[Dict], filepath: str = None):
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Sanitize repo name just in case
            safe_repo = self.repo.replace("/", "_")
            
            # Ensure datasets directory exists (it should be mounted, but good practice)
            os.makedirs("datasets", exist_ok=True)
            filepath = f"datasets/shadow_dataset_{safe_repo}_{timestamp}.json"
            
        with open(filepath, "w") as f:
            json.dump(dataset, f, indent=2)
        print(f"Saved {len(dataset)} items to {filepath}")
        return filepath
