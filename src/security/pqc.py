"""
Post-Quantum Cryptography Engine

Provides hybrid PQC encryption (ML-KEM-768 / Kyber) and signing (ML-DSA-65 / Dilithium).
Falls back to X25519 + Ed25519 + AES-256-GCM when liboqs-python is not installed.
"""
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass(frozen=True)
class PQCKeyPair:
    """Immutable key pair container"""
    algorithm: str
    public_key: bytes
    secret_key: bytes
    key_id: str
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class EncryptedPayload:
    """Immutable encrypted payload container"""
    kem_ciphertext: bytes
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    algorithm: str
    key_id: str

    def to_dict(self) -> dict:
        import base64
        return {
            "kem_ciphertext": base64.b64encode(self.kem_ciphertext).decode(),
            "nonce": base64.b64encode(self.nonce).decode(),
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "tag": base64.b64encode(self.tag).decode(),
            "algorithm": self.algorithm,
            "key_id": self.key_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncryptedPayload":
        import base64
        return cls(
            kem_ciphertext=base64.b64decode(data["kem_ciphertext"]),
            nonce=base64.b64decode(data["nonce"]),
            ciphertext=base64.b64decode(data["ciphertext"]),
            tag=base64.b64decode(data["tag"]),
            algorithm=data["algorithm"],
            key_id=data["key_id"],
        )


@dataclass(frozen=True)
class Signature:
    """Immutable signature container"""
    signature: bytes
    algorithm: str
    key_id: str
    signed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        import base64
        return {
            "signature": base64.b64encode(self.signature).decode(),
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Signature":
        import base64
        return cls(
            signature=base64.b64decode(data["signature"]),
            algorithm=data["algorithm"],
            key_id=data["key_id"],
            signed_at=data["signed_at"],
        )


def _key_id_from_public(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()[:16]


class PQCEngine:
    """
    Post-Quantum Cryptography engine.

    Uses ML-KEM-768 (Kyber) for key encapsulation and ML-DSA-65 (Dilithium) for signing.
    Falls back to X25519 + Ed25519 + AES-256-GCM when liboqs is not available.
    """

    def __init__(self):
        self._use_pqc = False
        try:
            import oqs  # noqa: F401
            self._use_pqc = True
            logger.info("PQC: liboqs available, using ML-KEM-768 / ML-DSA-65")
        except ImportError:
            logger.warning("PQC: liboqs not available, falling back to X25519 + Ed25519")

    @property
    def is_pqc(self) -> bool:
        return self._use_pqc

    # ---- Key Generation ----

    def generate_kem_keypair(self) -> PQCKeyPair:
        if self._use_pqc:
            return self._pqc_kem_keygen()
        return self._classical_kem_keygen()

    def generate_signing_keypair(self) -> PQCKeyPair:
        if self._use_pqc:
            return self._pqc_signing_keygen()
        return self._classical_signing_keygen()

    # ---- Encrypt / Decrypt ----

    def encrypt(self, plaintext: bytes, public_key: PQCKeyPair) -> EncryptedPayload:
        if self._use_pqc:
            return self._pqc_encrypt(plaintext, public_key)
        return self._classical_encrypt(plaintext, public_key)

    def decrypt(self, payload: EncryptedPayload, secret_key: PQCKeyPair) -> bytes:
        if self._use_pqc:
            return self._pqc_decrypt(payload, secret_key)
        return self._classical_decrypt(payload, secret_key)

    # ---- Sign / Verify ----

    def sign(self, data: bytes, signing_keypair: PQCKeyPair) -> Signature:
        if self._use_pqc:
            return self._pqc_sign(data, signing_keypair)
        return self._classical_sign(data, signing_keypair)

    def verify(self, data: bytes, signature: Signature, public_key: PQCKeyPair) -> bool:
        if self._use_pqc:
            return self._pqc_verify(data, signature, public_key)
        return self._classical_verify(data, signature, public_key)

    # ========== PQC Implementation (liboqs) ==========

    def _pqc_kem_keygen(self) -> PQCKeyPair:
        import oqs
        kem = oqs.KeyEncapsulation("Kyber768")
        public_key = kem.generate_keypair()
        secret_key = kem.export_secret_key()
        return PQCKeyPair(
            algorithm="ML-KEM-768",
            public_key=public_key,
            secret_key=secret_key,
            key_id=_key_id_from_public(public_key),
        )

    def _pqc_signing_keygen(self) -> PQCKeyPair:
        import oqs
        sig = oqs.Signature("Dilithium3")
        public_key = sig.generate_keypair()
        secret_key = sig.export_secret_key()
        return PQCKeyPair(
            algorithm="ML-DSA-65",
            public_key=public_key,
            secret_key=secret_key,
            key_id=_key_id_from_public(public_key),
        )

    def _pqc_encrypt(self, plaintext: bytes, public_key: PQCKeyPair) -> EncryptedPayload:
        import oqs
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        kem = oqs.KeyEncapsulation("Kyber768")
        ciphertext_kem, shared_secret = kem.encap_secret(public_key.public_key)

        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ccp-pqc-kem",
        ).derive(shared_secret)

        nonce = os.urandom(12)
        aesgcm = AESGCM(derived_key)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        # AES-GCM appends 16-byte tag
        ciphertext_data = ct[:-16]
        tag = ct[-16:]

        return EncryptedPayload(
            kem_ciphertext=ciphertext_kem,
            nonce=nonce,
            ciphertext=ciphertext_data,
            tag=tag,
            algorithm="ML-KEM-768+AES-256-GCM",
            key_id=public_key.key_id,
        )

    def _pqc_decrypt(self, payload: EncryptedPayload, secret_key: PQCKeyPair) -> bytes:
        import oqs
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        kem = oqs.KeyEncapsulation("Kyber768", secret_key=secret_key.secret_key)
        shared_secret = kem.decap_secret(payload.kem_ciphertext)

        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ccp-pqc-kem",
        ).derive(shared_secret)

        aesgcm = AESGCM(derived_key)
        ct_with_tag = payload.ciphertext + payload.tag
        return aesgcm.decrypt(payload.nonce, ct_with_tag, None)

    def _pqc_sign(self, data: bytes, signing_keypair: PQCKeyPair) -> Signature:
        import oqs
        sig = oqs.Signature("Dilithium3", secret_key=signing_keypair.secret_key)
        signature_bytes = sig.sign(data)
        return Signature(
            signature=signature_bytes,
            algorithm="ML-DSA-65",
            key_id=signing_keypair.key_id,
        )

    def _pqc_verify(self, data: bytes, signature: Signature, public_key: PQCKeyPair) -> bool:
        import oqs
        sig = oqs.Signature("Dilithium3")
        return sig.verify(data, signature.signature, public_key.public_key)

    # ========== Classical Fallback (X25519 + Ed25519) ==========

    def _classical_kem_keygen(self) -> PQCKeyPair:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        private_key = X25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes_raw()
        secret_key_bytes = private_key.private_bytes_raw()

        return PQCKeyPair(
            algorithm="X25519",
            public_key=public_key_bytes,
            secret_key=secret_key_bytes,
            key_id=_key_id_from_public(public_key_bytes),
        )

    def _classical_signing_keygen(self) -> PQCKeyPair:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.generate()
        public_key_bytes = private_key.public_key().public_bytes_raw()
        secret_key_bytes = private_key.private_bytes_raw()

        return PQCKeyPair(
            algorithm="Ed25519",
            public_key=public_key_bytes,
            secret_key=secret_key_bytes,
            key_id=_key_id_from_public(public_key_bytes),
        )

    def _classical_encrypt(self, plaintext: bytes, public_key: PQCKeyPair) -> EncryptedPayload:
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey, X25519PublicKey,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        # Ephemeral key exchange
        ephemeral_private = X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key().public_bytes_raw()
        peer_public = X25519PublicKey.from_public_bytes(public_key.public_key)
        shared_secret = ephemeral_private.exchange(peer_public)

        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ccp-x25519-kem",
        ).derive(shared_secret)

        nonce = os.urandom(12)
        aesgcm = AESGCM(derived_key)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        ciphertext_data = ct[:-16]
        tag = ct[-16:]

        return EncryptedPayload(
            kem_ciphertext=ephemeral_public,
            nonce=nonce,
            ciphertext=ciphertext_data,
            tag=tag,
            algorithm="X25519+AES-256-GCM",
            key_id=public_key.key_id,
        )

    def _classical_decrypt(self, payload: EncryptedPayload, secret_key: PQCKeyPair) -> bytes:
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey, X25519PublicKey,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        private = X25519PrivateKey.from_private_bytes(secret_key.secret_key)
        ephemeral_public = X25519PublicKey.from_public_bytes(payload.kem_ciphertext)
        shared_secret = private.exchange(ephemeral_public)

        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ccp-x25519-kem",
        ).derive(shared_secret)

        aesgcm = AESGCM(derived_key)
        ct_with_tag = payload.ciphertext + payload.tag
        return aesgcm.decrypt(payload.nonce, ct_with_tag, None)

    def _classical_sign(self, data: bytes, signing_keypair: PQCKeyPair) -> Signature:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        private_key = Ed25519PrivateKey.from_private_bytes(signing_keypair.secret_key)
        signature_bytes = private_key.sign(data)
        return Signature(
            signature=signature_bytes,
            algorithm="Ed25519",
            key_id=signing_keypair.key_id,
        )

    def _classical_verify(self, data: bytes, signature: Signature, public_key: PQCKeyPair) -> bool:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub = Ed25519PublicKey.from_public_bytes(public_key.public_key)
        try:
            pub.verify(signature.signature, data)
            return True
        except Exception:
            return False
