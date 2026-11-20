"""Send the latest update email with the workbook attached, over Gmail SMTP.
Run by .github/workflows/email-workbook.yml. Usage: python3 scripts/send_email.py [state/email.json]
Env: GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO (comma-separated). Missing secrets -> prints a notice and exits 0."""
import json, os, smtplib, ssl, sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
user, pw = os.environ.get("GMAIL_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
to = [x.strip() for x in os.environ.get("MAIL_TO", "").split(",") if x.strip()]
if not (user and pw and to):
    print("::notice::GMAIL_USER, GMAIL_APP_PASSWORD or MAIL_TO secret not set; skipping email.")
    sys.exit(0)

em = json.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "state" / "email.json"))
if em.get("to"):  # e.g. On-Market alerts go to their own address
    to = [x.strip() for x in em["to"].split(",") if x.strip()]
attach = em.get("attach", True)  # final-week alerts go out without the workbook
wb = ROOT / "state" / f"{em.get('sale_date')}.xlsx"
if attach and not wb.exists():
    sys.exit(f"workbook {wb} not found")

msg = EmailMessage()
msg["Subject"], msg["From"], msg["To"] = em["subject"], user, ", ".join(to)
msg.set_content(em.get("text") or em["subject"])
msg.add_alternative(em["html"], subtype="html")
if attach:
    msg.add_attachment(wb.read_bytes(), maintype="application",
                       subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       filename=f"Sheriff Sale {em['sale_date']} Prep.xlsx")
with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
    s.login(user, pw)
    s.send_message(msg)
print(f"sent '{em['subject']}' to {len(to)} recipient(s)" + (f" with {wb.name}" if attach else " (no attachment)"))
