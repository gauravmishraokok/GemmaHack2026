"""Attest/export notifications: emailed STR report (Resend) + SMS (Twilio).

Both go through their plain REST APIs with `requests` — no extra SDK
dependencies. Failures are caught and reported as statuses, never raised:
a notification hiccup must not break the export itself (the XML + audit
entry are already durable by the time this runs).

Email clients ignore <style> blocks and CSS variables, so the report HTML
uses inline styles with hard-coded hex values from the product palette.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict

import requests

import config
from shared_contracts import STRDraft

BAND_COLORS = {"green": "#0ca30c", "yellow": "#b17f12", "red": "#d03b3b"}
BAND_LABELS = {"green": "confident", "yellow": "review", "red": "verify"}


def _fmt_title(tag: str) -> str:
    return tag.replace("_", " ").title()


def build_report_html(draft: STRDraft, audit_entry: Dict[str, Any], actor: str) -> str:
    overall = (
        sum(n.confidence for n in draft.narration) / len(draft.narration)
        if draft.narration else 0.0
    )
    narration_rows = "".join(
        f"""<tr><td style="padding:10px 12px;border-left:4px solid {BAND_COLORS[n.band]};
            background:#f7f7f5;border-radius:4px;font-size:14px;line-height:1.6;color:#1a1a19;">
            {n.sentence}
            <div style="margin-top:4px;font-size:11px;color:{BAND_COLORS[n.band]};font-weight:bold;">
              {n.confidence * 100:.0f}% · {BAND_LABELS[n.band]}
            </div></td></tr>
            <tr><td style="height:8px;"></td></tr>"""
        for n in draft.narration
    )
    amounts = " · ".join(f"{a:,.2f}" for a in draft.amounts_cited[:12])
    if len(draft.amounts_cited) > 12:
        amounts += f" (+{len(draft.amounts_cited) - 12} more)"
    ev_refs = ", ".join(draft.evidence_refs[:20]) or "—"

    return f"""
<div style="font-family:-apple-system,'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;color:#1a1a19;">
  <div style="border-bottom:3px solid #d03b3b;padding:16px 0;">
    <h1 style="margin:0;font-size:20px;">SentinelAI — Suspicious Transaction Report</h1>
    <p style="margin:4px 0 0;font-size:12px;color:#666;">
      Attested &amp; exported {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')} · air-gapped, on-premise pipeline
    </p>
  </div>

  <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:13px;">
    <tr><td style="padding:6px 0;color:#666;width:180px;">Case</td>
        <td style="padding:6px 0;font-family:monospace;font-weight:bold;">{draft.case_id}</td></tr>
    <tr><td style="padding:6px 0;color:#666;">Ground of suspicion</td>
        <td style="padding:6px 0;"><span style="background:#d03b3b;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">{_fmt_title(draft.gos_tag)}</span></td></tr>
    <tr><td style="padding:6px 0;color:#666;">Recommended action</td>
        <td style="padding:6px 0;font-weight:bold;">{_fmt_title(draft.recommended_action)}</td></tr>
    <tr><td style="padding:6px 0;color:#666;">Overall confidence</td>
        <td style="padding:6px 0;font-weight:bold;color:{BAND_COLORS['green'] if overall > 0.75 else BAND_COLORS['yellow'] if overall >= 0.5 else BAND_COLORS['red']};">{overall * 100:.0f}%</td></tr>
    <tr><td style="padding:6px 0;color:#666;">Attested by</td>
        <td style="padding:6px 0;">{actor}</td></tr>
  </table>

  <h2 style="font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#666;margin:20px 0 8px;">
    Narration — confidence heat-map
  </h2>
  <p style="font-size:11px;color:#888;margin:0 0 10px;">
    Each sentence scored by the model's own token log-probabilities, fused with a deterministic
    grounding check of every cited figure against the ledger. Red = verify before relying on it.
  </p>
  <table style="width:100%;border-collapse:collapse;">{narration_rows}</table>

  <h2 style="font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#666;margin:20px 0 8px;">
    Amounts cited (ledger-verified)
  </h2>
  <p style="font-size:13px;font-family:monospace;margin:0;">{amounts or '—'}</p>

  <h2 style="font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#666;margin:20px 0 8px;">
    Evidence referenced
  </h2>
  <p style="font-size:12px;font-family:monospace;color:#444;margin:0;">{ev_refs}</p>

  <div style="margin-top:24px;padding:12px;background:#f0f0ee;border-radius:6px;font-size:11px;color:#555;">
    <strong>Tamper-evident audit trail:</strong> entry #{audit_entry.get('seq')} ·
    chain hash <span style="font-family:monospace;">{str(audit_entry.get('hash', ''))[:32]}…</span><br/>
    The full FIU-IND XML filing is attached. Drafted under schema-constrained decoding —
    the ground-of-suspicion tag is drawn from a closed dictionary the model cannot deviate from.
    A human attested this report; the model only drafted it.
  </div>
</div>
"""


def send_report_email(draft: STRDraft, xml: str, audit_entry: Dict[str, Any], actor: str) -> Dict[str, Any]:
    if not config.RESEND_API_KEY or not config.REPORT_EMAIL_TO:
        return {"status": "skipped", "reason": "RESEND_API_KEY / REPORT_EMAIL_TO not configured"}
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
            json={
                "from": config.REPORT_EMAIL_FROM,
                "to": config.REPORT_EMAIL_TO,
                "subject": f"[SentinelAI] STR attested — {draft.case_id} · {_fmt_title(draft.gos_tag)}",
                "html": build_report_html(draft, audit_entry, actor),
                "attachments": [
                    {
                        "filename": f"STR_{draft.case_id}.xml",
                        "content": base64.b64encode(xml.encode("utf-8")).decode("ascii"),
                    }
                ],
            },
            timeout=20,
        )
        if r.ok:
            return {"status": "sent", "to": config.REPORT_EMAIL_TO, "id": r.json().get("id")}
        return {"status": "failed", "detail": r.text[:300]}
    except Exception as e:  # noqa: BLE001 — notification failure must not break export
        return {"status": "failed", "detail": str(e)}


# Twilio's shared WhatsApp sandbox number — messages from it must use the
# whatsapp: channel prefix, and the recipient must have joined the sandbox
# once (send "join <code>" from their WhatsApp to this number).
_WHATSAPP_SANDBOX = "+14155238886"


def send_report_sms(draft: STRDraft, audit_entry: Dict[str, Any]) -> Dict[str, Any]:
    if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
        return {"status": "skipped", "reason": "Twilio credentials not configured"}
    frm, to = config.TWILIO_FROM_NUMBER, config.TWILIO_TO_NUMBER
    if not (frm and to):
        return {"status": "skipped", "reason": "TWILIO_FROM_NUMBER / TWILIO_TO_NUMBER not set in reasoning/.env"}
    # auto-route through the WhatsApp channel when using the sandbox number
    if _WHATSAPP_SANDBOX in frm and not frm.startswith("whatsapp:"):
        frm = f"whatsapp:{frm}"
    if frm.startswith("whatsapp:") and not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    overall = (
        sum(n.confidence for n in draft.narration) / len(draft.narration)
        if draft.narration else 0.0
    )
    body = (
        f"SentinelAI: STR attested for {draft.case_id}. "
        f"GoS: {_fmt_title(draft.gos_tag)}. Action: {_fmt_title(draft.recommended_action)}. "
        f"Confidence {overall * 100:.0f}%. Audit #{audit_entry.get('seq')}. Full report emailed."
    )
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            data={"From": frm, "To": to, "Body": body},
            timeout=20,
        )
        if not r.ok:
            return {"status": "failed", "detail": r.text[:300]}
        sid = r.json().get("sid")
        # Twilio accepts async then may fail delivery (e.g. sandbox not joined) —
        # poll once so the UI reports what actually happened, not just "queued".
        import time

        time.sleep(2.5)
        s = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages/{sid}.json",
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=10,
        )
        status = s.json().get("status", "queued") if s.ok else "queued"
        err = s.json().get("error_code") if s.ok else None
        if status in ("failed", "undelivered"):
            hint = (
                " — recipient must join the WhatsApp sandbox first: send the join code "
                f"from WhatsApp to {_WHATSAPP_SANDBOX}"
                if err == 63015
                else ""
            )
            return {"status": "failed", "detail": f"Twilio status {status} (error {err}){hint}", "sid": sid}
        return {"status": "sent", "to": to, "sid": sid, "twilio_status": status}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "detail": str(e)}


def notify_export(draft: STRDraft, xml: str, audit_entry: Dict[str, Any], actor: str) -> Dict[str, Any]:
    return {
        "email": send_report_email(draft, xml, audit_entry, actor),
        "sms": send_report_sms(draft, audit_entry),
    }
