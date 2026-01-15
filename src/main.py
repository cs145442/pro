import asyncio
import argparse
import os
import json
from dotenv import load_dotenv
from rich.console import Console
import logging
from src.core.orchestrator import AgentOrchestrator
from src.core.scorecard import ScorecardGenerator
from src.critic.shadow_test import ShadowTestRunner

from src.tools.github_fetcher import GitHubPRFetcher
from src.tools.world_builder import WorldBuilder

load_dotenv()
console = Console()

# Configure File Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/agent.log",
    filemode='w',
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(
        description="Artificial Architect - AI Software Engineer Evaluation Framework"
    )
    parser.add_argument(
        "--issue", "-i",
        type=str,
        help="Single issue description to process"
    )
    # ... existing args ...
    parser.add_argument(
        "--setup",
        type=str,
        help="Setup the world: Clone and Index a repository (e.g. 'square/okhttp')"
    )
    # ... existing args ...

    parser.add_argument(
        "--shadow", "-s",
        type=str,
        help="Path to shadow test dataset JSON for FOR evaluation"
    )
    parser.add_argument(
        "--fetch-prs",
        type=str,
        help="Fetch recent PRs from a GitHub repo (e.g. 'square/okhttp') to create shadow_dataset.json"
    )
    parser.add_argument(
        "--repo-type", "-r",
        type=str,
        default=os.getenv("REPO_TYPE", "general"),
        choices=["aosp", "okhttp", "signal", "general"],
        help="Target repository type for prompt tuning"
    )
    parser.add_argument(
        "--create-sample-dataset",
        action="store_true",
        help="Generate a sample shadow test dataset"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit the number of shadow test cases to run (0 = all)"
    )
    return parser.parse_args()

async def run_single_issue(agent: AgentOrchestrator, issue: str):
    """Run the agent on a single issue and generate report."""
    console.print(f"[bold yellow]Running on Issue:[/bold yellow] {issue}")
    
    final_state = await agent.run(issue)
    report_path = ScorecardGenerator.generate_markdown_report(final_state)
    
    console.print("[bold green]Agent Finished![/bold green]")
    console.print(f"[bold cyan]Scorecard Generated:[/bold cyan] {report_path}")
    return final_state

async def run_shadow_mode(agent: AgentOrchestrator, dataset_path: str, limit: int = 0):
    """Run the agent in Shadow Mode for FOR evaluation."""
    console.print(f"[bold magenta]Running Shadow Mode Evaluation[/bold magenta]")
    console.print(f"Dataset: {dataset_path}")
    
    runner = ShadowTestRunner(dataset_path)
    dataset = runner.load_dataset(dataset_path)
    
    if not dataset:
        console.print("[bold red]No dataset found![/bold red]")
        return
    
    if limit > 0:
        console.print(f"[yellow]Limiting execution to first {limit} cases[/yellow]")
        dataset = dataset[:limit]
    
    console.print(f"Loaded {len(dataset)} test cases")
    
    for case in dataset:
        console.print(f"\n[bold yellow]Testing Case: {case['id']}[/bold yellow]")
        
        # Determine Repo Path
        target_repo = os.getenv("TARGET_REPO", "")
        repo_name = target_repo.split("/")[-1].replace(".git", "") if target_repo else ""
        repo_path = f"/workspace/repos/{repo_name}" if repo_name else "/workspace"

        # TIME TRAVEL: Checkout the base commit if provided
        if "base_commit" in case:
            agent.sandbox.checkout_commit(case["base_commit"], workdir=repo_path)
            
        try:
            final_state = await agent.run(case['description'])
            
            # --- BLIND ORACLE VERIFICATION (Post-Execution) ---
            has_oracle = "oracle_tests" in case and case["oracle_tests"]
            diff = final_state.get('generated_diff')
            console.print(f"[DEBUG] Oracle Check: has_oracle={has_oracle}, diff_len={len(diff) if diff else 0}")
            if has_oracle:
                 if diff:
                     console.print(f"   [bold magenta]Running Oracle Verification on {len(case['oracle_tests'])} golden tests...[/bold magenta]")
                     # We call the validator manually here
                     oracle_result = await agent.for_validator.validate_patch(
                         repo_path, 
                         diff, 
                         # Simple detection, can be improved
                         language=agent._detect_language(repo_path),
                         oracle_test_files=case['oracle_tests'],
                         sandbox=agent.sandbox # Use Remote Sandbox
                     )
                     
                     # Update final state with Oracle results
                     final_state['oracle_score'] = oracle_result.get('for_score')
                     final_state['for_score'] = oracle_result.get('for_score') # Override main score
                     final_state['oracle_details'] = oracle_result.get('details')
                     
                     # Append to feedback so it shows in report
                     final_state.setdefault('critic_feedback', []).append(f"Oracle Verdict: {oracle_result.get('details')}")
                     
                     if oracle_result.get('for_score') == 100:
                         console.print("   [bold green]✅ Oracle Verification PASSED[/bold green]")
                     else:
                         console.print("   [bold red]❌ Oracle Verification FAILED[/bold red]")

            # Agent "approves" if safety_score > 90
            approved = final_state.get('safety_score', 0) > 90
            
            # Generate Detailed Scorecard for this PR
            report_path = ScorecardGenerator.generate_markdown_report(final_state)
            console.print(f"   ↳ Scorecard saved: {report_path}")

            runner.record_result(
                issue_id=case['id'],
                known_bug=case.get('has_bug', False),
                agent_approved=approved,
                details=f"Score: {final_state.get('safety_score')} | Report: {report_path}"
            )
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            runner.record_result(case['id'], case.get('has_bug', False), False, str(e))
        finally:
            # RESET TIME: Always go back to main
            if "base_commit" in case:
                agent.sandbox.reset_to_main(workdir=repo_path)
    
    # Print Summary
    summary = runner.summary()
    console.print("\n[bold cyan]═══ SHADOW MODE RESULTS ═══[/bold cyan]")
    console.print(f"Total Tests: {summary['total_tests']}")
    console.print(f"False Omissions: {summary['false_omissions']}")
    console.print(f"FOR Percentage: {summary['for_percentage']}%")
    console.print(f"[bold]FOR Safety Score: {summary['for_score']}/100[/bold]")
    
    # Save Results to Disk
    import time
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("reports", exist_ok=True)
    report_file = f"reports/shadow_results_{timestamp}.json"
    with open(report_file, "w") as f:
        json.dump(runner.results, f, default=lambda o: o.__dict__, indent=2)
    console.print(f"[green]Detailed results saved to: {report_file}[/green]")

async def main():
    args = parse_args()
    
    # Handle World Setup
    if args.setup:
        builder = WorldBuilder()
        builder.setup_world(args.setup)
        return

    # Handle sample dataset creation
    if args.create_sample_dataset:
        runner = ShadowTestRunner()
        path = runner.create_sample_dataset()
        console.print(f"[green]Sample dataset created: {path}[/green]")
        return
        
    # Handle GitHub Fetching
    if args.fetch_prs:
        token = os.getenv("GITHUB_TOKEN")
        fetcher = GitHubPRFetcher(args.fetch_prs, token)
        dataset = fetcher.fetch_recent_prs(days=90)
        path = fetcher.save_dataset(dataset)
        console.print(f"[green]Shadow Dataset Created: {path}[/green]")
        console.print(f"Run with: python src/main.py --shadow {path}")
        return
    
    console.print("[bold green]Artificial Architect System Initializing...[/bold green]")
    
    # Required API keys
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY not found in .env")
    
    # Optional (will fall back to OpenAI if missing)
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️ ANTHROPIC_API_KEY not found - will use OpenAI GPT-4.1 for Brain")
    
    if not os.getenv("GITHUB_TOKEN"):
        print("⚠️ GITHUB_TOKEN not found - API rate limits will apply")

    # Initialize the Brain
    console.print(f"[bold blue]Initializing Agent for: {args.repo_type}[/bold blue]")
    agent = AgentOrchestrator(repo_type=args.repo_type)
    
    try:
        await agent.startup()
        
        if args.shadow:
            await run_shadow_mode(agent, args.shadow, args.limit)
        elif args.issue:
            await run_single_issue(agent, args.issue)
        else:
            # Default: use sample issue
            sample = "Fix NullPointerException in WifiManager.java when toggling airplane mode."
            await run_single_issue(agent, sample)
            
    except Exception as e:
        console.print(f"[bold red]Agent Failed:[/bold red] {e}")
    finally:
        await agent.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
