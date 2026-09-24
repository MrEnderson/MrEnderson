"""v0.2.5.1 pure authority contracts + algebra
(`docs/V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md`).

Representation of authority is not possession of authority. Nothing in this
package grants, persists, delegates, approves, executes, recovers, combines,
infers or manufactures authority, and nothing here is wired into the action
pipeline. Delegation records, stores, evaluation and integration are later,
separately authorized v0.2.5.x stages.
"""
from app.authority_contracts.algebra import NO_AUTHORITY, leq, meet
from app.authority_contracts.contracts import (
    ACTION_TYPE_VOCABULARY,
    ACTION_VOCABULARY_VERSION,
    AUTHORITY_SCOPE_SCHEMA_VERSION,
    AuthorityScope,
    ObjectiveRef,
    PrincipalKind,
    PrincipalRef,
    PTier,
)

__all__ = [
    "ACTION_TYPE_VOCABULARY",
    "ACTION_VOCABULARY_VERSION",
    "AUTHORITY_SCOPE_SCHEMA_VERSION",
    "AuthorityScope",
    "NO_AUTHORITY",
    "ObjectiveRef",
    "PTier",
    "PrincipalKind",
    "PrincipalRef",
    "leq",
    "meet",
]
