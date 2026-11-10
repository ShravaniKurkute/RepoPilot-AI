"""Sandboxed execution engine for untrusted code execution.

Provides:
- Docker container lifecycle management via docker-py
- Resource quotas (CPU limits, memory limits, execution timeout)
- Offline network isolation (--network=none)
- Non-root user execution
"""

