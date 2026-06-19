"""Prefixed short unique ids, e.g. sess_3fa2c19be0."""
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
