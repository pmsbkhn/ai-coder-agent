"""Provider-agnostic LLM layer.

The agent core depends only on PlannerPort/CoderPort. Behind them sits an
LLMClient with two interchangeable implementations — Anthropic (default) and any
OpenAI-compatible endpoint (Ollama / vLLM / local). Swapping models is an env-var
change, never a core change.

The robustness against weaker open-source models lives in `structured.py`:
schema-validated output with a repair-retry loop, so a model that drifts on
format gets corrected instead of poisoning the pipeline.
"""
