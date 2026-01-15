# Artificial Architect: Setup Guide

You have successfully built the core of the **Artificial Architect**.

## 🚀 Getting Started (Docker Mode)

The entire system is now containerized. You do not need to install local dependencies.

### 1. Configure Secrets
Rename `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
# Edit .env with your keys
```

### 2. Prepare the Data
Create the directories for the persistent data:
```bash
mkdir repos index-data
```
*   `repos/`: Put your AOSP (or Pilot) source code mirrors here.
*   `index-data/`: Zoekt will store its index here.

### 3. Launch the Stack
```bash
docker-compose up --build -d
```
This will spin up:
*   `agent-brain`: The Python Orchestrator.
*   `neo4j`: The Graph Database (Access at http://localhost:7474).
*   `zoekt-web`: The Code Search Engine (Access at http://localhost:6070).

### 4. Verify
Check logs:
```bash
docker-compose logs -f agent-brain
```

### 5. Running the Agent (CLI)
Since the container runs in idle mode, you execute commands using `docker exec`:

#### A. Run on a Single Issue
```bash
docker exec -it pro-agent-brain-1 python src/main.py --issue "Fix NullPointer in Auth" --repo-type general
```

#### B. Run Shadow Mode Evaluation
Run against a dataset of PRs (e.g., Flask PR #5818):
```bash
docker exec -e TARGET_REPO="https://github.com/pallets/flask" -it pro-agent-brain-1 \
  python src/main.py --shadow datasets/flask_pr5818.json --repo-type general
```

#### C. Setup a New Repo
Clones and indexes a repository for the agent to use:
```bash
docker exec -it pro-agent-brain-1 python src/main.py --setup https://github.com/pallets/flask
```

#### D. Fetch PRs from GitHub
Creates a dataset from recent PRs (requires GITHUB_TOKEN):
```bash
docker exec -e GITHUB_TOKEN="<token>" -it pro-agent-brain-1 python src/main.py --fetch-prs pallets/flask
```

## 🏗️ Architecture Modules
*   `src/core/orchestrator.py`: The **LangGraph** State Machine (Brain).
*   `src/tools/sandbox.py`: The **Docker** Execution Wrapper (Hands).
*   `src/critic/safety.py`: The **Semgrep** Security Scanner (Conscience).
