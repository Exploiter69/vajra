from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time


@dataclass(frozen=True)
class WorkerProof:
    worker_id: str
    attempt_id: str
    nonce: str
    issued_at: int
    expires_at: int
    signature: str


class WorkerAuthenticator:
    """Dependency-free HMAC worker authentication bound to an attempt."""

    def __init__(self, secret: bytes, *, clock=time.time) -> None:
        if len(secret) < 32:
            raise ValueError("worker authentication secret must be at least 32 bytes")
        self._secret = bytes(secret)
        self._clock = clock

    def issue(self, worker_id: str, attempt_id: str, nonce: str, *, ttl_seconds: int = 300) -> WorkerProof:
        if not worker_id or not attempt_id or not nonce:
            raise ValueError("worker proof identity must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        issued = int(self._clock())
        expires = issued + ttl_seconds
        signature = self._sign(worker_id, attempt_id, nonce, issued, expires)
        return WorkerProof(worker_id, attempt_id, nonce, issued, expires, signature)

    def verify(self, proof: WorkerProof, *, expected_worker_id: str, expected_attempt_id: str, now: int | None = None) -> bool:
        current = int(self._clock()) if now is None else int(now)
        if proof.worker_id != expected_worker_id or proof.attempt_id != expected_attempt_id:
            return False
        if proof.issued_at > current or proof.expires_at < current:
            return False
        expected = self._sign(
            proof.worker_id, proof.attempt_id, proof.nonce,
            proof.issued_at, proof.expires_at,
        )
        return hmac.compare_digest(proof.signature, expected)

    def _sign(self, worker_id: str, attempt_id: str, nonce: str, issued_at: int, expires_at: int) -> str:
        message = f"{worker_id}\0{attempt_id}\0{nonce}\0{issued_at}\0{expires_at}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()
