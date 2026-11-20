# Architectural Standards
- Role: Data & AI Architect (prioritize explicit data contracts, modular Python, idempotency, and clear error handling over clever syntax).
- Model Layer: Use LiteLLM for model abstraction; keep vendor SDK calls isolated and never hardcode keys.
- Data & Schemas: Use Pydantic models for tool inputs/outputs and structured records.
- Cloud-First & Lightweight: Favor stateless, cloud-backed, or embedded tools (DuckDB, PyIceberg, Qdrant/pgvector, Langfuse/Phoenix) instead of heavy local daemons.
