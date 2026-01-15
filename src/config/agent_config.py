import os
from dotenv import load_dotenv

load_dotenv()

class AgentConfig:
    # Models
    BRAIN_MODEL = os.getenv("BRAIN_MODEL", "claude-3-5-sonnet-20240620")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4.1")
    CRITIC_MODEL = os.getenv("CRITIC_MODEL", "gpt-4o-mini")
    
    # Node-Specific Model Selection (Primary + Fallback)
    NODE_MODELS = {
        "orient": {
            "primary": os.getenv("ORIENT_MODEL", "gpt-5-nano"),
            "fallback": os.getenv("ORIENT_FALLBACK", "gpt-4o-mini")
        },
        "plan": {
            "primary": os.getenv("PLAN_MODEL", "o3-mini"),
            "fallback": os.getenv("PLAN_FALLBACK", "gpt-5-mini")
        },
        "code": {
            "primary": os.getenv("CODE_MODEL", "gpt-4.1-mini"),
            "fallback": os.getenv("CODE_FALLBACK", "gpt-5-mini")
        },
        "critic": {
            "primary": os.getenv("CRITIC_MODEL", "gpt-4o-mini"),
            "fallback": os.getenv("CRITIC_FALLBACK", "gpt-3.5-turbo")
        }
    }
    
    # Thresholds
    SAFETY_THRESHOLD = int(os.getenv("SAFETY_THRESHOLD", "90"))
    COMPLIANCE_THRESHOLD = int(os.getenv("COMPLIANCE_THRESHOLD", "80"))
    FOR_THRESHOLD = int(os.getenv("FOR_THRESHOLD", "95"))
    
    # Infrastructure
    SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "agent-sandbox:latest")
    SANDBOX_CONTAINER_NAME = os.getenv("SANDBOX_CONTAINER_NAME", "pro-agent-sandbox")
    REPO_DIR = os.getenv("REPO_DIR", "/app/repos")
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    
    # Pricing (per 1M tokens) - Input/Output (Standard tier)
    # Can be overridden by AGENT_PRICING env var (JSON string)
    _DEFAULT_PRICING = {
        # Anthropic Claude Models (Base Input/Output)
        # Opus Series
        "claude-opus-4.5": (5.00, 25.00),
        "claude-opus-4.1": (15.00, 75.00),
        "claude-opus-4": (15.00, 75.00),
        "claude-opus-3": (15.00, 75.00),  # Deprecated
        "claude-3-opus-20240229": (15.00, 75.00),  # Legacy name
        
        # Sonnet Series
        "claude-sonnet-4.5": (3.00, 15.00),
        "claude-sonnet-4": (3.00, 15.00),
        "claude-sonnet-3.7": (3.00, 15.00),  # Deprecated
        "claude-sonnet-3.5": (3.00, 15.00),
        "claude-3-5-sonnet-20240620": (3.00, 15.00),  # Legacy name
        
        # Haiku Series
        "claude-haiku-4.5": (1.00, 5.00),
        "claude-haiku-3.5": (0.80, 4.00),
        "claude-haiku-3": (0.25, 1.25),
        "claude-3-5-haiku-20241022": (1.00, 5.00),  # Legacy name
        
        # OpenAI GPT-5 Series (Standard)
        "gpt-5.2": (1.75, 14.00),
        "gpt-5.1": (1.25, 10.00),
        "gpt-5": (1.25, 10.00),
        "gpt-5-mini": (0.25, 2.00),
        "gpt-5-nano": (0.05, 0.40),
        "gpt-5.2-chat-latest": (1.75, 14.00),
        "gpt-5.1-chat-latest": (1.25, 10.00),
        "gpt-5-chat-latest": (1.25, 10.00),
        "gpt-5.2-codex": (1.75, 14.00),
        "gpt-5.1-codex-max": (1.25, 10.00),
        "gpt-5.1-codex": (1.25, 10.00),
        "gpt-5-codex": (1.25, 10.00),
        "gpt-5.2-pro": (21.00, 168.00),
        "gpt-5-pro": (15.00, 120.00),
        
        # OpenAI GPT-4.1 Series (Standard)
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        
        # OpenAI GPT-4o Series (Standard)
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-2024-05-13": (5.00, 15.00),
        "gpt-4o-mini": (0.15, 0.60),
        
        # OpenAI o-series Reasoning Models (Standard)
        "o1": (15.00, 60.00),
        "o1-pro": (150.00, 600.00),
        "o1-mini": (1.10, 4.40),
        "o3": (2.00, 8.00),
        "o3-pro": (20.00, 80.00),
        "o3-mini": (1.10, 4.40),
        "o3-deep-research": (10.00, 40.00),
        "o4-mini": (1.10, 4.40),
        "o4-mini-deep-research": (2.00, 8.00),
        
        # Special Models
        "computer-use-preview": (3.00, 12.00),
        "gpt-realtime": (4.00, 16.00),
        "gpt-realtime-mini": (0.60, 2.40),
        
        # Legacy Models (Standard)
        "chatgpt-4o-latest": (5.00, 15.00),
        "gpt-4-turbo-2024-04-09": (10.00, 30.00),
        "gpt-4-0125-preview": (10.00, 30.00),
        "gpt-4-1106-preview": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "gpt-3.5-turbo-0125": (0.50, 1.50),
    }

    @staticmethod
    def get_pricing():
        import json
        env_pricing = os.getenv("AGENT_PRICING")
        if env_pricing:
            try:
                return {**AgentConfig._DEFAULT_PRICING, **json.loads(env_pricing)}
            except json.JSONDecodeError:
                print("Warning: Invalid JSON in AGENT_PRICING, using defaults.")
                return AgentConfig._DEFAULT_PRICING
        return AgentConfig._DEFAULT_PRICING

    @staticmethod
    def get_price(model_name):
        pricing = AgentConfig.get_pricing()
        return pricing.get(model_name, (1.0, 1.0))
