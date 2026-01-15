#!/bin/bash
# Generate unique timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/app/logs/run_${TIMESTAMP}.log"

echo "tStarting Agent... Logs to: ${LOG_FILE}"

# Run the Agent and redirect ALL output to the unique log file
# We also 'tee' it to stdout so `docker logs` still works
# Run the Agent and redirect ALL output to the unique log file
# We also 'tee' it to stdout so `docker logs` still works
# Default behavior: Just keep the container alive for `docker exec` commands
# You can override this by passing specific commands if needed, 
# but for this dev setup, we want it explicitly idle.

echo "----------------------------------------------------------------"
echo "🤖 Artificial Architect Container Ready"
echo "----------------------------------------------------------------"
echo "The container is idle and ready for commands."
echo ""
echo "AVAILABLE COMMANDS (Run via 'docker exec -it <container_name> ...')"
echo "1. Run Single Issue:"
echo "   python src/main.py --issue 'Fix bug X in file Y' --repo-type <type>"
echo ""
echo "2. Run Shadow Mode (Evaluation):"
echo "   python src/main.py --shadow datasets/<file.json> --repo-type <type>"
echo ""
echo "3. Setup World (Clone & Index):"
echo "   python src/main.py --setup <repo_url>"
echo ""
echo "4. Create Sample Dataset:"
echo "   python src/main.py --create-sample-dataset"
echo "----------------------------------------------------------------"
echo "Logs are being written to: ${LOG_FILE}"

tail -f /dev/null
