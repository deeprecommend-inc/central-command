"""
Encrypted Credential Vault

PQC-encrypted key-value store for secrets.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from .pqc import PQCEngine, PQCKeyPair, EncryptedPayload


@dataclass
class VaultEntry:
    """Single vault entry"""
    key: str
    encrypted_value: EncryptedPayload
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class SecureVault:
    """
    PQC-encrypted credential vault.

    Stores secrets encrypted with hybrid KEM + AES-256-GCM.
    """

    def __init__(self, vault_dir: str = ".ccp_vault"):
        self._vault_dir = vault_dir
        self._engine = PQCEngine()
        self._kem_keypair: Optional[PQCKeyPair] = None
        self._entries: dict[str, VaultEntry] = {}
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def init(self) -> None:
        """Initialize vault: create directory, generate keys"""
        os.makedirs(self._vault_dir, exist_ok=True)

        keys_path = os.path.join(self._vault_dir, "vault.keys")
        if os.path.exists(keys_path):
            self._load_keys(keys_path)
            logger.info("Vault: loaded existing keys")
        else:
            self._kem_keypair = self._engine.generate_kem_keypair()
            self._save_keys(keys_path)
            logger.info("Vault: generated new keypair")

        # Load existing entries
        vault_path = os.path.join(self._vault_dir, "vault.enc")
        if os.path.exists(vault_path):
            self.load()

        self._initialized = True

    def set(self, key: str, value: str) -> None:
        """Encrypt and store a value"""
        self._ensure_initialized()
        encrypted = self._engine.encrypt(value.encode(), self._kem_keypair)
        now = time.time()
        if key in self._entries:
            self._entries[key].encrypted_value = encrypted
            self._entries[key].updated_at = now
        else:
            self._entries[key] = VaultEntry(
                key=key,
                encrypted_value=encrypted,
                created_at=now,
                updated_at=now,
            )
        self.save()

    def get(self, key: str) -> Optional[str]:
        """Decrypt and return a value"""
        self._ensure_initialized()
        entry = self._entries.get(key)
        if entry is None:
            return None
        plaintext = self._engine.decrypt(entry.encrypted_value, self._kem_keypair)
        return plaintext.decode()

    def delete(self, key: str) -> bool:
        """Delete a key"""
        self._ensure_initialized()
        if key in self._entries:
            del self._entries[key]
            self.save()
            return True
        return False

    def list_keys(self) -> list[str]:
        """List all stored keys"""
        self._ensure_initialized()
        return list(self._entries.keys())

    def rotate_keys(self) -> None:
        """Generate new keypair and re-encrypt all entries"""
        self._ensure_initialized()

        # Decrypt all values with old key
        decrypted = {}
        for key, entry in self._entries.items():
            plaintext = self._engine.decrypt(entry.encrypted_value, self._kem_keypair)
            decrypted[key] = plaintext

        # Generate new keypair
        self._kem_keypair = self._engine.generate_kem_keypair()

        # Re-encrypt with new key
        now = time.time()
        for key, plaintext in decrypted.items():
            encrypted = self._engine.encrypt(plaintext, self._kem_keypair)
            self._entries[key].encrypted_value = encrypted
            self._entries[key].updated_at = now

        # Save new keys and vault
        keys_path = os.path.join(self._vault_dir, "vault.keys")
        self._save_keys(keys_path)
        self.save()
        logger.info("Vault: key rotation complete")

    def save(self) -> None:
        """Persist vault to disk"""
        self._ensure_initialized()
        vault_path = os.path.join(self._vault_dir, "vault.enc")
        data = {}
        for key, entry in self._entries.items():
            data[key] = {
                "encrypted_value": entry.encrypted_value.to_dict(),
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }
        with open(vault_path, "w") as f:
            json.dump(data, f)

    def load(self) -> None:
        """Load vault from disk"""
        vault_path = os.path.join(self._vault_dir, "vault.enc")
        if not os.path.exists(vault_path):
            return
        with open(vault_path, "r") as f:
            data = json.load(f)
        for key, entry_data in data.items():
            self._entries[key] = VaultEntry(
                key=key,
                encrypted_value=EncryptedPayload.from_dict(entry_data["encrypted_value"]),
                created_at=entry_data["created_at"],
                updated_at=entry_data["updated_at"],
            )

    def get_for_settings(self) -> dict[str, str]:
        """Return all decrypted values as a dict for Settings integration"""
        self._ensure_initialized()
        result = {}
        for key in self._entries:
            val = self.get(key)
            if val is not None:
                result[key] = val
        return result

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Vault not initialized. Call init() first.")

    def _save_keys(self, path: str) -> None:
        import base64
        data = {
            "algorithm": self._kem_keypair.algorithm,
            "public_key": base64.b64encode(self._kem_keypair.public_key).decode(),
            "secret_key": base64.b64encode(self._kem_keypair.secret_key).decode(),
            "key_id": self._kem_keypair.key_id,
            "created_at": self._kem_keypair.created_at,
        }
        with open(path, "w") as f:
            json.dump(data, f)
        os.chmod(path, 0o600)

    def _load_keys(self, path: str) -> None:
        import base64
        with open(path, "r") as f:
            data = json.load(f)
        self._kem_keypair = PQCKeyPair(
            algorithm=data["algorithm"],
            public_key=base64.b64decode(data["public_key"]),
            secret_key=base64.b64decode(data["secret_key"]),
            key_id=data["key_id"],
            created_at=data["created_at"],
        )
