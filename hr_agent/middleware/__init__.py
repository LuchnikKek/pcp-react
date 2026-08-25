"""Middleware агента (ARCHITECTURE.md §2.6)."""

from hr_agent.middleware.authz import AuthzMiddleware
from hr_agent.middleware.dynamic_prompt import DynamicPromptMiddleware
from hr_agent.middleware.progress import ProgressMiddleware

__all__ = ["AuthzMiddleware", "DynamicPromptMiddleware", "ProgressMiddleware"]
