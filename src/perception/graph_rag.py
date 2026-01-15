from neo4j import GraphDatabase
import os
from typing import List

class GraphRAG:
    """
    Interface for the Neo4j Dependency Graph.
    Allows the agent to ask: "Who depends on this file?"
    """
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def get_dependencies(self, file_path: str) -> List[str]:
        """
        Returns a list of files that import or depend on the given file.
        (Previously DEPENDS_ON, now inferred from calls/imports)
        """
        query = """
        MATCH (f:File {path: $path})<-[:DEFINES]-(:Module)<-[:IMPORTS]-(dependent:File)
        RETURN distinct dependent.path as path
        UNION
        MATCH (f:File {path: $path})-[:DEFINES]->(:Function)<-[:CALLS]-(caller:Function)<-[:DEFINES]-(dependent:File)
        RETURN distinct dependent.path as path
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, path=file_path)
                return [record["path"] for record in result]
        except Exception as e:
            print(f"GraphRAG Query Failed: {e}")
            return []

    def get_callers(self, symbol_name: str) -> List[str]:
        """
        Returns a list of files containing functions that CALL the given symbol.
        """
        # CALLS edge direction: (caller)-[:CALLS]->(callee)
        # We use caller.file property directly instead of traversing DEFINES
        query = """
        MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $name})
        RETURN distinct caller.file as path
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, name=symbol_name)
                return [record["path"] for record in result if record["path"]]
        except Exception as e:
            print(f"GraphRAG get_callers Failed: {e}")
            return []

    def get_definitions(self, symbol_name: str) -> List[str]:
        """
        Returns the file where a symbol is defined.
        """
        query = """
        MATCH (fn:Function {name: $name})<-[:DEFINES]-(f:File)
        RETURN distinct f.path as path
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, name=symbol_name)
                return [record["path"] for record in result]
        except Exception as e:
            print(f"GraphRAG get_definitions Failed: {e}")
            return []

    def get_attr_callers(self, attr_name: str) -> List[str]:
        """
        Returns files containing functions that call .attr_name() on any object.
        This captures self.method(), obj.method() patterns.
        """
        query = """
        MATCH (caller:Function)-[:CALLS_ATTR]->(attr:AttributeCall {name: $name})
        RETURN DISTINCT caller.file as path
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, name=attr_name)
                return [record["path"] for record in result if record["path"]]
        except Exception as e:
            print(f"GraphRAG get_attr_callers Failed: {e}")
            return []

    def close(self):
        self.driver.close()
