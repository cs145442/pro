
import ast
import os
from typing import List, Dict, Set, Tuple
from neo4j import GraphDatabase
import logging

logger = logging.getLogger(__name__)

class GraphBuilder:
    """
    Parses source code and builds a Semantic Code Graph in Neo4j.
    Nodes: File, Module, Class, Function
    Edges: DEFINES, CALLS, IMPORTS, INHERITS_FROM
    """
    
    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        
    def close(self):
        self.driver.close()
        
    def build_graph(self, repo_path: str):
        """
        Scans the repository and populates the graph.
        """
        print(f"[GraphBuilder] Building semantic graph for {repo_path}...")
        
        # 1. Clear existing graph for this repo (simplification for now)
        # In production, we'd do incremental updates.
        self._clear_graph()
        
        # 2. Walk files and parse
        files_processed = 0
        for root, dirs, files in os.walk(repo_path):
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
                
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    # Relativize path for consistency
                    rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")
                    
                    try:
                        self._process_file(full_path, rel_path)
                        files_processed += 1
                    except Exception as e:
                        logger.error(f"Failed to process {rel_path}: {e}")
                        
        print(f"[GraphBuilder] Processed {files_processed} files.")

    def _clear_graph(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def _process_file(self, full_path: str, rel_path: str):
        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read()
            
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return  # Skip files with syntax errors

        # Create File Node
        with self.driver.session() as session:
            session.run(
                "MERGE (f:File {path: $path})", 
                path=rel_path
            )
            
        # Traverse AST
        visitor = CodeVisitor(self.driver, rel_path)
        visitor.visit(tree)

class CodeVisitor(ast.NodeVisitor):
    def __init__(self, driver, file_path):
        self.driver = driver
        self.file_path = file_path
        self.current_class = None
        self.current_function = None
        self.imports = {}  # alias -> real_name

    def visit_Import(self, node):
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name
            # Create Import Edge (simplified - linking to file/module would require resolution)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}"
            self.imports[alias.asname or alias.name] = full_name
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        prev_class = self.current_class
        self.current_class = node.name
        
        # Create Class Node
        with self.driver.session() as session:
            session.run("""
                MATCH (f:File {path: $file_path})
                MERGE (c:Class {name: $name, file: $file_path})
                MERGE (f)-[:DEFINES]->(c)
            """, file_path=self.file_path, name=node.name)
            
            # Inheritance
            for base in node.bases:
                if isinstance(base, ast.Name):
                    parent_name = base.id
                    # We might not know where parent is defined yet, so we just create a placeholder node or edge
                    # For simplicity, we create a Class node with just the name
                    session.run("""
                        MATCH (c:Class {name: $name, file: $file_path})
                        MERGE (p:Class {name: $parent_name})
                        MERGE (c)-[:INHERITS_FROM]->(p)
                    """, file_path=self.file_path, name=node.name, parent_name=parent_name)

        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        prev_func = self.current_function
        self.current_function = node.name
        
        # Create Function Node
        with self.driver.session() as session:
            # Attached to Class or File?
            if self.current_class:
                session.run("""
                    MATCH (c:Class {name: $class_name, file: $file_path})
                    MERGE (fn:Function {name: $name, file: $file_path, scope: $class_name})
                    MERGE (c)-[:DEFINES]->(fn)
                """, class_name=self.current_class, file_path=self.file_path, name=node.name)
            else:
                session.run("""
                    MATCH (f:File {path: $file_path})
                    MERGE (fn:Function {name: $name, file: $file_path})
                    MERGE (f)-[:DEFINES]->(fn)
                """, file_path=self.file_path, name=node.name)

        self.generic_visit(node)
        self.current_function = prev_func
        
    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Call(self, node):
        # Only track if we're inside a function
        if not self.current_function:
            self.generic_visit(node)
            return
            
        func_name = None
        is_attribute_call = False
        
        if isinstance(node.func, ast.Name):
            # Direct call: func()
            func_name = node.func.id
            is_attribute_call = False
        elif isinstance(node.func, ast.Attribute):
            # Attribute call: obj.method() or self.method()
            func_name = node.func.attr
            is_attribute_call = True
            
        if func_name:
            with self.driver.session() as session:
                if is_attribute_call:
                    # Create CALLS_ATTR edge for self.method() patterns
                    # We create an AttributeCall node to represent the method name
                    session.run("""
                        MATCH (caller:Function {name: $caller_name, file: $file_path})
                        MERGE (attr:AttributeCall {name: $attr_name})
                        MERGE (caller)-[:CALLS_ATTR]->(attr)
                    """, caller_name=self.current_function, file_path=self.file_path, attr_name=func_name)
                else:
                    # Create CALLS edge for direct function calls
                    session.run("""
                        MATCH (caller:Function {name: $caller_name, file: $file_path})
                        MATCH (callee:Function {name: $callee_name})
                        MERGE (caller)-[:CALLS]->(callee)
                    """, caller_name=self.current_function, file_path=self.file_path, callee_name=func_name)
                    
        self.generic_visit(node)

if __name__ == "__main__":
    # Test
    repo = os.getenv("REPO_PATH", "/workspace/repos/flask")
    builder = GraphBuilder()
    builder.build_graph(repo)
    builder.close()
