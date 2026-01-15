
import os
import sys

# Add src to path
sys.path.append("/app")

from src.perception.graph_builder import GraphBuilder
from src.perception.graph_rag import GraphRAG

def debug():
    # 1. Setup
    # Brain path
    repo_path = "/app/repos/flask"
    
    print(f"Checking if {repo_path} exists: {os.path.exists(repo_path)}")
    
    # 2. Build Graph
    print("Building Graph...")
    gb = GraphBuilder()
    gb.build_graph(repo_path)
    gb.close()
    
    # 3. Query
    print("Querying Graph...")
    rag = GraphRAG()
    
    # Test handle_exception
    symbol = "handle_exception"
    callers = rag.get_callers(symbol)
    print(f"Callers of {symbol}: {callers}")
    
    # Test something obvious like Flask
    class_view = rag.get_definitions("Flask")
    print(f"Definition of Flask: {class_view}")
    
    rag.close()

if __name__ == "__main__":
    debug()
