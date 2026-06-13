"""AI Coder Agent — Hexagonal MCP Orchestrator.

Layering (enforced by .importlinter + tests/test_arch_fitness.py):

    domain        pure Python: models, the AgentSession state machine, errors.
    application   use-cases + ports (Protocol). Talks to the world ONLY via ports.
    adapters      concrete implementations (LLM, MCP gateway, Postgres memory).

Nothing project-specific (MSFW, Maven, surefire) lives in domain/application;
it lives in a Project Profile (profiles/*.yaml) and in adapters.
"""

__version__ = "0.0.1"
