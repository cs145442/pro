"""
Pre-flight validation for all modified modules.
Runs: Syntax check, Import check, Basic smoke tests.
No LLM calls - just Python runtime checks.
"""
import sys
import traceback

def log(msg, ok=True):
    status = "✅" if ok else "❌"
    print(f"{status} {msg}")

def main():
    errors = []
    
    # 1. SYNTAX CHECK
    print("\n=== 1. SYNTAX VALIDATION ===")
    files_to_check = [
        "src/perception/graph_builder.py",
        "src/perception/graph_rag.py",
        "src/critic/for_validator.py",
        "src/core/orchestrator.py",
        "src/core/state.py",
        "src/core/scorecard.py",
    ]
    
    import py_compile
    for f in files_to_check:
        try:
            py_compile.compile(f, doraise=True)
            log(f"Syntax OK: {f}")
        except py_compile.PyCompileError as e:
            log(f"Syntax ERROR: {f} - {e}", ok=False)
            errors.append(f"Syntax: {f}")
    
    # 2. IMPORT CHECK
    print("\n=== 2. IMPORT VALIDATION ===")
    modules_to_import = [
        ("src.perception.graph_builder", "GraphBuilder"),
        ("src.perception.graph_rag", "GraphRAG"),
        ("src.critic.for_validator", "FORValidator"),
        ("src.core.orchestrator", "AgentOrchestrator"),
        ("src.core.state", "AgentState"),
        ("src.core.scorecard", "ScorecardGenerator"),
    ]
    
    for module_path, class_name in modules_to_import:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            log(f"Import OK: {module_path}.{class_name}")
        except Exception as e:
            log(f"Import ERROR: {module_path}.{class_name} - {e}", ok=False)
            errors.append(f"Import: {module_path}")
            traceback.print_exc()
    
    # 3. SMOKE TESTS (no LLM, no network where possible)
    print("\n=== 3. SMOKE TESTS ===")
    
    # Test GraphBuilder instantiation (skip actual build)
    try:
        from src.perception.graph_builder import GraphBuilder
        # Don't connect to Neo4j, just check class structure
        assert hasattr(GraphBuilder, 'build_graph')
        assert hasattr(GraphBuilder, '_process_file')
        log("GraphBuilder: Class structure OK")
    except Exception as e:
        log(f"GraphBuilder smoke test failed: {e}", ok=False)
        errors.append("Smoke: GraphBuilder")
    
    # Test GraphRAG query methods exist
    try:
        from src.perception.graph_rag import GraphRAG
        assert hasattr(GraphRAG, 'get_callers')
        assert hasattr(GraphRAG, 'get_definitions')
        assert hasattr(GraphRAG, 'get_dependencies')
        log("GraphRAG: Query methods exist")
    except Exception as e:
        log(f"GraphRAG smoke test failed: {e}", ok=False)
        errors.append("Smoke: GraphRAG")
    
    # Test FORValidator has required methods
    try:
        from src.critic.for_validator import FORValidator
        assert hasattr(FORValidator, 'validate_patch')
        assert hasattr(FORValidator, '_detect_test_runner')
        assert hasattr(FORValidator, '_validate_remote')
        log("FORValidator: Methods exist")
    except Exception as e:
        log(f"FORValidator smoke test failed: {e}", ok=False)
        errors.append("Smoke: FORValidator")
    
    # Test AgentState TypedDict has new fields
    try:
        from src.core.state import AgentState
        import typing
        hints = typing.get_type_hints(AgentState)
        assert 'self_correction_attempts' in hints
        assert 'validation_error' in hints
        log("AgentState: Self-correction fields exist")
    except Exception as e:
        log(f"AgentState smoke test failed: {e}", ok=False)
        errors.append("Smoke: AgentState")
    
    # 4. SUMMARY
    print("\n=== SUMMARY ===")
    if errors:
        print(f"❌ {len(errors)} issues found:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    else:
        print("✅ All checks passed! Safe to run shadow test.")
        sys.exit(0)

if __name__ == "__main__":
    main()
