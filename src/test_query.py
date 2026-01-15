"""Test the get_callers query directly."""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))
with driver.session() as s:
    # Test the exact query from GraphRAG
    query = """
    MATCH (callee:Function {name: $name})<-[:CALLS]-(caller:Function)<-[:DEFINES]-(f:File)  
    RETURN distinct f.path as path
    """
    print("Testing get_callers query for 'handle_exception':")
    r = s.run(query, name="handle_exception")
    results = [rec["path"] for rec in r]
    print(f"  Results: {results}")
    
    # Let's break it down step by step
    print("\nStep 1: Find handle_exception functions")
    r1 = s.run("MATCH (f:Function {name: 'handle_exception'}) RETURN f.name, f.file LIMIT 3")
    for rec in r1:
        print(f"  Found: {rec['f.name']} in {rec['f.file']}")
    
    print("\nStep 2: Find who CALLS handle_exception")
    r2 = s.run("MATCH (caller:Function)-[:CALLS]->(callee:Function {name: 'handle_exception'}) RETURN caller.name, callee.name LIMIT 5")
    for rec in r2:
        print(f"  {rec['caller.name']} -> {rec['callee.name']}")
    
    print("\nStep 3: Alternative - find callers with their files")
    r3 = s.run("""
        MATCH (caller:Function)-[:CALLS]->(callee:Function {name: 'handle_exception'})
        RETURN caller.name, caller.file LIMIT 5
    """)
    for rec in r3:
        print(f"  {rec['caller.name']} in {rec['caller.file']}")

driver.close()
