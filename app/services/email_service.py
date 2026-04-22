"""
Email notifications via SMTP (Gmail or any SMTP with STARTTLS).

Gmail setup:
  1. Enable 2FA on Google account
  2. Generate App Password at myaccount.google.com/apppasswords
  3. Set SMTP_PASS to the app password (no spaces)
"""
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import get_settings
from app.models.wishlist import WishlistItem
from app.models.listing import Listing

log = logging.getLogger(__name__)
settings = get_settings()


def _build_html(item: WishlistItem, new_listings: list[Listing]) -> str:
    rows = ""
    for l in new_listings:
        condition_color = "#1E7A44" if l.condition in ("M", "NM", "VG+") else "#976B00"
        rows += f"""
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #e2e2df;">
            <strong style="color:#1B1B19;">{l.condition or '—'}</strong>
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #e2e2df;font-variant-numeric:tabular-nums;">
            <strong>{l.currency} {l.price:.2f}</strong>
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #e2e2df;color:#5A5A54;">
            {l.seller_username or '—'} {f'({l.seller_feedback:.1f}%)' if l.seller_feedback else ''}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #e2e2df;color:#5A5A54;">
            {l.ships_from or '—'}
          </td>
          <td style="padding:10px 16px;border-bottom:1px solid #e2e2df;">
            <a href="{l.url}" style="color:#3A65D6;">Apri →</a>
          </td>
        </tr>"""

    count = len(new_listings)
    noun = "nuova inserzione" if count == 1 else "nuove inserzioni"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1B1B19;background:#F0F0EE;margin:0;padding:32px 0;">
  <div style="max-width:640px;margin:0 auto;background:#fff;border:1px solid #e2e2df;border-radius:8px;overflow:hidden;">

    <div style="background:#fff;padding:24px 32px;border-bottom:1px solid #e2e2df;">
      <p style="font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:#96968E;margin:0 0 8px;">LP Monitor · Nuovi match</p>
      <h1 style="font-size:20px;font-weight:600;letter-spacing:-0.03em;margin:0 0 4px;">{item.artist} — {item.title}</h1>
      <p style="font-size:13px;color:#5A5A54;margin:0;">{count} {noun} trovate su Discogs</p>
    </div>

    <div style="padding:0;">
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="background:#f7f7f5;">
            <th style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#96968E;padding:8px 16px;text-align:left;border-bottom:1px solid #e2e2df;">Cond.</th>
            <th style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#96968E;padding:8px 16px;text-align:left;border-bottom:1px solid #e2e2df;">Prezzo</th>
            <th style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#96968E;padding:8px 16px;text-align:left;border-bottom:1px solid #e2e2df;">Venditore</th>
            <th style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#96968E;padding:8px 16px;text-align:left;border-bottom:1px solid #e2e2df;">Paese</th>
            <th style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#96968E;padding:8px 16px;text-align:left;border-bottom:1px solid #e2e2df;">Link</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>

    <div style="padding:20px 32px;border-top:1px solid #e2e2df;">
      <p style="font-size:11px;color:#96968E;margin:0;">
        LP Monitor · Istanza privata ·
        <a href="http://vinylmonitor.dffm.it/results" style="color:#3A65D6;">Vedi tutti i risultati</a>
      </p>
    </div>
  </div>
</body>
</html>"""


def send_new_listings(item: WishlistItem, new_listings: list[Listing]) -> bool:
    """Send email notification for new listings. Returns True on success."""
    if not settings.email_enabled:
        log.debug("Email disabled, skipping notification")
        return False
    if not all([settings.smtp_user, settings.smtp_pass, settings.mail_to]):
        log.warning("SMTP not configured, skipping email")
        return False
    if not new_listings:
        return False

    count = len(new_listings)
    subject = f"LP Monitor: {count} nuov{'a' if count == 1 else 'e'} — {item.artist} · {item.title}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = settings.mail_to

    html_body = _build_html(item, new_listings)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for attempt in range(3):
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_pass)
                smtp.sendmail(msg["From"], [settings.mail_to], msg.as_string())
            log.info("Email sent: item=%s listings=%d", item.id, count)
            return True
        except smtplib.SMTPAuthenticationError as exc:
            log.error("SMTP auth failed: %s", exc)
            return False  # No point retrying auth errors
        except Exception as exc:
            log.warning("Email attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))

    log.error("Email failed after 3 attempts for item %s", item.id)
    return False
