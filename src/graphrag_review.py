"""
Senior Engineer Review: GraphRAG Completeness Check
Answers:
1. Where is update_template_context defined/used?
2. Where is do_teardown_appcontext defined/used?
3. Does GraphRAG return files or individual call sites?
4. Can it handle self.method() calls?
"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))

def query_symbol(name):
    print(f"\n{'='*60}")
    print(f"ANALYSIS: {name}")
    print('='*60)
    
    with driver.session() as s:
        # 1. Where is it DEFINED?
        r1 = s.run("""
            MATCH (f:Function {name: $name})
            RETURN f.file as file, f.scope as scope
        """, name=name)
        defs = list(r1)
        print(f"\n📍 DEFINITIONS ({len(defs)} found):")
        for rec in defs:
            scope = rec['scope'] or '(module-level)'
            print(f"   - {rec['file']} :: {scope}.{name}")
        
        # 2. Where is it CALLED (as direct function call)?
        r2 = s.run("""
            MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $name})
            RETURN caller.name as caller, caller.file as file, caller.scope as scope
        """, name=name)
        calls = list(r2)
        print(f"\n📞 CALLERS ({len(calls)} found):")
        for rec in calls:
            scope = rec['scope'] or ''
            caller = f"{scope}.{rec['caller']}" if scope else rec['caller']
            print(f"   - {rec['file']} :: {caller}()")
        
        # 3. What GraphRAG.get_callers() would return (just files)
        r3 = s.run("""
            MATCH (caller:Function)-[:CALLS]->(callee:Function {name: $name})
            RETURN DISTINCT caller.file as file
        """, name=name)
        files = [r['file'] for r in r3]
        print(f"\n📁 GraphRAG.get_callers() returns: {files}")

query_symbol("update_template_context")
query_symbol("do_teardown_appcontext")
query_symbol("handle_exception")

# Limitation analysis
print("\n" + "="*60)
print("⚠️  GRAPHRAG LIMITATIONS (Senior Engineer Review)")
print("="*60)
print("""
1. ONLY DIRECT CALLS DETECTED:
   - ✅ Detects: func() or module.func()
   - ❌ Misses: self.func() (instance method calls)
   - ❌ Misses: getattr(obj, 'func')()
   - ❌ Misses: callbacks passed as arguments

2. NO INSTANCE TRACKING:
   - ❌ Cannot trace: app.do_teardown_appcontext()
   - ❌ Cannot trace: flask_app.update_template_context()
   - This is because AST sees 'attr' access, not resolved types

3. RETURN TYPE:
   - Returns: List of FILE PATHS only
   - Does NOT return: Line numbers, call context, or caller signatures

4. INHERITANCE NOT RESOLVED:
   - If SubClass overrides method, CALLS to SubClass.method
     won't link to BaseClass.method

RECOMMENDATION: GraphRAG is useful for HEURISTIC guidance but not
complete. It should be COMBINED with:
- Zoekt keyword search (for string matches like 'do_teardown')
- LLM reasoning (to infer usage patterns)
""")

driver.close()
