"""
Debug script to verify GraphRAG functionality.
Run with: docker exec pro-agent-brain-1 python src/debug_graph.py
"""
import os
import sys

def debug():
    print("1. Checking path...")
    repo_path = "/app/repos/flask"
    print(f"   Path exists: {os.path.exists(repo_path)}")
    
    if os.path.exists(repo_path):
        files = os.listdir(repo_path)
        print(f"   Contents: {files[:5]}...")
    else:
        print("   ERROR: Flask repo not found!")
        return

    print("2. Testing Neo4j connection...")
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            print("   Neo4j connection: OK")
        driver.close()
    except Exception as e:
        print(f"   Neo4j connection FAILED: {e}")
        return

    print("3. Building graph...")
    try:
        from src.perception.graph_builder import GraphBuilder
        gb = GraphBuilder()
        gb.build_graph(repo_path)
        gb.close()
    except Exception as e:
        print(f"   GraphBuilder FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    print("4. Querying graph...")
    try:
        from src.perception.graph_rag import GraphRAG
        rag = GraphRAG()
        callers = rag.get_callers("update_template_context")
        print(f"   Callers of update_template_context: {callers}")
        rag.close()
    except Exception as e:
        print(f"   GraphRAG query FAILED: {e}")
        import traceback
        traceback.print_exc()

    print("Done.")

if __name__ == "__main__":
    debug()
