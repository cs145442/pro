from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from src.core.state import AgentState
from src.core.mttr_tracker import MTTRTracker
from src.perception.zoekt_client import ZoektClient
from src.perception.graph_rag import GraphRAG
from src.tools.sandbox import SandboxEnvironment
from src.critic.safety import SafetyCritic
from src.critic.compliance import ComplianceCritic
from src.critic.risk_calibrator import RiskCalibrator
from src.critic.hallucination_detector import HallucinationDetector
from src.critic.for_validator import FORValidator  # NEW: Priority 1
from src.critic.spec_gaming_detector import SpecGamingDetector  # NEW: Priority 1
from src.critic.prompt_injection_tester import PromptInjectionTester  # NEW: Priority 1
from src.critic.code_quality_analyzer import CodeQualityAnalyzer  # NEW: Priority 2
from src.core.tool_tracker import ToolUsageTracker  # NEW: Priority 3
from src.metric.technical_debt_tracker import TechnicalDebtTracker  # NEW: Priority 3
from src.config.agent_config import AgentConfig
import os

class AgentOrchestrator:
    def __init__(self, repo_type="aosp"):
        # 1. The Brain (with fallback)
        
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key and not anthropic_key.startswith("#"):
            try:
                from langchain_anthropic import ChatAnthropic
                self.llm = ChatAnthropic(model=AgentConfig.BRAIN_MODEL, temperature=0)
                self.brain_model = AgentConfig.BRAIN_MODEL
                self.brain_provider = "anthropic"
                print(f"🧠 Brain: Using {self.brain_model} (Anthropic)")
            except Exception as e:
                print(f"⚠️ Anthropic init failed ({e}), falling back to {AgentConfig.FALLBACK_MODEL}")
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(model=AgentConfig.FALLBACK_MODEL, temperature=0)
                self.brain_model = AgentConfig.FALLBACK_MODEL
                self.brain_provider = "openai"
        else:
            print(f"⚠️ Anthropic API key not configured, using {AgentConfig.FALLBACK_MODEL}")
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(model=AgentConfig.FALLBACK_MODEL, temperature=0)
            self.brain_model = AgentConfig.FALLBACK_MODEL
            self.brain_provider = "openai"
        
        # 2. The Tools
        self.zoekt = ZoektClient()
        self.graph_rag = GraphRAG()
        self.sandbox = SandboxEnvironment()
        
        # 3. The Critics (Multi-Paradigm)
        self.safety = SafetyCritic()  # Medical Paradigm
        self.compliance = ComplianceCritic()  # Legal Paradigm
        self.risk_calibrator = RiskCalibrator()  # Financial Paradigm
        self.hallucination_detector = HallucinationDetector()  # Legal Paradigm
        self.for_validator = FORValidator()  # NEW: Medical Paradigm - Priority 1
        self.spec_gaming = SpecGamingDetector()  # NEW: Behavioral Paradigm - Priority 1
        self.pirr_tester = PromptInjectionTester()  # NEW: Defense Paradigm - Priority 1
        self.code_quality = CodeQualityAnalyzer()  # NEW: Financial Paradigm - Priority 2
        self.tool_tracker = ToolUsageTracker()  # NEW: Behavioral Paradigm - Priority 3
        self.tdr_tracker = TechnicalDebtTracker()  # NEW: Financial Paradigm - Priority 3
        
        # 4. Metrics
        self.mttr_tracker = None  # Initialized per run (Defense Paradigm)

        # 3. Dynamic Prompts
        role_description = {
            "aosp": "Senior Android Platform Engineer (AOSP Specialist)",
            "okhttp": "Senior Java Libraries Engineer (Network Stack Specialist)",
            "signal": "Senior Mobile Security Engineer (Rust/Java Specialist)",
            "general": "Senior Software Engineer"
        }.get(repo_type, "Senior Software Engineer")

        # Reasoning-enhanced planning prompt (for o3-mini)
        self.plan_prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are a {role_description}. Your task is to create a comprehensive implementation plan.\n\n"
                       f"IMPORTANT: Before creating your plan, think step-by-step through:\n"
                       f"1. What files are DIRECTLY affected by this change?\n"
                       f"2. What are ALL the callers of any modified functions? (Check GraphRAG output in context)\n"
                       f"3. What edge cases or side effects might this change introduce?\n"
                       f"4. Is the requirement clear and unambiguous?\n"
                       f"   - If the issue description is vague (e.g., 'make it faster', 'fix the bug'), "
                       f"ASK CLARIFYING QUESTIONS instead of assuming.\n"
                       f"   - If unclear about which approach to take, list alternatives and recommend one.\n\n"
                       f"Then, create a detailed step-by-step implementation plan with all files that need modification."),
            ("user", "Issue: {issue}\n\nContext:\n{context}\n\nPlan:")
        ])
        
        self.code_prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are a {role_description}. Your task is to modify the code to solve the issue. \n"
                       f"Do NOT generate a git diff. Instead, use SEARCH/REPLACE blocks for each change.\n"
                       f"Format:\n"
                       f"<<<<<<< SEARCH\n"
                       f"[Exact content to find]\n"
                       f"=======\n"
                       f"[New content to replace with]\n"
                       f">>>>>>> REPLACE\n\n"
                       f"Rules:\n"
                       f"1. The SEARCH block must contain enough context to be unique.\n"
                       f"2. The SEARCH block must match the existing code EXACTLY (including whitespace).\n"
                       f"3. Include the 'File: <path>' line before each block to specify the target file.\n"),
            ("user", "Plan: {plan}\n\nExisting Files:\n{files}\n\nGenerate Search/Replace Blocks:")
        ])

        self.graph = self._build_graph()

    def _get_llm_for_node(self, node_name: str, temperature: float = 0):
        """
        Get the appropriate LLM for a specific node with fallback support.
        Tries primary model first, falls back to cheaper model on API errors.
        """
        node_config = AgentConfig.NODE_MODELS.get(node_name, {})
        primary_model = node_config.get("primary", AgentConfig.BRAIN_MODEL)
        fallback_model = node_config.get("fallback", AgentConfig.FALLBACK_MODEL)
        
        # Determine provider from model name
        def _get_llm(model_name, temp):
            # O-series reasoning models (o1, o3, o4) don't support temperature
            supports_temperature = not model_name.startswith(("o1", "o3", "o4"))
            
            if model_name.startswith("claude"):
                from langchain_anthropic import ChatAnthropic
                if supports_temperature:
                    return ChatAnthropic(model=model_name, temperature=temp)
                else:
                    return ChatAnthropic(model=model_name)
            else:  # OpenAI models (gpt, o-series)
                from langchain_openai import ChatOpenAI
                if supports_temperature:
                    return ChatOpenAI(model=model_name, temperature=temp)
                else:
                    return ChatOpenAI(model=model_name)
        
        try:
            llm = _get_llm(primary_model, temperature)
            print(f"🧠 [{node_name}] Using {primary_model}")
            return llm
        except Exception as e:
            print(f"⚠️ [{node_name}] {primary_model} failed ({e}), using fallback {fallback_model}")
            return _get_llm(fallback_model, temperature)


    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("orient", self.orient_node)
        workflow.add_node("plan", self.plan_node)
        workflow.add_node("code", self.code_node)
        workflow.add_node("critic", self.critic_node)
        workflow.set_entry_point("orient")
        workflow.add_edge("orient", "plan")
        workflow.add_edge("plan", "code")
        workflow.add_edge("code", "critic")
        workflow.add_conditional_edges("critic", self.check_review, {"approved": END, "rejected": "plan"})
        return workflow.compile()

    async def orient_node(self, state: AgentState):
        """Phase 1: Query Zoekt & Graph for context."""
        try:
            print(f"--- Orienting on: {state['issue_description'][:50]}... ---")
            print(f"[DEBUG] State keys: {list(state.keys())}")
            print(f"[DEBUG] State types: {[(k, type(v).__name__) for k, v in state.items()]}")
            
            # 1. Zoekt Search
            # Scope search to the target repo to avoid stale results from other repos
            target_repo_url = os.getenv("TARGET_REPO", "")
            target_repo_name = target_repo_url.split("/")[-1] if target_repo_url else ""
            
            # PRE-FLIGHT CHECK: Verify Repo Exists on Disk
            repo_disk_path = f"repos/{target_repo_name}"
            if target_repo_name and not os.path.exists(repo_disk_path):
                 print(f"[WARNING] Repo folder '{repo_disk_path}' missing. Triggering Auto-Indexing...")
                 from src.tools.world_builder import WorldBuilder
                 wb = WorldBuilder()
                 wb.setup_world(target_repo_url)

            keywords = state['issue_description'].split()[:3]
            query_terms = " ".join(keywords)
            # Add repo filter constraint
            query = f"{query_terms} repo:{target_repo_name}" if target_repo_name else query_terms
            
            print(f"[DEBUG] Zoekt query: {query}")
            results = self.zoekt.search(query, num_results=5)
            print(f"[DEBUG] Zoekt returned {len(results)} results")
            
            context_snippets = []
            files_found = []
            for r in results:
                # Handle both string results and dict results
                if isinstance(r, str):
                    path = r
                elif isinstance(r, dict):
                    path = r.get("FileName", r.get("Name", "unknown"))
                else:
                    print(f"[WARNING] Unexpected result type: {type(r)}")
                    continue
                    
                context_snippets.append(f"File Found: {path}")
                files_found.append(path)

            # 1.5. Auto-Healing: Fallback if search still fails (e.g. index corruption)
            if not files_found and target_repo_name:
                 print("[WARNING] No files found in index even after pre-check. Re-triggering indexing just in case.")
                 target_repo = os.getenv("TARGET_REPO")
                 if not target_repo:
                     raise ValueError("TARGET_REPO env var not set! Cannot auto-index.")
                     
                 from src.tools.world_builder import WorldBuilder
                 wb = WorldBuilder()
                 wb.setup_world(target_repo)
                 
                 # Retry Search
                 print("[INFO] Indexing complete. Retrying search...")
                 results = self.zoekt.search(query, num_results=3)
                 for r in results:
                     if isinstance(r, dict):
                         path = r.get("FileName", r.get("Name", "unknown"))
                         files_found.append(path)
                         context_snippets.append(f"File Found: {path}")
                
            # 1.5. Build Semantic Graph (GraphRAG)
            try:
                from src.perception.graph_builder import GraphBuilder
                print("[GraphRAG] Building semantic graph...")
                
                # Map Sandbox Path (/workspace/repos) to Brain Path (/app/repos)
                # The agent-brain container mounts ./repos to /app/repos
                repo_path_brain = state['repo_path'].replace("/workspace/repos", "/app/repos")
                
                if not os.path.exists(repo_path_brain):
                     print(f"[GraphRAG] Warning: Brain path {repo_path_brain} does not exist. Using original {state['repo_path']}")
                     repo_path_brain = state['repo_path']
                
                gb = GraphBuilder(uri=os.getenv("NEO4J_URI"), user=os.getenv("NEO4J_USERNAME"), password=os.getenv("NEO4J_PASSWORD"))
                gb.build_graph(repo_path_brain)
                gb.close()
            except Exception as e:
                print(f"[ERROR] GraphBuilder failed: {e}")
            
            # 2. Graph Retrieval (Semantic Dependency Analysis)
            dependencies = []
            
            # 2a. Identify functions modified in the plan (heuristic)
            # We look for function names in the issue description or search results
            import re
            potential_symbols = set()
            # Extract function-like names from issue description
            potential_symbols.update(re.findall(r'`(\w+)`', state['issue_description']))
            potential_symbols.update(re.findall(r'(\w+)\(\)', state['issue_description']))
            
            # Also extract from found files (basic parsing of function definitions)
            for file_path in files_found:
                 try:
                     content = self.sandbox.execute_command(f"cat {file_path}", workdir=state['repo_path'])
                     # Find all "def func_name" in the file
                     defs = re.findall(r'def\s+(\w+)\s*\(', content)
                     potential_symbols.update(defs)
                 except:
                     pass
            
            print(f"[GraphRAG] Analyzing impact for symbols: {list(potential_symbols)[:5]}...")
            
            # Triple-Layer Dependency Analysis
            for symbol in potential_symbols:
                dependent_files = set()
                
                # Layer 1: Direct function calls (func())
                direct_callers = self.graph_rag.get_callers(symbol)
                if direct_callers:
                    print(f"[GraphRAG Layer 1] Direct callers of {symbol}: {direct_callers}")
                    dependent_files.update(direct_callers)
                
                # Layer 2: Attribute-based calls (self.method(), obj.method())
                attr_callers = self.graph_rag.get_attr_callers(symbol)
                if attr_callers:
                    print(f"[GraphRAG Layer 2] Attribute callers of {symbol}: {attr_callers}")
                    dependent_files.update(attr_callers)
                
                # Layer 3: Zoekt keyword search (safety net)
                try:
                    zoekt_results = self.zoekt.search(symbol, num_results=10)
                    zoekt_files = [r.get('FileName', r.get('Name')) for r in zoekt_results if isinstance(r, dict)]
                    if zoekt_files:
                        print(f"[GraphRAG Layer 3] Zoekt matches for {symbol}: {len(zoekt_files)} files")
                        dependent_files.update(zoekt_files)
                except Exception as e:
                    print(f"[GraphRAG Layer 3] Zoekt search failed: {e}")
                
                # Add all discovered dependencies to context
                for dep_file in dependent_files:
                    if dep_file not in files_found:
                        files_found.append(dep_file)
                        context_snippets.append(f"File Found (Impact Analysis - {symbol}): {dep_file}")
                        dependencies.append(f"{dep_file} depends on {symbol}")
            
            # 2b. Check file-level dependencies
            for f in files_found:
                deps = self.graph_rag.get_dependencies(f)
                if deps:
                    dependencies.extend(deps)
                    context_snippets.append(f"⚠️ Dependency Warning: Modifying {f} may break {deps}")

            print(f"--- Found {len(files_found)} files and {len(dependencies)} dependencies ---")
            print(f"[DEBUG] Returning context_snippets type: {type(context_snippets)}")
            return {"retrieved_context": context_snippets, "known_dependencies": dependencies}
        except Exception as e:
            print(f"[ERROR] orient_node failed: {e}")
            import traceback
            traceback.print_exc()
            raise


    async def plan_node(self, state: AgentState):
        """Phase 2: Generate Plan using LLM."""
        try:
            print("--- Architecting Plan ---")
            print(f"[DEBUG] plan_node received state keys: {list(state.keys())}")
            print(f"[DEBUG] retrieved_context type: {type(state.get('retrieved_context'))}")
            
            # Use reasoning model (o3-mini) for planning
            llm = self._get_llm_for_node("plan")
            chain = self.plan_prompt | llm
            
            context_list = state.get('retrieved_context', [])
            if isinstance(context_list, str):
                print(f"[WARNING] retrieved_context is a string, converting to list")
                context_list = [context_list]
            
            input_vars = {
                "issue": state['issue_description'],
                "context": "\n".join(context_list)
            }
            print(f"[DEBUG] Calling LLM with input_vars keys: {list(input_vars.keys())}")
            
            response = await chain.ainvoke(input_vars)
            print(f"[DEBUG] LLM responded with content length: {len(response.content)}")
            plan_steps = response.content.split("\n")
            
            # Track token usage
            tokens = state.get('tokens_used', {"brain": 0, "critics": 0, "total": 0})
            print(f"[DEBUG] tokens before: {tokens}")
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_in = response.usage_metadata.get('input_tokens', 0)
                tokens_out = response.usage_metadata.get('output_tokens', 0)
                tokens['brain'] += tokens_in + tokens_out
                tokens['total'] += tokens_in + tokens_out
                print(f"[DEBUG] Added {tokens_in + tokens_out} tokens")
            
            print(f"[DEBUG] Returning plan with {len(plan_steps)} steps")
            return {"plan": plan_steps, "tokens_used": tokens}
        except Exception as e:
            print(f"[ERROR] plan_node failed: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def code_node(self, state: AgentState):
        """Phase 3: Write Code using LLM with Self-Correction Loop."""
        print("--- Writing Implementation ---")
        
        max_retries = 3
        self_correction_attempts = 0
        validation_error = None
        failed_files = set()  # Track files that failed validation
        
        for attempt in range(max_retries):
            # 1. Read files from Sandbox (Real I/O)
            file_contents = ""
            files_to_read = state.get('retrieved_context', [])
            
            for item in files_to_read:
                if "File Found: " in item:
                    file_path = item.split("File Found: ")[1].strip()
                    try:
                        print(f"[DEBUG] Reading file from Sandbox: {file_path} (cwd={state['repo_path']})")
                        content = self.sandbox.execute_command(f"cat {file_path}", workdir=state['repo_path'])
                        if "cat: " in content and "No such file" in content:
                            print(f"[WARNING] File not found in sandbox: {file_path}")
                            continue
                            
                        # Limit output to prevent context overflow
                        MAX_FILE_SIZE = 5000
                        if len(content) > MAX_FILE_SIZE:
                            content = content[:MAX_FILE_SIZE//2] + "\n...[TRUNCATED_BY_AGENT]...\n" + content[-MAX_FILE_SIZE//2:]
                        
                        file_contents += f"\n\n--- {file_path} ---\n{content}\n"
                    except Exception as e:
                        print(f"[ERROR] Failed to read {file_path}: {e}")
                        file_contents += f"\n(Could not read {file_path}: {e})"

            # 2. Build prompt with error context
            plan_text = "\n".join(state['plan'])
            
            # Add explicit error feedback if retrying
            if attempt > 0 and validation_error:
                error_context = f"""

⚠️ CRITICAL ERROR - YOUR PREVIOUS ATTEMPT FAILED ⚠️
Attempt {attempt} failed with the following error:
---
{validation_error}
---

INSTRUCTIONS FOR THIS RETRY:
1. DO NOT modify the same file with the same change that caused the error.
2. If the error is a SyntaxError, you likely have an unmatched quote or bracket.
3. If the error is an ImportError/TypeError, your code has a logic bug.
4. Focus ONLY on the source code files (*.py), NOT documentation files (*.rst).
5. Generate a DIFFERENT and CORRECT solution this time.
"""
                plan_text = error_context + "\n\nOriginal Plan:\n" + plan_text
                
                # Add list of files to avoid if they repeatedly fail
                if failed_files:
                    plan_text += f"\n\n🚫 DO NOT MODIFY these files (they caused errors): {', '.join(failed_files)}"

            # 3. Generate diff with DYNAMIC TEMPERATURE for retries
            # Increase temperature on retries to get different outputs
            retry_temperature = min(0.3 * attempt, 0.7)  # 0, 0.3, 0.6
            
            if attempt > 0 and retry_temperature > 0:
                # Create new LLM instance with higher temperature for this retry
                print(f"[Self-Correction] Using temperature={retry_temperature} for retry #{attempt}")
                if self.brain_provider == "openai":
                    from langchain_openai import ChatOpenAI
                    retry_llm = ChatOpenAI(model=AgentConfig.NODE_MODELS["code"]["primary"], temperature=retry_temperature)
                else:
                    from langchain_anthropic import ChatAnthropic
                    retry_llm = ChatAnthropic(model=AgentConfig.NODE_MODELS["code"]["primary"], temperature=retry_temperature)
                chain = self.code_prompt | retry_llm
            else:
                # First attempt: use gpt-4.1-mini for massive context window
                chain = self.code_prompt | self._get_llm_for_node("code")
            
            input_vars = {
                "plan": plan_text,
                "files": file_contents or "(New File Creation)"
            }
            response = await chain.ainvoke(input_vars)
            diff = response.content
            
            # Clean diff (strip markdown fences if present)
            if diff.startswith("```"):
                lines = diff.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                diff = "\n".join(lines)
            
            # Track token usage
            tokens = state.get('tokens_used', {"brain": 0, "critics": 0, "total": 0})
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_in = response.usage_metadata.get('input_tokens', 0)
                tokens_out = response.usage_metadata.get('output_tokens', 0)
                tokens['brain'] += tokens_in + tokens_out
                tokens['total'] += tokens_in + tokens_out
            
            # 4. Validate in sandbox (3-level validation)
            is_valid, error = await self._validate_syntax_in_sandbox(diff, state['repo_path'])
            
            if is_valid:
                print(f"[Self-Correction] Validation passed on attempt {attempt + 1}")
                return {
                    "generated_diff": diff, 
                    "tokens_used": tokens,
                    "self_correction_attempts": self_correction_attempts,
                    "validation_error": None
                }
            
            # Validation failed, prepare for retry
            self_correction_attempts += 1
            validation_error = error
            
            # Extract failed file from error and track it
            if "Error in " in error:
                failed_file = error.split("Error in ")[1].split(":")[0].strip()
                failed_files.add(failed_file)
            
            print(f"[Self-Correction] Attempt {attempt + 1} failed validation: {error}")
        
        # After max retries, return best effort (let critic catch it)
        print(f"[Self-Correction] Max retries ({max_retries}) exhausted. Returning best effort.")
        return {
            "generated_diff": diff, 
            "tokens_used": tokens,
            "self_correction_attempts": self_correction_attempts,
            "validation_error": validation_error
        }

    async def critic_node(self, state: AgentState):
        """Phase 4: Safety & Compliance Check."""
        print("--- Running Critic Loop ---")
        
        diff = state['generated_diff']
        
        # 1. Write diff to local temp file for Semgrep
        temp_file = "temp_patch.java"
        with open(temp_file, "w") as f:
            f.write(diff) # In reality, we'd apply the patch to the source file, then scan the source file.
            
        # 2. Safety Check
        # Safety scan with tool tracking
        try:
            safety_issues = self.safety.scan_diff(temp_file) 
            self.tool_tracker.log_invocation("safety_scan", True)
        except Exception as e:
            self.tool_tracker.log_invocation("safety_scan", False, str(e))
            safety_issues = [f"Safety scan failed: {e}"]

        safety_score = 100 - (len(safety_issues) * 20)
        
        # Cleanup
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        # 3. Compliance Check
        compliance_feedback = await self.compliance.review(diff)
        
        # Parse compliance feedback to generate score
        compliance_score = 100  # Start optimistic
        feedback_lower = compliance_feedback.lower()
        
        # Check for violations
        if "violation" in feedback_lower and "none found" not in feedback_lower:
            compliance_score -= 30
        if "missing" in feedback_lower or "should be added" in feedback_lower:
            compliance_score -= 20
        if "restricted import" in feedback_lower and "no restricted" not in feedback_lower:
            compliance_score -= 50
        
        # Ensure score is in valid range
        compliance_score = max(0, min(100, compliance_score))
        
        print(f"--- Scores: Safety={safety_score}/100, Compliance={compliance_score}/100 ---")
        
        # 4. FOR Validation (NEW: Priority 1)
        language = self._detect_language(state['repo_path'])
        for_result = await self.for_validator.validate_patch(
            repo_path=state['repo_path'],
            diff=diff,
            language=language,
            sandbox=self.sandbox
        )
        for_score = for_result['for_score']
        tests_broken = for_result['tests_broken']
        print(f"--- FOR: {for_score}/100 (Tests broken: {tests_broken}) ---")
        
        # 5. Specification Gaming Detection (NEW: Priority 1)
        spec_gaming_result = self.spec_gaming.detect_gaming(
            diff=diff,
            pre_execution_snapshot=None  # Could be enhanced with honey-pot in future
        )
        spec_gaming_index = spec_gaming_result['index']
        test_files_modified = spec_gaming_result['test_modified']
        print(f"--- Spec Gaming Index: {spec_gaming_index}/100 ---")
        
        # 6. Prompt Injection Resistance (NEW: Priority 1)
        pirr_result = self.pirr_tester.check_resistance(
            input_description=state['issue_description'],
            generated_diff=diff
        )
        pirr_score = pirr_result['score']
        poisoned_detected = pirr_result['was_poisoned']
        print(f"--- PIRR: {pirr_score}/100 (Poisoned: {poisoned_detected}) ---")
        
        # 7. Code Quality Analysis (NEW: Priority 2)
        language = self._detect_language(state['repo_path'])
        quality_result = self.code_quality.analyze_diff(
            diff=diff,
            language=language
        )
        mi_score = quality_result['maintainability_index']
        cc_average = quality_result['cyclomatic_complexity']
        dup_ratio = quality_result['duplication_ratio']
        avr_count = quality_result['architectural_violations']
        coupling = quality_result['coupling_score']
        print(f"--- Code Quality: MI={mi_score}/100, CC={cc_average:.1f}, Dup={dup_ratio:.1f}%, AVR={avr_count}, Coupling={coupling}/100 ---")
        
        # 8. Tool Use Success Rate (NEW: Priority 3)
        tusr_data = self.tool_tracker.calculate_tusr()
        tusr_score = tusr_data['tusr']
        print(f"--- TUSR: {tusr_score}/100 (Total tools: {tusr_data['total']}, Failed: {tusr_data['failed']}) ---")
        
        # 9. Technical Debt Ratio (NEW: Priority 3)
        work_type = self.tdr_tracker.classify_work_type(
            issue_description=state['issue_description'],
            diff=diff,
            plan=state.get('plan', [])
        )
        tdr_data = self.tdr_tracker.calculate_tdr()
        print(f"--- TDR: {tdr_data['tdr_ratio']:.1f}% ({work_type} work) ---")
        
        # Increment retry count
        retry_count = state.get('retry_count', 0) + 1
        
        # Combine all feedback
        all_feedback = safety_issues + [compliance_feedback]
        if for_result['details']:
            all_feedback.append(f"FOR: {for_result['details']}")
        if spec_gaming_result['violations']:
            all_feedback.append(f"Spec Gaming: {spec_gaming_result['details']}")
        if pirr_result['violations']:
            all_feedback.append(f"PIRR: {pirr_result['details']}")
        if quality_result['details']:
            all_feedback.append(f"Code Quality: MI={mi_score}, CC={cc_average:.1f}")
        
        return {
            "safety_score": safety_score,
            "compliance_score": compliance_score,
            "for_score": for_score,
            "tests_broken": tests_broken,
            "spec_gaming_index": spec_gaming_index,
            "test_files_modified": test_files_modified,
            "pirr_score": pirr_score,
            "poisoned_input_detected": poisoned_detected,
            "maintainability_index": mi_score,
            "cyclomatic_complexity": cc_average,
            "duplication_ratio": dup_ratio,
            "architectural_violations": avr_count,
            "coupling_score": coupling,
            "tusr_score": tusr_score,
            "total_tool_invocations": tusr_data['total'],
            "successful_tool_invocations": tusr_data['successful'],
            "failed_tool_invocations": tusr_data['failed'],
            "tdr_ratio": tdr_data['tdr_ratio'],
            "work_type": work_type,
            "historical_tdr": tdr_data['tdr_ratio'],  # Same for single run
            "critic_feedback": all_feedback,
            "retry_count": retry_count
        }

    async def startup(self):
        """Initialize external tool connections."""
        print("--- Starting Agent Tools ---")
        try:
            self.sandbox.start()
        except Exception as e:
            print(f"Warning: Sandbox failed to start ({e}). Running in mocked I/O mode.")

    def check_review(self, state: AgentState):
        """Decide if code passes or needs revision."""
        MAX_RETRIES = 3
        retry_count = state.get('retry_count', 0)
        
        if retry_count >= MAX_RETRIES:
            print(f"[WARNING] Max retries ({MAX_RETRIES}) reached, accepting current solution")
            print("--- PR APPROVED (Max Retries Reached) ---")
            return "approved"

        # Check safety score
        if state.get('safety_score', 0) >= AgentConfig.SAFETY_THRESHOLD:
            print("--- PR APPROVED ---")
            return "approved"
        else:
            print(f"Safety score {state.get('safety_score')} < {AgentConfig.SAFETY_THRESHOLD} (Attempt {retry_count}/{MAX_RETRIES}), retrying...")
            print("--- PR REJECTED (Retrying) ---")
            return "rejected"
            

    async def _validate_syntax_in_sandbox(self, diff: str, repo_path: str) -> tuple:
        """
        4-Level validation of generated code in sandbox.
        Returns: (is_valid: bool, error_message: Optional[str])
        
        Levels:
        1. Syntax Check (py_compile)
        2. Import Smoke Test 
        3. Test Collection Check
        4. Quick Smoke Test (run 1 fast test to catch runtime errors)
        """
        try:
            print("[Self-Correction] Validating generated code...")
            
            # Extract modified files from the diff using multiple patterns
            import re
            modified_files = set()
            
            # Pattern 1: "File: <path>" prefix
            for line in diff.split('\n'):
                if line.startswith("File: "):
                    file_path = line.split("File: ")[1].strip()
                    modified_files.add(file_path)
            
            # Pattern 2: Look for file paths in the content after SEARCH blocks
            # When LLM doesn't use File: prefix, we try to infer from content
            if not modified_files and "<<<<<<< SEARCH" in diff:
                # Try to detect common Flask file patterns
                common_patterns = [
                    r'(src/flask/\w+\.py)',
                    r'(src/\w+/\w+\.py)',
                    r'(tests/test_\w+\.py)',
                    r'(app\.py)',
                ]
                for pattern in common_patterns:
                    matches = re.findall(pattern, diff)
                    modified_files.update(matches)
                
                # If still no files, try to infer from imports in the diff
                if not modified_files:
                    # Look for unique Python file signatures like 'def wsgi_app' or 'class Flask'
                    if 'def wsgi_app(' in diff or 'class Flask' in diff:
                        modified_files.add('src/flask/app.py')
                    if 'class AppContext' in diff or 'def push(' in diff:
                        modified_files.add('src/flask/ctx.py')
            
            if not modified_files:
                print("[Self-Correction] Warning: No files detected in diff. Assuming src/flask/app.py")
                # Default to the most common file for Flask tasks
                modified_files.add('src/flask/app.py')
            
            print(f"[Self-Correction] Detected modified files: {modified_files}")
            
            # Apply the patch
            sandbox = self.sandbox
            
            if "<<<<<<< SEARCH" in diff:
                # Use custom patcher with enhanced logic
                import base64
                
                # Enhanced patcher that also tries to infer file paths
                patcher_script = r"""
import os
import sys
import re

def apply_patch(patch_text):
    current_file = None
    lines = patch_text.split('\n')
    current_block = {"search": [], "replace": [], "state": "idle"}
    patched_files = []
    
    for line in lines:
        if line.startswith("File: "):
            current_file = line.split("File: ")[1].strip()
        elif line.strip() == "<<<<<<< SEARCH":
            current_block["state"] = "search"
        elif line.strip() == "=======":
            current_block["state"] = "replace"
        elif line.strip() == ">>>>>>> REPLACE":
            # If no current_file, try to infer from search content
            if not current_file:
                search_content = '\n'.join(current_block["search"])
                current_file = infer_file(search_content)
            
            if current_file:
                if do_replace(current_file, current_block["search"], current_block["replace"]):
                    patched_files.append(current_file)
            current_block = {"search": [], "replace": [], "state": "idle"}
            current_file = None  # Reset for next block
        else:
            if current_block["state"] == "search":
                current_block["search"].append(line)
            elif current_block["state"] == "replace":
                current_block["replace"].append(line)
    
    for f in set(patched_files):
        print(f"Patched {f}")

def infer_file(search_content):
    # Try to find the file by searching for the content
    search_dirs = ['src/flask', 'src', 'tests', '.']
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    try:
                        with open(filepath, 'r') as file:
                            content = file.read()
                            # Check if the first few lines match
                            first_lines = '\n'.join(search_content.split('\n')[:3])
                            if first_lines and first_lines in content:
                                return filepath
                    except:
                        pass
    return None

def do_replace(filepath, search_lines, replace_lines):
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r') as f:
        content = f.read()
    search_text = '\n'.join(search_lines)
    replace_text = '\n'.join(replace_lines)
    if search_text in content:
        new_content = content.replace(search_text, replace_text)
        with open(filepath, 'w') as f:
            f.write(new_content)
        return True
    return False

if __name__ == "__main__":
    patch_content = sys.stdin.read()
    apply_patch(patch_content)
"""
                b64_script = base64.b64encode(patcher_script.encode('utf-8')).decode('utf-8')
                sandbox.execute_command(
                    f"python3 -c \"import base64; open('/tmp/val_patcher.py', 'wb').write(base64.b64decode('{b64_script}'))\""
                )
                
                # Write patch content
                b64_patch = base64.b64encode(diff.encode('utf-8')).decode('utf-8')
                sandbox.execute_command(
                    f"python3 -c \"import base64; open('/tmp/val_input.patch', 'wb').write(base64.b64decode('{b64_patch}'))\""
                )
                
                # Run patcher
                patch_cmd = "sh -c 'python3 /tmp/val_patcher.py < /tmp/val_input.patch'"
                patch_out = sandbox.execute_command(patch_cmd, workdir=repo_path)
                print(f"[Self-Correction] Patch output: {patch_out[:300]}")
            
            # Level 1: Syntax Check
            print("[Self-Correction] Level 1: Syntax Check...")
            for file_path in modified_files:
                if file_path.endswith('.py'):
                    result = sandbox.execute_command(f"python -m py_compile {file_path}", workdir=repo_path)
                    if "SyntaxError" in result or ("Error" in result and "No such file" not in result):
                        sandbox.execute_command("git checkout .", workdir=repo_path)
                        return False, f"Syntax Error in {file_path}: {result[:500]}"
            
            # Level 2: Import Smoke Test
            print("[Self-Correction] Level 2: Import Smoke Test...")
            for file_path in modified_files:
                if file_path.endswith(".py") and file_path.startswith("src/"):
                    module_path = file_path.replace("/", ".").replace(".py", "")
                    result = sandbox.execute_command(f"python -c 'import {module_path}'", workdir=repo_path)
                    if "Error" in result and "No module named" not in result:
                        sandbox.execute_command("git checkout .", workdir=repo_path)
                        return False, f"Import Error in {module_path}: {result[:500]}"
            
            # Level 3: Test Collection Smoke Test
            print("[Self-Correction] Level 3: Test Collection...")
            result = sandbox.execute_command("sh -c 'pytest --collect-only --maxfail=1 tests/ 2>&1 | head -30'", workdir=repo_path)
            if "ERROR" in result and "collect" in result.lower():
                sandbox.execute_command("git checkout .", workdir=repo_path)
                return False, f"Test Collection Error: {result[:500]}"
            
            # Level 4: Quick Runtime Smoke Test (run 1 fast test to catch TypeError)
            print("[Self-Correction] Level 4: Quick Runtime Test...")
            # Run a quick subset of tests with short timeout
            result = sandbox.execute_command(
                "sh -c 'timeout 30s pytest tests/test_basic.py::test_appcontext -x 2>&1 | tail -20'", 
                workdir=repo_path
            )
            if "TypeError" in result or "AttributeError" in result or "FAILED" in result:
                sandbox.execute_command("git checkout .", workdir=repo_path)
                return False, f"Runtime Error in quick smoke test: {result[:500]}"
            
            # Rollback after validation
            sandbox.execute_command("git checkout .", workdir=repo_path)
            
            print("[Self-Correction] All validation levels passed!")
            return True, None
            
        except Exception as e:
            print(f"[Self-Correction] Validation error: {e}")
            try:
                sandbox.execute_command("git checkout .", workdir=repo_path)
            except:
                pass
            return False, f"Validation exception: {str(e)}"

    def _detect_language(self, repo_path: str) -> str:
        """Detect primary language of repository for test runner selection."""
        from pathlib import Path
        repo = Path(repo_path)
        
        # Check for language indicators
        if (repo / "pom.xml").exists() or (repo / "build.gradle").exists():
            return "java"
        elif (repo / "package.json").exists():
            return "javascript"
        elif (repo / "go.mod").exists():
            return "go"
        elif (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
            return "python"
        else:
            # Default to python
            return "python"

    async def shutdown(self):
        """Cleanup tool connections."""
        print("--- Shutting Down Agent Tools ---")
        self.sandbox.stop()
        self.graph_rag.close()

    async def run(self, issue_description: str):
        """Entry point to run the agent on an issue."""
        # Initialize MTTR Tracker for this run
        self.mttr_tracker = MTTRTracker()
        
        # Determine correct repo path based on TARGET_REPO
        target_repo = os.getenv("TARGET_REPO")
        repo_path = "/workspace"
        if target_repo:
            repo_name = target_repo.split("/")[-1].replace(".git", "")
            # Check if it exists in repos dir (mounted volume)
            possible_path = f"/workspace/repos/{repo_name}"
            # We assume WorldBuilder has set it up here
            repo_path = possible_path
            
        initial_state = AgentState(
            issue_id="issue-001",
            issue_description=issue_description,
            repo_path=repo_path,
            retrieved_context=[],
            known_dependencies=[],
            plan=[],
            current_step=0,
            generated_diff=None,
            safety_score=0,
            compliance_score=0,
            faithfulness_score=100,  # Legal Paradigm
            risk_level="MEDIUM",  # Financial Paradigm
            risk_score=5,  # Financial Paradigm
            mttr_seconds=0,  # Defense Paradigm
            for_score=100,  # NEW: Medical Paradigm - Priority 1
            tests_broken=0,  # NEW: Medical Paradigm - Priority 1
            spec_gaming_index=100,  # NEW: Behavioral Paradigm - Priority 1
            test_files_modified=False,  # NEW: Behavioral Paradigm - Priority 1
            pirr_score=100,  # NEW: Defense Paradigm - Priority 1
            poisoned_input_detected=False,  # NEW: Defense Paradigm - Priority 1
            maintainability_index=100,  # NEW: Financial Paradigm - Priority 2
            cyclomatic_complexity=0.0,  # NEW: Financial Paradigm - Priority 2
            duplication_ratio=0.0,  # NEW: Financial Paradigm - Priority 2
            architectural_violations=0,  # NEW: Financial Paradigm - Priority 2
            coupling_score=100,  # NEW: Financial Paradigm - Priority 2
            tusr_score=100,  # NEW: Behavioral Paradigm - Priority 3
            total_tool_invocations=0,  # NEW: Behavioral Paradigm - Priority 3
            successful_tool_invocations=0,  # NEW: Behavioral Paradigm - Priority 3
            failed_tool_invocations=0,  # NEW: Behavioral Paradigm - Priority 3
            tdr_ratio=0.0,  # NEW: Financial Paradigm - Priority 3
            work_type="feature",  # NEW: Financial Paradigm - Priority 3
            historical_tdr=0.0,  # NEW: Financial Paradigm - Priority 3
            tokens_used={"brain": 0, "critics": 0, "total": 0},
            models_used={"brain": self.brain_model, "critics": "gpt-4o-mini"},
            critic_feedback=[],
            retry_count=0,
            self_correction_attempts=0,  # NEW: Behavioral Paradigm - Section 8.2
            validation_error=None,  # NEW: Behavioral Paradigm - Section 8.2
            status="STARTING"
        )
        
        result = await self.graph.ainvoke(initial_state)
        
        # Finalize MTTR
        result['mttr_seconds'] = self.mttr_tracker.total_time()
        
        # Record work in TDR tracker (NEW: Priority 3)
        try:
            loc_changed = len(result.get('generated_diff', '').split('\n'))
            self.tdr_tracker.record_work(
                issue_id=result['issue_id'],
                work_type=result['work_type'],
                ces_score=0,  # Will be calculated by scorecard
                loc_changed=loc_changed,
                description=result['issue_description']
            )
        except Exception as e:
            print(f"Warning: Failed to record work in TDR tracker: {e}")
        
        return result
