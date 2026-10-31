"""Email alert (D-5.3): one email when an action's failed runs in a row reach `alerts.after_failures`.

Stateless on purpose: the email goes out exactly when the streak becomes equal to the threshold, so a
streak that keeps failing does not send again, a success resets it by ending the streak, and a worker
restart cannot send twice. A failed send is logged and never fails the run.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import Engine

from app.core.settings import get_settings
from app.secrets import SecretNotFound, check_host, get_secret
from app.storage import repo, session_scope

log = logging.getLogger("alerts")
DEFAULT_AFTER_FAILURES = 3
SECRET_NAME = "smtp_password"


def build_message(settings, integration: str, action: str, trigger: str, failures: int, error: dict | None, when: str,
                  to: list[str]) -> EmailMessage:
    error = error or {}
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = f"[Integration Platform] {integration} is failing ({failures} failed runs in a row)"
    msg.set_content(
        f'The integration "{integration}" has failed {failures} runs in a row.\n\n'
        f"Last error:  {error.get('code', 'unknown')}\n"
        f"Message:     {error.get('message', '')}\n"
        f"Last run:    {when} ({action}, {trigger})\n\n"
        "Nothing was lost. Records saved by earlier runs are unchanged.\n"
        f"This message is sent once. It is sent again only after a successful run and {failures} new failures.\n"
    )
    return msg


def send(settings, msg: EmailMessage, password: str | None) -> None:
    """Port 465 uses SSL, 587 uses STARTTLS, anything else is plain (D-5.3)."""
    port = settings.smtp_port or 587
    if port == 465:
        smtp = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=20, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(settings.smtp_host, port, timeout=20)
    with smtp:
        if port == 587:
            smtp.starttls(context=ssl.create_default_context())
        if password and settings.smtp_username:
            smtp.login(settings.smtp_username, password)
        smtp.send_message(msg)


def _note(engine: Engine, account: str, cfg: dict, action: str, outcome: str, failures: int, message: str | None = None) -> None:
    """Remember what came of this alert, so the dashboard can say whether the person was told. Never raises."""
    try:
        with session_scope(engine) as s:
            repo.record_alert_attempt(s, account, cfg["name"], action, outcome, failures, message)
    except Exception as exc:  # noqa: BLE001
        log.error("could not record the alert outcome for %s: %s", cfg.get("name"), type(exc).__name__)


def maybe_alert(engine: Engine, account: str, cfg: dict, action: str, trigger: str, result) -> bool:
    """Call after a run is finished. Returns True if an email was sent. Never raises."""
    streak, password = 0, None
    try:
        alerts = cfg.get("alerts")
        if not alerts or result.status != "failed" or trigger not in repo.COUNTED_TRIGGERS:
            return False
        threshold = alerts.get("after_failures", DEFAULT_AFTER_FAILURES)
        with session_scope(engine) as s:
            streak = repo.failure_streak(s, account, cfg["name"], action)
        if streak != threshold:
            return False
        settings = get_settings()
        if not (settings.smtp_host and settings.smtp_from):
            log.warning("alert for %s not sent: SMTP_HOST and SMTP_FROM are not set", cfg["name"])
            _note(engine, account, cfg, action, "not_configured", streak, "SMTP is not set up on the server (SMTP_HOST and SMTP_FROM)")
            return False
        try:
            with session_scope(engine) as s:
                secret = get_secret(SECRET_NAME, s, account)
            check_host(secret, settings.smtp_host)  # D-7.6: the password goes only to its own mail server
            password = secret.value
        except SecretNotFound:
            pass  # a relay without login
        msg = build_message(settings, cfg["name"], action, trigger, streak, result.error, result.finished_at or "", alerts["to"])
        send(settings, msg, password)
        log.info("alert sent for %s after %s failures", cfg["name"], streak)
        _note(engine, account, cfg, action, "sent", streak)
        return True
    except Exception as exc:  # noqa: BLE001 - a failed alert must never fail the run
        log.error("alert for %s could not be sent: %s", cfg.get("name"), type(exc).__name__)
        if streak:
            detail = f"{type(exc).__name__}: {exc}"
            _note(engine, account, cfg, action, "failed", streak, detail.replace(password, "[redacted]") if password else detail)
        return False
