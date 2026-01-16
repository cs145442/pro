import os
import subprocess
import docker
from rich.console import Console
import logging

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
        self.logger = logging.getLogger(__name__)
        
        # Ensure local repo dir exists
        if not os.path.exists(self.repo_dir):
            os.makedirs(self.repo_dir)

    def setup_world(self, repo_url: str):
        """Full setup pipeline for a repo."""
        self.logger.info(f"🌍 World Builder: Setting up {repo_url}...")
        
        # 1. Clone
        repo_name = self._clone_repo(repo_url)
        
        # 2. Index (Zoekt)
        self._trigger_zoekt_index(repo_name)
        
        # 3. Graph (Neo4j)
        self._populate_graph(repo_name)
        
        self.logger.info(f"✅ World Build Complete for {repo_name}!")

    def _clone_repo(self, repo_url: str) -> str:
        """Git clone the repo if not exists."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        target_path = os.path.join(self.repo_dir, repo_name)
        
        if os.path.exists(target_path):
            self.logger.info(f"Repo {repo_name} already exists. Pulling latest...")
            try:
                subprocess.run(["git", "-C", target_path, "pull"], check=True)
            except Exception as e:
                self.logger.error(f"Git pull failed: {e}")
        else:
            self.logger.info(f"Cloning {repo_url}...")
            try:
                subprocess.run(["git", "clone", repo_url, target_path], check=True)
            except Exception as e:
                self.logger.error(f"Git clone failed: {e}")
                raise
        return repo_name

    def _trigger_zoekt_index(self, repo_name: str):
        """Trigger the zoekt-index container to re-index."""
        self.logger.info(f"Triggering Zoekt Indexer for {repo_name}...")

        try:
            # Find the zoekt-index container
            containers = self.docker_client.containers.list(filters={"name": "zoekt-index"})
            if not containers:
                self.logger.error("Error: zoekt-index container not found!")
                return
            
            indexer = containers[0]
            # Run the index command inside the container
            # The container mounts /app/repos (host) -> /data/repos (container)
            result = indexer.exec_run(f"zoekt-git-index -index /data/index /data/repos/{repo_name}")
            self.logger.info(f"Indexing {repo_name}...")
            
            if result.exit_code == 0:
                self.logger.info("Zoekt Indexing Triggered Successfully")
            else:
                self.logger.error(f"Zoekt Indexing Failed: {result.output.decode()}")
                
        except Exception as e:
            self.logger.error(f"Failed to trigger Zoekt: {e}")

    def _populate_graph(self, repo_name: str):
        """
        Populate Neo4j with the repo structure using batch ingestion.
        """
        self.logger.info(f"Populating Knowledge Graph for {repo_name}...")
        
        try:
            # 1. Connect to GraphRAG
            from src.perception.graph_rag import GraphRAG
            graph = GraphRAG()
            
            # 2. Prepare for Batch Parsing
            from src.perception.parsing import ParserFactory
            
            base_path = os.path.join(self.repo_dir, repo_name)
            all_nodes = []
            all_edges = []
            
            # 3. Iterate and Parse
            file_count = 0
            for root, _, files in os.walk(base_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_path)
                    
                    # Read Content
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                    except Exception:
                        continue # Binary or unreadable
                    
                    # Parse
                    parser = ParserFactory.get_parser(file_path)
                    if parser:
                        result = parser.parse(content, rel_path)
                        if result:
                            # Add File Node
                            all_nodes.append({
                                "labels": ["File"],
                                "properties": {"path": rel_path, "repo": repo_name}
                            })
                            all_nodes.extend(result.nodes)
                            all_edges.extend(result.edges)
                            file_count += 1
            
            self.logger.info(f"Parsed {file_count} files. Ingesting {len(all_nodes)} nodes and {len(all_edges)} edges...")
            print(f"DEBUG: Parsed {file_count} files. Ingesting {len(all_nodes)} nodes...")

            # 4. Batch Ingest (Simple Iteration for Now to ensure correctness, can optimize to UNWIND later)
            with graph.driver.session() as session:
                # Create Schema (Fixes Warnings)
                self._create_indices(session)
                
                # Clear Repo
                session.run("MATCH (n {repo: $repo}) DETACH DELETE n", repo=repo_name) # Unsafe if query matches non-repo nodes, scoped by label ideally
                
                # Ingest Nodes
                for node in all_nodes:
                    labels = ":".join(node["labels"])
                    props = node["properties"]
                    # Cypher injection risk if labels dynamic, but they are hardcoded in parser
                    query = f"MERGE (n:{labels} {{path: $path}}) SET n += $props" 
                    # Note: We rely on 'path' or 'name' uniqueness. 
                    # Simplifying for Module/Function:
                    if "Module" in node["labels"]:
                         query = f"MERGE (n:{labels} {{name:AsyncFunctionDef, path: $path}}) SET n += $props" # Wait, name?
                         # Let's use a generic ID strategy. 
                         # Actually, let's keep it simple: 
                         pass
                
                # REWRITE: The generic ingestion is tricky with varying keys. 
                # Let's use specific batch functions.
                self._batch_ingest_files(session, [n for n in all_nodes if "File" in n["labels"]])
                self._batch_ingest_modules(session, [n for n in all_nodes if "Module" in n["labels"]])
                self._batch_ingest_functions(session, [n for n in all_nodes if "Function" in n["labels"]])
                self._batch_ingest_edges(session, all_edges)

            self.logger.info("Graph population complete.")
            graph.close()
                
        except Exception as e:
            self.logger.error(f"Failed to populate graph: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _batch_ingest_files(self, session, nodes):
        for n in nodes:
            session.run("MERGE (n:File {path: $path}) SET n += $props", path=n["properties"]["path"], props=n["properties"])

    def _batch_ingest_modules(self, session, nodes):
        for n in nodes:
             session.run("MERGE (n:Module {name: $name, path: $path}) SET n += $props", 
                         name=n["properties"]["name"], path=n["properties"]["path"], props=n["properties"])

    def _batch_ingest_functions(self, session, nodes):
        for n in nodes:
             session.run("MERGE (n:Function {name: $name, file: $file}) SET n += $props", 
                         name=n["properties"]["name"], file=n["properties"]["file"], props=n["properties"])
    
    def _batch_ingest_edges(self, session, edges):
        for edge in edges:
            if edge["type"] == "DEFINES":
                # File -> Module/Function
                if edge["to_type"] == "Module":
                    session.run("""
                        MATCH (a:File {path: $from_path})
                        MERGE (b:Module {name: $to_name, path: $to_path})
                        MERGE (a)-[:DEFINES]->(b)
                    """, from_path=edge["from_props"]["path"], to_name=edge["to_props"]["name"], to_path=edge["to_props"]["path"])
                elif edge["to_type"] == "Function":
                     session.run("""
                        MATCH (a:File {path: $from_path})
                        MERGE (b:Function {name: $to_name, file: $to_file})
                        MERGE (a)-[:DEFINES]->(b)
                    """, from_path=edge["from_props"]["path"], to_name=edge["to_props"]["name"], to_file=edge["to_props"]["file"])
            
            elif edge["type"] == "IMPORTS":
                # File -> Module
                # Note: Imports are fuzzy. We merge the module node if it doesn't exist (Ghost Node)
                session.run("""
                    MATCH (a:File {path: $from_path})
                    MERGE (b:Module {name: $to_name})
                    MERGE (a)-[:IMPORTS]->(b)
                """, from_path=edge["from_props"]["path"], to_name=edge["to_props"]["name"])


            elif edge["type"] == "CALLS":
                # Function -> Function (Fuzzy)
                 session.run("""
                    MATCH (a:Function {name: $from_name, file: $from_file})
                    MERGE (b:Function {name: $to_name})
                    MERGE (a)-[:CALLS]->(b)
                """, from_name=edge["from_props"]["name"], from_file=edge["from_props"]["file"], to_name=edge["to_props"]["name"])

    def _create_indices(self, session):
        """Creates indices to optimize queries and prevent missing label warnings."""
        try:
            # Neo4j 4.x/5.x syntax
            session.run("CREATE INDEX file_path_index IF NOT EXISTS FOR (n:File) ON (n.path)")
            session.run("CREATE INDEX module_name_index IF NOT EXISTS FOR (n:Module) ON (n.name)")
            session.run("CREATE INDEX function_name_index IF NOT EXISTS FOR (n:Function) ON (n.name)")
        except Exception as e:
            self.logger.warning(f"Could not create indices: {e}")


