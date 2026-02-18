"""Tests for Post-Quantum Cryptography engine"""
import pytest
from src.security.pqc import PQCEngine, PQCKeyPair, EncryptedPayload, Signature


@pytest.fixture
def engine():
    return PQCEngine()


@pytest.fixture
def kem_keypair(engine):
    return engine.generate_kem_keypair()


@pytest.fixture
def signing_keypair(engine):
    return engine.generate_signing_keypair()


class TestKeyGeneration:
    def test_kem_keypair_generated(self, engine):
        kp = engine.generate_kem_keypair()
        assert kp.public_key
        assert kp.secret_key
        assert kp.key_id
        assert kp.algorithm in ("ML-KEM-768", "X25519")

    def test_signing_keypair_generated(self, engine):
        kp = engine.generate_signing_keypair()
        assert kp.public_key
        assert kp.secret_key
        assert kp.key_id
        assert kp.algorithm in ("ML-DSA-65", "Ed25519")

    def test_different_keypairs(self, engine):
        kp1 = engine.generate_kem_keypair()
        kp2 = engine.generate_kem_keypair()
        assert kp1.key_id != kp2.key_id


class TestEncryptDecrypt:
    def test_roundtrip(self, engine, kem_keypair):
        plaintext = b"secret data for CCP"
        encrypted = engine.encrypt(plaintext, kem_keypair)
        decrypted = engine.decrypt(encrypted, kem_keypair)
        assert decrypted == plaintext

    def test_different_ciphertexts(self, engine, kem_keypair):
        plaintext = b"same data"
        enc1 = engine.encrypt(plaintext, kem_keypair)
        enc2 = engine.encrypt(plaintext, kem_keypair)
        # Ephemeral key or KEM ciphertext should differ
        assert enc1.kem_ciphertext != enc2.kem_ciphertext or enc1.nonce != enc2.nonce

    def test_wrong_key_fails(self, engine):
        kp1 = engine.generate_kem_keypair()
        kp2 = engine.generate_kem_keypair()
        encrypted = engine.encrypt(b"test", kp1)
        with pytest.raises(Exception):
            engine.decrypt(encrypted, kp2)

    def test_empty_data(self, engine, kem_keypair):
        encrypted = engine.encrypt(b"", kem_keypair)
        decrypted = engine.decrypt(encrypted, kem_keypair)
        assert decrypted == b""

    def test_large_data(self, engine, kem_keypair):
        plaintext = os.urandom(100_000)
        encrypted = engine.encrypt(plaintext, kem_keypair)
        decrypted = engine.decrypt(encrypted, kem_keypair)
        assert decrypted == plaintext


class TestSignVerify:
    def test_sign_verify_valid(self, engine, signing_keypair):
        data = b"decision payload"
        sig = engine.sign(data, signing_keypair)
        assert engine.verify(data, sig, signing_keypair)

    def test_tampered_data_fails(self, engine, signing_keypair):
        data = b"original"
        sig = engine.sign(data, signing_keypair)
        assert not engine.verify(b"tampered", sig, signing_keypair)

    def test_wrong_key_fails(self, engine):
        kp1 = engine.generate_signing_keypair()
        kp2 = engine.generate_signing_keypair()
        sig = engine.sign(b"data", kp1)
        assert not engine.verify(b"data", sig, kp2)


class TestSerialization:
    def test_encrypted_payload_roundtrip(self, engine, kem_keypair):
        encrypted = engine.encrypt(b"test serialization", kem_keypair)
        d = encrypted.to_dict()
        restored = EncryptedPayload.from_dict(d)
        assert restored.algorithm == encrypted.algorithm
        assert restored.key_id == encrypted.key_id
        # Verify we can decrypt the restored payload
        decrypted = engine.decrypt(restored, kem_keypair)
        assert decrypted == b"test serialization"

    def test_signature_roundtrip(self, engine, signing_keypair):
        sig = engine.sign(b"test", signing_keypair)
        d = sig.to_dict()
        restored = Signature.from_dict(d)
        assert restored.algorithm == sig.algorithm
        assert restored.key_id == sig.key_id
        assert restored.signature == sig.signature


import os
