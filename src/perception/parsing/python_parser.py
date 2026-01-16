import ast
import os
from typing import List, Dict, Any, Set
from .abstract import LanguageParser, ParsedResult

class PythonParser(LanguageParser):
    def parse(self, content: str, file_path: str) -> ParsedResult:
        result = ParsedResult()
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return result  # Skip malformed files

        visitor = GraphVisitor(file_path)
        visitor.visit(tree)
        
        result.nodes = visitor.nodes
        result.edges = visitor.edges
        return result

class GraphVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        
        # Track scope
        self.current_class = None
        self.current_function = None

    def visit_ClassDef(self, node):
        class_name = node.name
        qualified_name = f"{self.file_name}:{class_name}"
        
        # Create Entity Node (Module/Class)
        self.nodes.append({
            "labels": ["Module"],
            "properties": {"name": class_name, "path": self.file_path, "type": "class"}
        })
        
        # DEFINES Edge: File -> Class
        self.edges.append({
            "type": "DEFINES",
            "from_type": "File", "from_props": {"path": self.file_path},
            "to_type": "Module", "to_props": {"name": class_name, "path": self.file_path}
        })
        
        prev_class = self.current_class
        self.current_class = class_name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node)

    def _handle_function(self, node):
        func_name = node.name
        
        # Scope resolution
        if self.current_class:
            qualified_name = f"{self.current_class}.{func_name}"
        else:
            qualified_name = func_name

        # Create Function Node
        self.nodes.append({
            "labels": ["Function"],
            "properties": {"name": list_clean(qualified_name), "file": self.file_path}
        })

        # DEFINES Edge: File -> Function
        # (Technically Class -> Function if method, but simpler schema links File for now)
        self.edges.append({
            "type": "DEFINES",
            "from_type": "File", "from_props": {"path": self.file_path},
            "to_type": "Function", "to_props": {"name": list_clean(qualified_name), "file": self.file_path}
        })

        prev_func = self.current_function
        self.current_function = qualified_name
        self.generic_visit(node)
        self.current_function = prev_func

    def visit_Import(self, node):
        for alias in node.names:
            imported_name = alias.name
            # Approximate path or module name
            self.edges.append({
                "type": "IMPORTS",
                "from_type": "File", "from_props": {"path": self.file_path},
                "to_type": "Module", "to_props": {"name": imported_name} # Fuzzy match
            })

    def visit_ImportFrom(self, node):
        if node.module:
            self.edges.append({
                "type": "IMPORTS",
                "from_type": "File", "from_props": {"path": self.file_path},
                "to_type": "Module", "to_props": {"name": node.module} 
            })

    def visit_Call(self, node):
        # Extract function call name
        call_name = self._get_call_name(node.func)
        if call_name and self.current_function:
            # We only track calls FROM a function TO another function
            self.edges.append({
                "type": "CALLS",
                "from_type": "Function", "from_props": {"name": list_clean(self.current_function), "file": self.file_path},
                "to_type": "Function", "to_props": {"name": call_name} 
            })

    def _get_call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return None

def list_clean(name):
    # Neo4j properties can't be complex objects, keep it string
    return str(name)
