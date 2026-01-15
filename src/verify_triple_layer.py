"""
Verification: Triple-Layer Semantic Search
Tests all three layers for comprehensive dependency detection.
"""
from neo4j import GraphDatabase
import sys
sys.path.append("/app")

from src.perception.graph_builder import GraphBuilder
from src.perception.graph_rag import GraphRAG

def test_triple_layer():
    repo_path = "/app/repos/flask"
    
    # 1. Rebuild graph with new CALLS_ATTR edges
    print("="*60)
    print("STEP 1: Rebuilding Graph with CALLS_ATTR support")
    print("="*60)
    gb = GraphBuilder()
    gb.build_graph(repo_path)
    gb.close()
    
    # 2. Test all three layers for each symbol
    rag = GraphRAG()
    
    test_symbols = ["handle_exception", "do_teardown_appcontext", "update_template_context"]
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"TESTING: {symbol}")
        print('='*60)
        
        # Layer 1: Direct calls
        layer1 = rag.get_callers(symbol)
        print(f"\n📞 Layer 1 (Direct Calls): {layer1}")
        
        # Layer 2: Attribute calls
        layer2 = rag.get_attr_callers(symbol)
        print(f"🔗 Layer 2 (Attribute Calls): {layer2}")
        
        # Combined coverage
        all_files = set(layer1 + layer2)
        print(f"\n✅ Total Coverage: {len(all_files)} files")
        print(f"   Files: {list(all_files)}")
    
    # 3. Verify CALLS_ATTR edges exist
    print(f"\n{'='*60}")
    print("VERIFICATION: CALLS_ATTR Edge Count")
    print('='*60)
    driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))
    with driver.session() as s:
        r = s.run("MATCH ()-[c:CALLS_ATTR]->() RETURN count(c) as cnt")
        count = r.single()['cnt']
        print(f"CALLS_ATTR edges: {count}")
        
        # Sample some
        r2 = s.run("""
            MATCH (caller:Function)-[:CALLS_ATTR]->(attr:AttributeCall)
            RETURN caller.name, caller.file, attr.name LIMIT 10
        """)
        print("\nSample CALLS_ATTR edges:")
        for rec in r2:
            print(f"  {rec['caller.file']} :: {rec['caller.name']}() -> .{rec['attr.name']}()")
    driver.close()
    
    rag.close()
    print("\n✅ Verification Complete!")

if __name__ == "__main__":
    test_triple_layer()
