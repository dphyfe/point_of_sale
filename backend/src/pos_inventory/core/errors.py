"""Domain-level error types mapped to HTTP responses by main.py."""

from __future__ import annotations


class DomainError(Exception):
    code: str = "domain_error"
    http_status: int = 400


class RoleForbidden(DomainError):
    code = "role_forbidden"
    http_status = 403


class IdempotencyConflict(DomainError):
    code = "already_processed"
    http_status = 409


class BusinessRuleConflict(DomainError):
    code = "business_rule_conflict"
    http_status = 409


class NotFound(DomainError):
    code = "not_found"
    http_status = 404


class ValidationFailed(DomainError):
    code = "validation_failed"
    http_status = 400
