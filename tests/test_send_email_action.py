#!/usr/bin/env python3
"""
Test scenariusza wysyłania e-maili (akcja send_email) z atrapą SMTP.
"""

import asyncio
import contextlib
import os
import smtplib
from typing import Any, Dict, List

from avena_commons.orchestrator.actions import ActionContext, ActionExecutor
from avena_commons.util.logger import MessageLogger


class _DummySMTP:
    sent_messages: List[Dict[str, Any]] = []

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, username: str, password: str):
        self.username = username
        self.password = password

    def send_message(self, msg):
        _record = {
            "from": msg["From"],
            "to": msg["To"],
            "subject": msg["Subject"],
            "body": msg.get_content(),
        }
        _DummySMTP.sent_messages.append(_record)


@contextlib.contextmanager
def _patch_smtp(monkeypatch):  # type: ignore[override]
    """Kontekst zastępujący smtplib.SMTP i SMTP_SSL atrapą."""
    monkeypatch.setattr(smtplib, "SMTP", _DummySMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _DummySMTP)
    try:
        yield
    finally:
        _DummySMTP.sent_messages.clear()


async def _run_send_email_action(monkeypatch):  # type: ignore[override]
    logger = MessageLogger(filename=None, debug=True)
    executor = ActionExecutor()

    class MockOrchestrator:
        def __init__(self):
            # Pozwala sterować prawdziwym serwerem SMTP przez zmienne środowiskowe
            host = os.getenv("SMTP_HOST", "smtp.test")
            port = int(os.getenv("SMTP_PORT", "587"))
            starttls = os.getenv("STARTTLS", "1") == "1"
            tls = os.getenv("TLS", "0") == "1"
            username = os.getenv("SMTP_USERNAME", "user")
            password = os.getenv("SMTP_PASSWORD", "pass")
            mail_from = os.getenv("SMTP_FROM", "orchestrator@test")

            self._configuration = {
                "smtp": {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "starttls": starttls,
                    "tls": tls,
                    "from": mail_from,
                }
            }
            self._state = {
                "io": {"fsm_state": "RUN"},
                "supervisor_1": {"fsm_state": "FAULT"},
            }

    orch = MockOrchestrator()
    context = ActionContext(
        orchestrator=orch, message_logger=logger, scenario_name="test_email"
    )

    action_cfg = {
        "type": "send_email",
        "to": ["ops@test"],
        "subject": "[TEST] Fault in {{ trigger.source }}",
        "body": "List: {{ clients_in_fault }}",
    }

    use_real = os.getenv("USE_REAL_SMTP", "0") == "1"

    if not use_real:
        with _patch_smtp(monkeypatch):
            await executor.execute_action(action_cfg, context)
            assert len(_DummySMTP.sent_messages) == 1
            sent = _DummySMTP.sent_messages[0]
            assert sent["from"]
            assert "ops@test" in sent["to"]
            assert sent["subject"].startswith("[TEST]")
            # W treści powinna być lista klientów w błędzie
            assert "supervisor_1" in sent["body"]
    else:
        # W trybie realnym po prostu oczekujemy braku wyjątków podczas wysyłki
        await executor.execute_action(action_cfg, context)


def test_send_email_action(monkeypatch):  # type: ignore[override]
    asyncio.run(_run_send_email_action(monkeypatch))
