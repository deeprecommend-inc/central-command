"""Tests for Signed Audit Logger"""
import os
import time
import pytest
from src.security.pqc import PQCEngine
from src.security.audit import AuditLogger, AuditEntry


@pytest.fixture
def engine():
    return PQCEngine()


@pytest.fixture
def signing_keypair(engine):
    return engine.generate_signing_keypair()


@pytest.fixture
def signed_logger(engine, signing_keypair):
    return AuditLogger(pqc_engine=engine, signing_keypair=signing_keypair)


@pytest.fixture
def unsigned_logger():
    return AuditLogger()


class TestLogLLMCall:
    def test_creates_signed_entry(self, signed_logger):
        entry = signed_logger.log_llm_call(
            session_id="s1",
            prompt_hash="abc123",
            response_hash="def456",
            action="proceed",
            confidence=0.9,
            tokens_used=150,
        )
        assert entry.entry_id
        assert entry.event_type == "llm_call"
        assert entry.input_hash == "abc123"
        assert entry.output_hash == "def456"
        assert entry.signature is not None
        assert entry.metadata["action"] == "proceed"
        assert entry.metadata["tokens_used"] == 150

    def test_unsigned_mode(self, unsigned_logger):
        entry = unsigned_logger.log_llm_call(
            session_id="s1",
            prompt_hash="a",
            response_hash="b",
            action="proceed",
            confidence=0.8,
            tokens_used=100,
        )
        assert entry.signature is None
        assert entry.event_type == "llm_call"


class TestVerification:
    def test_verify_valid_entry(self, signed_logger):
        entry = signed_logger.log_event("test", "in", "out")
        assert signed_logger.verify_entry(entry)

    def test_tampered_entry_fails(self, signed_logger):
        entry = signed_logger.log_event("test", "in", "out")
        # Tamper with the entry
        tampered = AuditEntry(
            entry_id=entry.entry_id,
            timestamp=entry.timestamp,
            event_type=entry.event_type,
            input_hash="TAMPERED",
            output_hash=entry.output_hash,
            metadata=entry.metadata,
            signature=entry.signature,
        )
        assert not signed_logger.verify_entry(tampered)

    def test_verify_all_counts(self, signed_logger):
        signed_logger.log_event("a", "1", "2")
        signed_logger.log_event("b", "3", "4")
        signed_logger.log_event("c", "5", "6")
        valid, invalid = signed_logger.verify_all()
        assert valid == 3
        assert invalid == 0

    def test_unsigned_entry_passes(self, unsigned_logger):
        entry = unsigned_logger.log_event("test", "in", "out")
        assert unsigned_logger.verify_entry(entry)


class TestLogDecision:
    def test_log_decision(self, signed_logger):
        class MockDecision:
            def to_dict(self):
                return {"action": "proceed", "confidence": 0.9}

        entry = signed_logger.log_decision(
            decision=MockDecision(),
            state_hash="state123",
            session_id="s1",
        )
        assert entry.event_type == "decision"
        assert entry.input_hash == "state123"
        assert entry.metadata["session_id"] == "s1"


class TestQuerying:
    def test_query_by_event_type(self, signed_logger):
        signed_logger.log_event("llm_call", "a", "b")
        signed_logger.log_event("decision", "c", "d")
        signed_logger.log_event("llm_call", "e", "f")

        results = signed_logger.get_entries(event_type="llm_call")
        assert len(results) == 2

    def test_query_by_timestamp(self, signed_logger):
        before = time.time()
        signed_logger.log_event("a", "1", "2")
        after = time.time()
        signed_logger.log_event("b", "3", "4")

        results = signed_logger.get_entries(until=after)
        assert len(results) >= 1
        assert all(e.timestamp <= after for e in results)


class TestFilePersistence:
    def test_file_persistence(self, tmp_path, engine, signing_keypair):
        log_file = str(tmp_path / "audit.jsonl")

        # Write entries
        logger1 = AuditLogger(
            pqc_engine=engine, signing_keypair=signing_keypair, log_file=log_file,
        )
        logger1.log_event("test1", "a", "b")
        logger1.log_event("test2", "c", "d")

        # Load in new instance
        logger2 = AuditLogger(
            pqc_engine=engine, signing_keypair=signing_keypair, log_file=log_file,
        )
        assert len(logger2.entries) == 2
        assert logger2.entries[0].event_type == "test1"
        assert logger2.entries[1].event_type == "test2"
