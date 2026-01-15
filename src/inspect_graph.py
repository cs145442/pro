"""Inspect Neo4j graph contents."""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))
with driver.session() as s:
    # Count nodes by label
    r = s.run("MATCH (n) RETURN labels(n)[0] as label, count(*) as cnt")
    print("Node counts:")
    for rec in r:
        print(f"  {rec['label']}: {rec['cnt']}")
    
    # Check for handle_exception function
    r2 = s.run('MATCH (f:Function {name: "handle_exception"}) RETURN f.file, f.name LIMIT 5')
    print("\nhandle_exception functions:")
    for rec in r2:
        print(f"  {rec['f.file']}")
    
    # Count CALLS edges
    r3 = s.run("MATCH ()-[c:CALLS]->() RETURN count(c) as cnt")
    print(f"\nCALLS edges: {r3.single()['cnt']}")
    
    # Sample some CALLS
    r4 = s.run("MATCH (a:Function)-[:CALLS]->(b:Function) RETURN a.name, b.name LIMIT 5")
    print("\nSample CALLS:")
    for rec in r4:
        print(f"  {rec['a.name']} -> {rec['b.name']}")

driver.close()
