"""Tests for Encrypted Credential Vault"""
import pytest
from src.security.vault import SecureVault


@pytest.fixture
def vault(tmp_path):
    v = SecureVault(vault_dir=str(tmp_path / "vault"))
    v.init()
    return v


class TestVaultInit:
    def test_init_creates_directory(self, tmp_path):
        vault_dir = str(tmp_path / "new_vault")
        v = SecureVault(vault_dir=vault_dir)
        v.init()
        assert v.initialized
        assert (tmp_path / "new_vault").exists()
        assert (tmp_path / "new_vault" / "vault.keys").exists()

    def test_not_initialized_raises(self, tmp_path):
        v = SecureVault(vault_dir=str(tmp_path / "vault"))
        with pytest.raises(RuntimeError, match="not initialized"):
            v.set("key", "value")


class TestVaultOperations:
    def test_set_get_roundtrip(self, vault):
        vault.set("API_KEY", "sk-test-12345")
        assert vault.get("API_KEY") == "sk-test-12345"

    def test_nonexistent_key_returns_none(self, vault):
        assert vault.get("DOES_NOT_EXIST") is None

    def test_list_keys(self, vault):
        vault.set("KEY_A", "value_a")
        vault.set("KEY_B", "value_b")
        keys = vault.list_keys()
        assert "KEY_A" in keys
        assert "KEY_B" in keys
        assert len(keys) == 2

    def test_delete(self, vault):
        vault.set("TO_DELETE", "value")
        assert vault.delete("TO_DELETE")
        assert vault.get("TO_DELETE") is None
        assert "TO_DELETE" not in vault.list_keys()

    def test_delete_nonexistent(self, vault):
        assert not vault.delete("NOPE")

    def test_overwrite(self, vault):
        vault.set("KEY", "old")
        vault.set("KEY", "new")
        assert vault.get("KEY") == "new"
        assert len(vault.list_keys()) == 1

    def test_multiple_values(self, vault):
        vault.set("A", "1")
        vault.set("B", "2")
        vault.set("C", "3")
        assert vault.get("A") == "1"
        assert vault.get("B") == "2"
        assert vault.get("C") == "3"


class TestVaultPersistence:
    def test_persistence_across_load_save(self, tmp_path):
        vault_dir = str(tmp_path / "vault")

        # Create and populate
        v1 = SecureVault(vault_dir=vault_dir)
        v1.init()
        v1.set("PERSIST_KEY", "persist_value")

        # Load in new instance
        v2 = SecureVault(vault_dir=vault_dir)
        v2.init()
        assert v2.get("PERSIST_KEY") == "persist_value"


class TestKeyRotation:
    def test_rotation_preserves_values(self, vault):
        vault.set("KEY_1", "value_1")
        vault.set("KEY_2", "value_2")

        vault.rotate_keys()

        assert vault.get("KEY_1") == "value_1"
        assert vault.get("KEY_2") == "value_2"

    def test_rotation_changes_key_id(self, vault):
        vault.set("KEY", "value")
        old_key_id = vault._kem_keypair.key_id
        vault.rotate_keys()
        assert vault._kem_keypair.key_id != old_key_id


class TestVaultForSettings:
    def test_get_for_settings(self, vault):
        vault.set("API_KEY", "sk-123")
        vault.set("SECRET", "s3cret")
        settings = vault.get_for_settings()
        assert settings == {"API_KEY": "sk-123", "SECRET": "s3cret"}
