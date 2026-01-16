import unittest
from unittest.mock import MagicMock, patch
import os
from src.perception.parsing.python_parser import PythonParser
from src.tools.world_builder import WorldBuilder

class TestGraphIngestion(unittest.TestCase):
    def test_python_parser_logic(self):
        """Verify the AST parser extracts exact nodes/edges."""
        code = """
import os
from flask import Flask

class MyApp:
    def run(self):
        print("Running")

def helper():
    pass
"""
        parser = PythonParser()
        result = parser.parse(code, "app.py")
        
        # Verify Modules (Classes)
        modules = [n for n in result.nodes if "Module" in n["labels"]]
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["properties"]["name"], "MyApp")

        # Verify Functions
        funcs = [n for n in result.nodes if "Function" in n["labels"]]
        self.assertEqual(len(funcs), 2)
        names = sorted([n["properties"]["name"] for n in funcs])
        self.assertEqual(names, ["MyApp.run", "helper"])

        # Verify Imports
        imports = [e for e in result.edges if e["type"] == "IMPORTS"]
        # os, Flask
        self.assertEqual(len(imports), 2)
        
    @patch('src.perception.graph_rag.GraphRAG')
    @patch('src.tools.world_builder.docker')
    def test_world_builder_ingestion(self, mock_docker, mock_graph_class):
        """Verify WorldBuilder calls Neo4j with correct data."""
        # Setup Mock Graph
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_graph_instance = mock_graph_class.return_value
        mock_graph_instance.driver.session.return_value.__enter__.return_value = mock_session
        
        # Create Dummy File
        os.makedirs("test_repo", exist_ok=True)
        with open("test_repo/test.py", "w") as f:
            f.write("def foo(): pass")
            
        # Run Builder
        builder = WorldBuilder(repo_dir=".")
        builder._populate_graph("test_repo")
        
        # Verify Session Calls (roughly)
        # Should call MERGE for File, MERGE for Function, etc.
        self.assertTrue(mock_session.run.called)
        
        # Cleanup
        os.remove("test_repo/test.py")
        os.rmdir("test_repo")

if __name__ == '__main__':
    unittest.main()
