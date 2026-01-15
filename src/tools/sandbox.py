import docker
import os
from docker.errors import DockerException

class SandboxEnvironment:
    """
    Manages the execution environment for the Agent.
    Ensures that all side-effects (rm -rf /) are contained.
    """
    def __init__(self, image_name=None, container_name=None):
        self.client = docker.from_env()
        # Allow override via env var or arg, default to config
        from src.config.agent_config import AgentConfig
        self.image = image_name or AgentConfig.SANDBOX_IMAGE
        self.container_name = container_name or getattr(AgentConfig, "SANDBOX_CONTAINER_NAME", "pro-agent-sandbox")
        self.container = None

    def start(self):
        """Starts or attaches to the persistent container."""
        try:
            # 1. Try to find existing container
            try:
                # First try exact match
                try:
                    self.container = self.client.containers.get(self.container_name)
                except docker.errors.NotFound:
                    # Try finding by image name if exact name (likely compose generated) not found
                    candidates = self.client.containers.list(filters={"ancestor": self.image})
                    if candidates:
                        self.container = candidates[0]
                        print(f"Found sandbox by image: {self.container.name}")
                    else:
                        # Try common compose variations
                        variants = [f"{self.container_name}-1", f"pro-{self.container_name}-1"]
                        for v in variants:
                            try:
                                self.container = self.client.containers.get(v)
                                print(f"Found sandbox by variant: {v}")
                                break
                            except docker.errors.NotFound:
                                continue
                        
                        if not self.container:
                            raise docker.errors.NotFound("No sandbox found")

                print(f"Attached to existing sandbox: {self.container.name} ({self.container.id[:10]})")
                if self.container.status != 'running':
                    print("Container not running, starting it...")
                    self.container.start()
                return
            except docker.errors.NotFound:
                print(f"Container {self.container_name} not found. Creating new one... (Warning: Volume mounts may fail in DinD)")

            # 2. Fallback to creation (Legacy/Local mode)
            self.container = self.client.containers.run(
                self.image, 
                detach=True, 
                tty=True,
                name=self.container_name, 
                # Be careful with volumes in DinD. 
                # Ideally we rely on docker-compose to have set this up.
                volumes={os.getcwd(): {'bind': '/workspace', 'mode': 'rw'}}
            )
            print(f"Sandbox started: {self.container.id[:10]}")
        except DockerException as e:
            print(f"Failed to start sandbox: {e}")
            raise

    def execute_command(self, info: str, workdir: str = "/workspace"):
        """Execute a command in the sandbox."""
        if not self.container:
            raise RuntimeError("Sandbox container not active! Cannot execute command.")
        exit_code, output = self.container.exec_run(info, workdir=workdir)
        return output.decode("utf-8")

    def checkout_commit(self, commit_hash: str, workdir: str = "/workspace"):
        """Time Travel: Revert repo to a specific commit state."""
        print(f"⌛ Sandbox Time Travel: Checking out {commit_hash[:7]} in {workdir}...")
        result = self.execute_command(f"git checkout {commit_hash}", workdir=workdir)
        if "error" in result.lower() or "fatal" in result.lower():
            print(f"Warning: Checkout failed: {result}")
        return result
        
    def reset_to_main(self, workdir: str = "/workspace"):
        """Return to the main branch."""
        print(f"⌛ Sandbox Time Travel: Returning to main in {workdir}...")
        self.execute_command("git checkout main", workdir=workdir)

    def stop(self):
        """Clean up the container."""
        if self.container:
            # Only remove if it's NOT the persistent one managed by compose
            if self.container_name != "pro-agent-sandbox":
                print(f"Stopping temporary sandbox: {self.container_name}")
                self.container.stop()
                self.container.remove()
            else:
                print(f"Keeping persistent sandbox: {self.container_name}")
            self.container = None
