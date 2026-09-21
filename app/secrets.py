"""Secret-provider boundary.

Containerized deployments prefer secret files under /run/secrets. Environment
fallback is demo/test-only. Demo/test secrets that are required but not supplied
are generated randomly per process so no universal credential is shipped in
source code.
"""
from __future__ import annotations
import json
import os
import secrets as pysecrets
from pathlib import Path
from .config import settings


class SecretProvider:
    def __init__(self):
        self._ephemeral: dict[str, str] = {}

    def _file_candidates(self, name: str) -> list[Path]:
        explicit = os.getenv(f"{name}_FILE", "")
        candidates = []
        if explicit:
            candidates.append(Path(explicit))
        candidates.append(Path("/run/secrets") / name.lower())
        return candidates

    def get(self, name: str, default: str | None = None) -> str:
        for path in self._file_candidates(name):
            try:
                if path.is_file():
                    value = path.read_text().strip()
                    if value:
                        return value
            except OSError:
                pass

        secret_id = os.getenv(f"{name}_AWS_SECRET_ID", "")
        if secret_id:
            import boto3
            value = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
            raw = value.get("SecretString", "")
            try:
                obj = json.loads(raw)
                return str(obj.get(name, raw))
            except Exception:
                return raw

        if settings.environment in {"demo", "test"}:
            env_value = os.getenv(name)
            if env_value:
                return env_value
            if default is not None:
                return default
            if name not in self._ephemeral:
                self._ephemeral[name] = pysecrets.token_urlsafe(48)
            return self._ephemeral[name]

        raise RuntimeError(f"Required secret {name} is not available through a secret file/provider")


secrets = SecretProvider()
