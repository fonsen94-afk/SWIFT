"""
Swift Alliance - Streamlit UI (persisted settings)

This updated Streamlit app adds persistent settings (schema and logo) saved to
./config.json and stores uploaded files into ./assets/ so they survive server restarts.

Run:
  pip install -r requirements.txt
  streamlit run swift_alliance_streamlit.py
"""

import streamlit as st
import tempfile
import os
import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
import io
import shutil

# Local modules (must be present in same directory)
from swift_alliance_bank import create_bank_instance, demo  # demo() creates sample data
from swift_messages import generate_mt103, generate_pain001, payment_from_transaction
from swift_iso_validator import validate_pain001_generated, validate_mt103_text, SchemaNotFoundError
import config_manager

# Optional paramiko for SFTP (only used if available)
try:
    import paramiko
    HAS_PARAMIKO = True
except Exception:
    HAS_PARAMIKO = False

# Ensure assets directory exists for persistent uploads
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

st.set_page_config(page_title="Swift Alliance - Message Converter & Validator", layout="wide")

st.title("Swift Alliance — Message Converter & ISO20022 Validator (Streamlit)")

# Load persistent config
config = config_manager.load_config()
if "schema_path" not in st.session_state:
    st.session_state["schema_path"] = config.get("schema_path")
if "logo_path" not in st.session_state:
    st.session_state["logo_path"] = config.get("logo_path")

# Left column: bank/accounts and helpers
col1, col2 = st.columns([1, 2])

with col1:
    st.header("Backend / Accounts")
    bank = create_bank_instance()
    if not bank.accounts:
        st.warning("No accounts found in bank data. Use the button below to create demo data or register customers in the CLI.")
    if st.button("Create demo data (adds one customer + accounts)"):
        demo()
        bank = create_bank_instance()
        st.success("Demo data created. Refreshing accounts...")

    account_options = ["-- Select account --"] + sorted(list(bank.accounts.keys()))
    selected_account = st.selectbox("Select account number", account_options)

    st.markdown("**Selected account details**")
    if selected_account and selected_account != "-- Select account --":
        acc = bank.accounts.get(selected_account)
        if acc:
            cust = bank.customers.get(acc.customer_id)
            st.write(f"Account: `{acc.account_number}`")
            st.write(f"Type: {acc.account_type.value}")
            st.write(f"Currency: {acc.currency.value}")
            st.write(f"Balance: {acc.balance.quantize(Decimal('0.01'))}")
            if cust:
                st.write(f"Customer: {cust.first_name} {cust.last_name} ({cust.customer_id})")
    st.markdown("---")
    st.header("Schema / Logo (persistent)")

    # Schema upload or select existing persistent schema
    st.write("Current schema (persisted):", os.path.basename(st.session_state.get("schema_path")) if st.session_state.get("schema_path") else "None")
    uploaded_xsd = st.file_uploader("Upload pain.001 XSD (optional, persisted)", type=["xsd"])
    if uploaded_xsd is not None:
        # save to assets/schemas/
        schemas_dir = os.path.join(ASSETS_DIR, "schemas")
        os.makedirs(schemas_dir, exist_ok=True)
        target = os.path.join(schemas_dir, os.path.basename(uploaded_xsd.name))
        with open(target, "wb") as f:
            f.write(uploaded_xsd.read())
        st.session_state["schema_path"] = target
        # persist config
        config_manager.save_config({"schema_path": st.session_state["schema_path"], "logo_path": st.session_state.get("logo_path")})
        st.success(f"Schema uploaded and saved persistently at: {target}")

    # Allow choosing from persisted schemas in assets/schemas/
    schemas_dir = os.path.join(ASSETS_DIR, "schemas")
    if os.path.isdir(schemas_dir):
        available = sorted([f for f in os.listdir(schemas_dir) if f.lower().endswith(".xsd")])
        if available:
            sel = st.selectbox("Choose persisted schema (assets/schemas)", ["-- keep current --"] + available)
            if sel and sel != "-- keep current --":
                st.session_state["schema_path"] = os.path.join(schemas_dir, sel)
                config_manager.save_config({"schema_path": st.session_state["schema_path"], "logo_path": st.session_state.get("logo_path")})
                st.success(f"Selected schema: {sel}")

    # Logo uploader (persisted to ./assets/)
    st.write("Current logo (persisted):", os.path.basename(st.session_state.get("logo_path")) if st.session_state.get("logo_path") else "None")
    logo_file = st.file_uploader("Upload logo (PNG/SVG) to persist", type=["png", "svg", "jpg", "jpeg"])
    if logo_file:
        target = os.path.join(ASSETS_DIR, os.path.basename(logo_file.name))
        with open(target, "wb") as f:
            f.write(logo_file.read())
        st.session_state["logo_path"] = target
        config_manager.save_config({"schema_path": st.session_state.get("schema_path"), "logo_path": st.session_state["logo_path"]})
        st.success(f"Logo saved persistently at: {target}")

with col2:
    # Show persisted logo if present
    logo_path = st.session_state.get("logo_path")
    if logo_path and os.path.exists(logo_path):
        st.image(logo_path, width=300)
    else:
        st.markdown("*(No persisted logo — upload one in the left panel)*")

    st.header("Compose Payment")
    ordering_name = st.text_input("Ordering name", value="")
    ordering_account = st.text_input("Ordering account (IBAN)", value=(selected_account if selected_account and selected_account != "-- Select account --" else ""))
    beneficiary_name = st.text_input("Beneficiary name", value="")
    beneficiary_account = st.text_input("Beneficiary account (IBAN)", value="")
    beneficiary_bic = st.text_input("Beneficiary BIC (optional)", value="")
    col_amount1, col_amount2 = st.columns([1, 1])
    with col_amount1:
        amount_text = st.text_input("Amount (e.g., 1234.56)", value="0.00")
    with col_amount2:
        currency = st.text_input("Currency", value="USD")
    value_date = st.text_input("Value date (YYYY-MM-DD)", value=datetime.date.today().isoformat())
    remittance = st.text_area("Remittance information", value="")
    reference = st.text_input("Reference (optional)", value="")

    st.markdown("---")
    st.write("Select message format and actions:")

    fmt = st.radio("Format", ["ISO20022 pain.001 (XML)", "MT103 (text)"])

    # Buttons for actions
    btn_generate = st.button("Generate Preview")
    btn_validate = st.button("Validate Current Preview")
    btn_download = st.button("Download Message")
    btn_send_mock = st.button("Send (mock) — log locally / email (optional)")

    # Session store for preview content and validation
    if "preview_content" not in st.session_state:
        st.session_state["preview_content"] = ""
    if "validation_result" not in st.session_state:
        st.session_state["validation_result"] = {"valid": False, "errors": []}
    if "last_format" not in st.session_state:
        st.session_state["last_format"] = None

    def _build_payment_dict():
        # Validate amount
        try:
            amt = Decimal(amount_text.strip())
        except (InvalidOperation, ValueError):
            st.error("Invalid amount. Use numbers like 1234.56")
            return None
        return payment_from_transaction(
            account_number=ordering_account.strip(),
            account_name=ordering_name.strip(),
            beneficiary_account=beneficiary_account.strip(),
            beneficiary_name=beneficiary_name.strip(),
            amount=amt,
            currency=currency.strip() or "USD",
            value_date=value_date.strip() or None,
            remittance_info=remittance.strip() or None,
            beneficiary_bic=beneficiary_bic.strip() or None,
            reference=reference.strip() or None
        )

    # Generate preview
    if btn_generate:
        payment = _build_payment_dict()
        if payment is None:
            st.stop()
        if fmt.startswith("ISO20022"):
            xml = generate_pain001(payment)
            st.session_state["preview_content"] = xml
            st.session_state["last_format"] = "XML"
            st.success("XML preview generated")
            # Auto-validate if persisted schema present
            schema_path = st.session_state.get("schema_path")
            if schema_path and os.path.exists(schema_path):
                try:
                    valid, errors = validate_pain001_generated(xml, schema_path)
                    st.session_state["validation_result"] = {"valid": valid, "errors": errors or []}
                    if valid:
                        st.success("XML validated: VALID")
                    else:
                        st.error("XML validation: INVALID — see details below")
                except SchemaNotFoundError as e:
                    st.error(f"Schema error: {e}")
                    st.session_state["validation_result"] = {"valid": False, "errors": [str(e)]}
            else:
                st.warning("No persisted schema selected — upload a pain.001 XSD on the left to enable validation.")
                st.session_state["validation_result"] = {"valid": False, "errors": ["No schema uploaded for validation."]}
        else:
            mt = generate_mt103(payment)
            st.session_state["preview_content"] = mt
            st.session_state["last_format"] = "MT"
            valid, issues = validate_mt103_text(mt)
            st.session_state["validation_result"] = {"valid": valid, "errors": issues}
            if valid:
                st.success("MT103 generated and basic validation PASSED")
            else:
                st.error("MT103 basic validation FAILED — see details below")

    # Manual validate
    if btn_validate:
        content = st.session_state.get("preview_content", "")
        if not content:
            st.warning("No preview content to validate. Generate a message first.")
        else:
            if st.session_state.get("last_format") == "XML":
                schema_path = st.session_state.get("schema_path")
                if not schema_path or not os.path.exists(schema_path):
                    st.error("No persisted schema. Upload a pain.001 XSD on the left to validate XML.")
                else:
                    try:
                        valid, errors = validate_pain001_generated(content, schema_path)
                        st.session_state["validation_result"] = {"valid": valid, "errors": errors or []}
                        if valid:
                            st.success("XML validation: VALID")
                        else:
                            st.error("XML validation: INVALID")
                    except SchemaNotFoundError as e:
                        st.error(f"Schema error: {e}")
            else:
                valid, issues = validate_mt103_text(content)
                st.session_state["validation_result"] = {"valid": valid, "errors": issues}
                if valid:
                    st.success("MT103 validation: OK")
                else:
                    st.error("MT103 validation: issues found")

    # Show preview and validation results
    st.subheader("Preview")
    preview = st.session_state.get("preview_content", "")
    if preview:
        st.code(preview, language='xml' if st.session_state.get("last_format") == "XML" else 'text')
    else:
        st.info("No preview yet. Fill the form and click 'Generate Preview'.")

    st.subheader("Validation Result")
    val = st.session_state.get("validation_result", {"valid": False, "errors": []})
    if val["valid"]:
        st.success("Validation: VALID")
    else:
        st.error("Validation: INVALID or not performed")
    if val["errors"]:
        st.write("Issues:")
        for i, e in enumerate(val["errors"], start=1):
            st.write(f"{i}. {e}")

    # Download widget
    if btn_download:
        content = st.session_state.get("preview_content", "")
        if not content:
            st.warning("Nothing to download. Generate a preview first.")
        else:
            suffix = ".xml" if st.session_state.get("last_format") == "XML" else ".txt"
            filename = f"swift_message_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
            st.download_button("Download message", content, file_name=filename, mime="application/octet-stream")

    # Mock send: log or optional SMTP/SFTP
    if btn_send_mock:
        content = st.session_state.get("preview_content", "")
        if not content:
            st.warning("Nothing to send. Generate a preview first.")
        else:
            # Block by default if invalid (user can override)
            if not st.session_state.get("validation_result", {}).get("valid", False):
                if not st.checkbox("I understand message is invalid and want to continue sending (override)"):
                    st.stop()
            send_method = st.selectbox("Mock send method", ["Log locally", "Email (SMTP)", "Upload via SFTP (optional)"])
            if send_method == "Log locally":
                logf = "swift_send_log.txt"
                with open(logf, "a", encoding="utf-8") as f:
                    f.write(f"----- {datetime.datetime.utcnow().isoformat()} -----\n")
                    f.write(content + "\n\n")
                st.success(f"Message logged to {logf}")
            elif send_method == "Email (SMTP)":
                smtp_host = st.text_input("SMTP host (hostname:port)", value="smtp.example.com:587")
                smtp_user = st.text_input("SMTP username")
                smtp_pass = st.text_input("SMTP password", type="password")
                recipient = st.text_input("Recipient email")
                if st.button("Send email now"):
                    import smtplib
                    try:
                        host, port = smtp_host.split(":")
                        port = int(port)
                        with smtplib.SMTP(host, port, timeout=10) as s:
                            s.starttls()
                            s.login(smtp_user, smtp_pass)
                            msg = f"Subject: SWIFT Message\n\n{content}"
                            s.sendmail(smtp_user, [recipient], msg.encode("utf-8"))
                        st.success("Email sent (SMTP).")
                    except Exception as e:
                        st.error(f"SMTP send failed: {e}")
            else:
                if not HAS_PARAMIKO:
                    st.error("Paramiko not installed; SFTP not available.")
                else:
                    sftp_host = st.text_input("SFTP host")
                    sftp_port = st.number_input("SFTP port", value=22)
                    sftp_user = st.text_input("SFTP user")
                    sftp_pass = st.text_input("SFTP password", type="password")
                    remote_path = st.text_input("Remote path (full filename)", value="/upload/message.txt")
                    if st.button("Upload via SFTP now"):
                        try:
                            transport = paramiko.Transport((sftp_host, int(sftp_port)))
                            transport.connect(username=sftp_user, password=sftp_pass)
                            sftp = paramiko.SFTPClient.from_transport(transport)
                            with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
                                tf.write(content)
                                tmpname = tf.name
                            sftp.put(tmpname, remote_path)
                            sftp.close()
                            transport.close()
                            os.unlink(tmpname)
                            st.success("Uploaded via SFTP.")
                        except Exception as e:
                            st.error(f"SFTP upload failed: {e}")

st.markdown("---")
st.markdown("Notes: This is a local-only demo utility. For production SWIFT submissions use a certified gateway.")