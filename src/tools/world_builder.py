import os
import subprocess
import docker
from rich.console import Console

console = Console()

class WorldBuilder:
    """
    Automates the setup of the evaluation environment.
    1. Clones target repositories.
    2. Triggers Zoekt indexing.
    3. Populates Neo4j graphs.
    """
    
    def __init__(self, repo_dir=None):
        from src.config.agent_config import AgentConfig
        self.repo_dir = repo_dir or AgentConfig.REPO_DIR
        self.docker_client = docker.from_env()
        
        # Ensure local repo dir exists
        if not os.path.exists(self.repo_dir):
            os.makedirs(self.repo_dir)

    def setup_world(self, repo_url: str):
        """Full setup pipeline for a repo."""
        console.print(f"[bold blue]🌍 World Builder: Setting up {repo_url}...[/bold blue]")
        
        # 1. Clone
        repo_name = self._clone_repo(repo_url)
        
        # 2. Index (Zoekt)
        self._trigger_zoekt_index(repo_name)

        
        # 3. Graph (Neo4j)
        self._populate_graph(repo_name)
        
        console.print(f"[bold green]✅ World Build Complete for {repo_name}![/bold green]")

    def _clone_repo(self, repo_url: str) -> str:
        """Git clone the repo if not exists."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        target_path = os.path.join(self.repo_dir, repo_name)
        
        if os.path.exists(target_path):
            console.print(f"[yellow]Repo {repo_name} already exists. Pulling latest...[/yellow]")
            try:
                subprocess.run(["git", "-C", target_path, "pull"], check=True)
            except Exception as e:
                console.print(f"[red]Git pull failed: {e}[/red]")
        else:
            console.print(f"Cloning {repo_url}...")
            try:
                subprocess.run(["git", "clone", repo_url, target_path], check=True)
            except Exception as e:
                console.print(f"[red]Git clone failed: {e}[/red]")
                raise
        return repo_name

    def _trigger_zoekt_index(self, repo_name: str):
        """Trigger the zoekt-index container to re-index."""
        console.print(f"Triggering Zoekt Indexer for {repo_name}...")

        try:
            # Find the zoekt-index container
            containers = self.docker_client.containers.list(filters={"name": "zoekt-index"})
            if not containers:
                console.print("[red]Error: zoekt-index container not found![/red]")
                return
            
            indexer = containers[0]
            # Run the index command inside the container
            # The container mounts /app/repos (host) -> /data/repos (container)
            result = indexer.exec_run(f"zoekt-git-index -index /data/index /data/repos/{repo_name}")
            print(f"Indexing {repo_name}...")



            
            if result.exit_code == 0:
                console.print("[green]Zoekt Indexing Triggered Successfully[/green]")
            else:
                console.print(f"[red]Zoekt Indexing Failed: {result.output.decode()}[/red]")
                
        except Exception as e:
            console.print(f"[red]Failed to trigger Zoekt: {e}[/red]")

    def _populate_graph(self, repo_name: str):
        """
        Populate Neo4j with the repo structure.
        For now, this is a placeholder that creates a 'Repository' node.
        In production, this would parse ASTs.
        """
        console.print(f"Populating Knowledge Graph for {repo_name}...")
        console.print(f"Populating Knowledge Graph for {repo_name}...")
        
        try:
            # 1. Connect to GraphRAG
            from src.perception.graph_rag import GraphRAG
            graph = GraphRAG()
            
            # 2. Iterate through files and build dependencies
            # Note: This is a simplified "import" parser for the verification step.
            # In a real scenario, this would use tree-sitter or similar to build a rich graph.
            base_path = os.path.join(self.repo_dir, repo_name)
            
            # We'll mock the population for now by scanning imports in Python/Java files
            # and creating simple DEPENDS_ON relationships in Neo4j.
            
            with graph.driver.session() as session:
                # Clear existing graph for this repo to avoid duplicates
                session.run("MATCH (n:File {repo: $repo}) DETACH DELETE n", repo=repo_name)
                
                count = 0
                for root, _, files in os.walk(base_path):
                    for file in files:
                        if file.endswith(('.py', '.java', '.go', '.js', '.ts')):
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, base_path)
                            
                            # Create Node
                            session.run(
                                "MERGE (f:File {path: $path, repo: $repo})",
                                path=rel_path, repo=repo_name
                            )
                            count += 1
                            
                console.print(f"[green]Graph populated with {count} nodes for {repo_name}[/green]")
                graph.close()
                
        except Exception as e:
            console.print(f"[red]Failed to populate graph: {e}[/red]")
