import os
import requests
import streamlit as st
import logging
from dotenv import load_dotenv
import time
import hmac
import re

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
API_BASE = os.getenv("API_BASE")
API_KEY = os.getenv("RM_API_KEY")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# --- Streamlit Page Setup ---
st.set_page_config(
    page_title="CSM Backend Portal - Next Quarter",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* Brand accent you can reuse */
:root, .stApp { --brand: #00c951; }

/* Respect Streamlit theme (no 'force light', no !important) */
.stApp {
  background: var(--background-color);
  color: var(--text-color);
}
.block-container { padding-top: 2rem; padding-bottom: 2rem; }

/* Inputs */
.stTextInput input,
.stSelectbox [role="combobox"],
.stNumberInput input,
.stFileUploader {
  background: var(--secondary-background-color);
  color: var(--text-color);
  border-radius: 8px;
}

/* Buttons — keep to theme colors and avoid !important */
/* Buttons — use brand directly */
.stButton > button {
  background: var(--brand);
  border: 1px solid var(--brand);
  color: #ffffff;
  border-radius: 8px;
  font-weight: 600;
  padding: 0.6rem 1rem;
  transition: transform .02s ease, filter .15s ease;
}
.stButton > button:hover { filter: brightness(0.95); }
.stButton > button:active { transform: translateY(1px); }


/* Tabs – underline style with brand accent, theme-aware borders/text */
.stTabs [data-baseweb="tab-list"] {
  gap: 18px;
  border-bottom: 1px solid rgba(0,0,0,.12);
}
[data-theme="dark"] .stTabs [data-baseweb="tab-list"] {
  border-bottom-color: rgba(255,255,255,.16);
}
.stTabs [data-baseweb="tab"] {
  background: transparent;
  border: none;
  height: 44px;
  padding: 0 6px;
  color: var(--text-color);
  opacity: .75;
  font-weight: 600;
  border-bottom: 2px solid transparent;
  transition: color .15s ease, border-color .15s ease, opacity .15s ease;
}
.stTabs [data-baseweb="tab"]:hover {
  opacity: 1;
  border-bottom: 2px solid rgba(0,0,0,.12);
}
[data-theme="dark"] .stTabs [data-baseweb="tab"]:hover {
  border-bottom-color: rgba(255,255,255,.16);
}
.stTabs [aria-selected="true"] {
  color: var(--brand);
  border-bottom: 2px solid var(--brand);
  opacity: 1;
}

/* Sidebar labels */
.sidebar-title {
  font-weight: 700;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(0,0,0,.55);
  margin-bottom: 0.25rem;
}
[data-theme="dark"] .sidebar-title { color: rgba(255,255,255,.6); }
.sidebar-value { font-weight: 600; margin-bottom: 0.75rem; }

/* Alerts */
.stAlert { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ------------------------------
# (A) PIN GATE — Streamlit-only
# ------------------------------
def _get_pin_from_env() -> str | None:
    # Prefer env; fall back to st.secrets to support Streamlit Cloud
    pin = os.getenv("APP_PIN")
    if not pin:
        try:
            pin = st.secrets.get("APP_PIN")  # type: ignore[attr-defined]
        except Exception:
            pin = None
    if pin and isinstance(pin, (int, float)):
        pin = str(int(pin)).zfill(6)
    if pin and isinstance(pin, str):
        pin = pin.strip()
    return pin

def _valid_six_digit(pin: str | None) -> bool:
    return bool(pin and re.fullmatch(r"\d{6}", pin))

def require_pin():
    """Blocks the UI until a valid 6-digit APP_PIN is provided."""
    PIN = _get_pin_from_env()

    # Fail closed if misconfigured
    if not _valid_six_digit(PIN):
        st.error("Server misconfigured: APP_PIN (6 digits) not set.")
        logger.critical("APP_PIN missing or invalid; must be 6 digits.")
        st.stop()

    # Session flags
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if "failed_attempts" not in st.session_state:
        st.session_state.failed_attempts = 0
    if "lock_until" not in st.session_state:
        st.session_state.lock_until = 0.0

    # Lockout check (simple anti-bruteforce)
    now = time.time()
    if now < st.session_state.lock_until:
        wait_s = int(st.session_state.lock_until - now)
        st.warning(f"Too many incorrect attempts. Try again in {wait_s} second(s).")
        st.stop()

    if st.session_state.authed:
        return

    st.title("Enter Access PIN")
    with st.form("pin_form", clear_on_submit=False):
        pin_try = st.text_input("6-digit PIN", type="password", max_chars=6)
        submit = st.form_submit_button("Unlock")

    if submit:
        if hmac.compare_digest(pin_try.strip(), PIN):  # constant-time compare
            st.session_state.authed = True
            st.session_state.failed_attempts = 0
            st.session_state.lock_until = 0.0
            st.success("Unlocked")
            st.experimental_rerun()
        else:
            st.session_state.failed_attempts += 1
            # Lock out for 60s after 5 wrong tries (tweak as desired)
            if st.session_state.failed_attempts >= 5:
                st.session_state.lock_until = time.time() + 60
                st.warning("Too many attempts. Locked for 60 seconds.")
            else:
                remaining = 5 - st.session_state.failed_attempts
                st.error(f"Incorrect PIN. {remaining} attempt(s) remaining.")
            st.stop()

# Call the gate as early as possible, before any app content/API errors
require_pin()


# --- Session State ---
def initialize_session_state():
    defaults = {
        'setup_complete': False,
        'ds_root': '',
        'customer_id': '',
        'customer_name': '',
        'account_names': [],
        'contact_upload_version': 0,
        'contact_upload_notice': None,
        'contact_upload_payload': None,
        'rc_last_status': None,
        'rc_last_error': None,
        'rc_started_once': False,

        # NEW for Update Ranks
        'manual_rows': [],             # holds rows for manual entry
        'ranks_upload_version': 0,     # remounts the Excel uploader after success
        'ranks_notice': None           # one-shot success toast
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

initialize_session_state()

# --- API Helper ---
def make_api_request(method, endpoint, **kwargs):
    url = f"{API_BASE}/api/{endpoint}"
    try:
        resp = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        logger.error(f"HTTP Error for {url}: {e}")
    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed: {e}")
        logger.error(f"API request failed for {url}: {e}")
    return None

# --- Tabs ---
def initial_setup_tab():
    st.header("Initial Setup")

    # Simple connect form
    with st.form("connect_form", clear_on_submit=False):
        customer_id = st.text_input(
            "Customer ID",
            value=st.session_state.get('customer_id', ''),
            help="Unique identifier for the customer."
        )
        connect = st.form_submit_button("Connect to Repo")

    if connect:
        if not customer_id:
            st.error("Please enter a Customer ID.")
            return

        with st.spinner("Validating path and fetching customer data..."):
            # 1) Validate path & get ds_root + customer_name
            validate_resp = make_api_request("post", "validate_path", data={"customer_id": customer_id})
            if not validate_resp:
                return

            ds_root = validate_resp.get("ds_root", "")
            customer_name = validate_resp.get("customer_name", "")

            # 2) Fetch accounts
            account_response = make_api_request("post", "accountnames", data={"customer_id": customer_id})
            if not account_response or not account_response.get("accounts"):
                st.error("No accounts found for this customer ID or failed to fetch them.")
                logger.warning(f"No accounts found for customer_id={customer_id}")
                return

            account_names = account_response["accounts"]
            selected_account = account_names[0]

            # 3) Setup with default operation = "Nothing" (not shown to user)
            setup_data = {
                "ds_path": ds_root,
                "operation": "Nothing",
                "account": selected_account
            }
            setup_response = make_api_request("post", "setup", data=setup_data)
            if not setup_response:
                return

        # Persist state and move on
        st.session_state['ds_root'] = ds_root
        st.session_state['customer_id'] = customer_id
        st.session_state['customer_name'] = customer_name
        st.session_state['account_names'] = account_names
        st.session_state['setup_complete'] = True
        st.success("Connected successfully.")
        st.rerun()

def usage_tracking_tab():
    st.header("Usage Tracking")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable downloads.")
        return

    st.info("Download Qpilot usage tracking (5 tables) as a single Excel file.")

    label = f"Prepare Usage Tracking data for {st.session_state['customer_name']}" \
            if st.session_state['customer_name'] else "Download Usage Tracking"

    if st.button(label):
        with st.spinner("Preparing usage tracking Excel..."):
            url = f"{API_BASE}/api/download_usage_tracking"
            try:
                resp = requests.get(
                    url,
                    headers=HEADERS,
                    params={"customer_id": st.session_state['customer_id']},
                    timeout=120
                )
                resp.raise_for_status()
                st.download_button(
                    label="Click to download",
                    data=resp.content,
                    file_name=f"{st.session_state['customer_name'] or 'customer'}_{st.session_state['customer_id']}_Qpilot Usage tracking.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                logger.info(f"Usage tracking downloaded for {st.session_state['customer_name']}")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to download usage tracking: {e}")
                logger.error(f"Usage tracking download failed: {e}")

def refresh_config_tab():
    """Re-run config generation and live-monitor status (auto-polls for ~7 minutes)."""
    st.header("Refresh Config")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable this section.")
        return

    st.write("Click the button below to update config files with the latest product offerings.")

    if st.button("Re-run Config Generation", disabled=disabled):
        with st.spinner("Triggering config generation..."):
            resp = make_api_request(
                "post",
                "refreshconfig",
                data={"customer_id": st.session_state['customer_id']}
            )

        if not resp or not resp.get("success"):
            st.error("Failed to start config generation.")
            return

        st.success("Launching script and monitoring progress...")

        # UI placeholders
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Poll every 2s for up to 7 minutes
        start = time.time()
        timeout = 7 * 60
        while time.time() - start < timeout:
            time.sleep(2)
            status_resp = make_api_request(
                "get",
                "config_status",
                params={"customer_id": st.session_state['customer_id']}
            )

            if not status_resp:
                status_text.warning("Unable to fetch progress.")
                continue

            progress = float(status_resp.get("progress", 0.0))
            raw_status = (status_resp.get("status") or "").strip()

            # Friendly copy (same vibes as your sample)
            if raw_status.lower().startswith("starting"):
                pretty = "Content loaded from DB. Generation has started."
            elif raw_status.lower().startswith("generating"):
                pretty = "Generating config & JD…"
            elif raw_status.lower().startswith("completed"):
                pretty = "Completed"
            elif raw_status.lower().startswith("error"):
                pretty = "Error occurred"
            else:
                pretty = raw_status or "Unknown"

            progress_bar.progress(max(0.0, min(1.0, progress)))
            status_text.write(f"Status: **{pretty}**")

            if raw_status.lower().startswith("completed"):
                st.success("Configuration completed successfully.")
                break
            if raw_status.lower().startswith("error"):
                st.error("An error occurred. Check server logs for details.")
                break
        else:
            st.warning("Config generation timed out after 7 minutes. It may still complete in the background.")

def contacts_tab():
    st.header("Manage Contacts")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable this section.")
        return

    # If we have a persisted notice from last run, show it once
    if st.session_state.get('contact_upload_notice'):
        st.success(st.session_state['contact_upload_notice'])
        st.session_state['contact_upload_notice'] = None
        st.session_state['contact_upload_payload'] = None

    account = st.selectbox("Account", st.session_state.get('account_names', []), key="contact_account")

    st.subheader("Upload new contacts (CSV)")

    uploader_key = f"contact_upload_{st.session_state.get('contact_upload_version', 0)}"
    contact_file = st.file_uploader("Choose a CSV file", type=["csv"], key=uploader_key)

    submit_disabled = contact_file is None
    if st.button("Submit New Contacts", disabled=submit_disabled):
        try:
            files = {"file": (f"{account}.csv", contact_file.getvalue())}
            data = {"account": account}
            with st.spinner("Uploading contacts..."):
                response = make_api_request("post", "upload_contacts", files=files, data=data)

            if response:
                st.session_state['contact_upload_notice'] = "Contacts uploaded successfully."
                st.session_state['contact_upload_payload'] = response
                st.session_state['contact_upload_version'] = st.session_state.get('contact_upload_version', 0) + 1
                st.rerun()
            else:
                st.error("Upload failed. Please check the file and try again.")
        except Exception as e:
            st.error(f"Unexpected error during upload: {e}")

def ranks_tab():
    """Update initiative ranks via Excel upload or manual entry."""
    st.header("Update Ranks")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable this section.")
        return

    if st.session_state.get('ranks_notice'):
        st.success(st.session_state['ranks_notice'])
        st.session_state['ranks_notice'] = None

    account = st.selectbox("Account", st.session_state.get('account_names', []), key="ranks_account")

    mode = st.radio("Choose update method", ["Upload Excel file", "Manual entry"], horizontal=True)

    if mode == "Upload Excel file":
        st.caption("Your Excel must contain columns: **initiativename** and **rank**.")

        uploader_key = f"ranks_upload_{st.session_state.get('ranks_upload_version', 0)}"
        excel_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"], key=uploader_key)

        submit_disabled = excel_file is None
        if st.button("Submit Ranks from Excel", disabled=submit_disabled):
            import pandas as pd
            try:
                df = pd.read_excel(excel_file)
            except Exception as e:
                st.error(f"Could not read Excel: {e}")
                return

            required = {"initiativename", "rank"}
            if not required.issubset(set(df.columns.str.lower())):
                st.error("The uploaded Excel must have columns: initiativename, rank")
                return

            df.columns = [c.lower() for c in df.columns]
            rows = (
                df[["initiativename", "rank"]]
                .dropna(subset=["initiativename", "rank"])
                .to_dict("records")
            )
            if not rows:
                st.warning("No valid rows found.")
                return

            payload = {"account": account, "rows": rows}
            with st.spinner("Updating ranks..."):
                resp = make_api_request("post", "update_ranks", json=payload)

            if resp:
                st.session_state['ranks_notice'] = f"Ranks updated successfully: {resp.get('updated', len(rows))} record(s)."
                st.session_state['ranks_upload_version'] = st.session_state.get('ranks_upload_version', 0) + 1
                st.rerun()
            else:
                st.error("Server did not confirm the update. Please check logs.")

    else:  # Manual entry
        st.caption("Add or edit initiatives below, then submit.")

        to_delete = None
        for i, row in enumerate(st.session_state['manual_rows']):
            c1, c2, c3 = st.columns([5, 2, 1])
            st.session_state['manual_rows'][i]['initiativename'] = c1.text_input(
                "Initiative Name",
                value=row.get("initiativename", ""),
                key=f"ini_{i}",
            )
            st.session_state['manual_rows'][i]['rank'] = c2.number_input(
                "Rank",
                min_value=1,
                value=int(row.get("rank", i + 1)) if str(row.get("rank", "")).isdigit() else 1,
                key=f"rank_{i}",
            )
            if c3.button("Remove", key=f"del_{i}"):
                to_delete = i

        if to_delete is not None:
            st.session_state['manual_rows'].pop(to_delete)
            st.rerun()

        c1, c2 = st.columns([1, 2])
        if c1.button("Add Initiative"):
            st.session_state['manual_rows'].append({"initiativename": "", "rank": len(st.session_state['manual_rows']) + 1})
            st.rerun()

        submit_disabled = not st.session_state['manual_rows']
        if c2.button("Submit Manual Ranks", disabled=submit_disabled):
            rows = [r for r in st.session_state['manual_rows'] if str(r.get("initiativename", "")).strip()]
            if not rows:
                st.warning("Please add at least one initiative with a name.")
                return

            payload = {"account": account, "rows": rows}
            with st.spinner("Updating ranks..."):
                resp = make_api_request("post", "update_ranks", json=payload)

            if resp:
                st.success(f"Ranks updated successfully: {resp.get('updated', len(rows))} record(s).")
                st.session_state['manual_rows'] = []
            else:
                st.error("Server did not confirm the update. Please check logs.")

def offerings_tab():
    st.header("Product Offerings")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable downloads.")
        return

    st.info("Generate and download the current product offerings as an Excel file.")
    label = f"Download Offerings for {st.session_state['customer_name']}" if st.session_state['customer_name'] else "Download Offerings"

    if st.button(label):
        with st.spinner("Preparing download..."):
            url = f"{API_BASE}/api/download_products_excel"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=60)
                resp.raise_for_status()
                st.download_button(
                    label="Click to download",
                    data=resp.content,
                    file_name=f"{st.session_state['customer_name'] or 'customer'}_product_offerings.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                logger.info(f"Product offerings downloaded for {st.session_state['customer_name']}")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to download product offerings: {e}")
                logger.error(f"Download failed: {e}")

# --- Main ---
def main():
    st.title("CSM Backend Portal - Next Quarter")

    if st.session_state.setup_complete:
        with st.sidebar:
            st.markdown("### Customer Details")
            st.markdown(f"**Name:** {st.session_state['customer_name']}")
            st.markdown(f"**ID:** {st.session_state['customer_id']}")
            st.markdown(f"**Accounts:** {len(st.session_state.get('account_names', []))}")

    t1, t2, t3, t4, t5 = st.tabs(
        ["Initial Setup", "Manage Contacts", "Product Offerings", "Usage Tracking", "Update Ranks"]
    )
    with t1:
        initial_setup_tab()
    with t2:
        contacts_tab()
    with t3:
        offerings_tab()
    with t4:
        usage_tracking_tab()
    with t5:
        ranks_tab()

if __name__ == "__main__":
    # NOTE: API key/base checks now run AFTER the PIN gate to avoid leaking info to unauthenticated users.
    if not API_KEY:
        st.error("API_KEY is not set. Please configure it in your environment variables.")
        logger.critical("RM_API_KEY environment variable not found.")
    elif not API_BASE:
        st.error("API_BASE is not set. Please configure it in your environment variables.")
        logger.critical("API_BASE environment variable not found.")
    else:
        main()
