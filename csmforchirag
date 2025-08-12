import os
import requests
import streamlit as st
import logging
from dotenv import load_dotenv

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

# --- Light UI / Styling (Green #00c951 + White) ---
st.markdown("""
<style>
/* Force light */
html, body, .stApp { background: #ffffff !important; color: #0f1419 !important; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; }

/* Inputs */
.stTextInput>div>div>input,
.stSelectbox>div>div>div>div,
.stFileUploader,
.stNumberInput>div>div>input {
    background: #f7f9fb !important;
    border-radius: 8px !important;
}

/* Buttons */
.stButton>button {
    background: #00c951 !important;
    color: #ffffff !important;
    border: 1px solid #00c951 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1rem !important;
    transition: transform .02s ease, filter .15s ease;
}
.stButton>button:hover { filter: brightness(0.95); }
.stButton>button:active { transform: translateY(1px); }

/* Tabs – underline style with green accent */
.stTabs [data-baseweb="tab-list"] {
    gap: 18px;
    border-bottom: 1px solid #ececec;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: none;
    height: 44px;
    padding: 0 6px;
    color: #4b5563;
    font-weight: 600;
    border-bottom: 2px solid transparent;
    transition: color .15s ease, border-color .15s ease;
}
.stTabs [data-baseweb="tab"]:hover { color: #0f1419; border-bottom: 2px solid #e5e7eb; }
.stTabs [aria-selected="true"] { color: #00c951; border-bottom: 2px solid #00c951; }

/* Sidebar labels */
.sidebar-title {
    font-weight: 700;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #6b7280;
    margin-bottom: 0.25rem;
}
.sidebar-value {
    font-weight: 600;
    margin-bottom: 0.75rem;
}

/* Info and success boxes – subtle */
.stAlert {
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)

# --- Session State ---
def initialize_session_state():
    defaults = {
        'setup_complete': False,
        'ds_root': '',
        'customer_id': '',
        'customer_name': '',
        'account_names': [],
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
        customer_id = st.text_input("Customer ID", value=st.session_state.get('customer_id', ''), help="Unique identifier for the customer.")
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

    # No duplicate details here—sidebar handles the summary.

def contacts_tab():
    st.header("Manage Contacts")
    disabled = not st.session_state.setup_complete

    if disabled:
        st.info("Complete Initial Setup to enable this section.")
        return

    account = st.selectbox("Account", st.session_state.get('account_names', []), key="contact_account")

    st.subheader("Upload new contacts (CSV)")
    contact_file = st.file_uploader("Choose a CSV file", type=["csv"], key="contact_upload")
    if contact_file and st.button("Submit New Contacts"):
        files = {"file": (f"{account}.csv", contact_file.getvalue())}
        data = {"account": account}
        with st.spinner("Uploading contacts..."):
            response = make_api_request("post", "upload_contacts", files=files, data=data)
            if response:
                st.success("Contacts uploaded successfully.")

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

    # Sidebar: show details ONLY here (no operation mentioned)
    if st.session_state.setup_complete:
        with st.sidebar:
            st.markdown("### Customer Details")
            st.markdown(f"**Name:** {st.session_state['customer_name']}")
            st.markdown(f"**ID:** {st.session_state['customer_id']}")
            st.markdown(f"**Accounts:** {len(st.session_state.get('account_names', []))}")

    # Only the three requested tabs
    t1, t2, t3 = st.tabs(["Initial Setup", "Manage Contacts", "Product Offerings"])
    with t1:
        initial_setup_tab()
    with t2:
        contacts_tab()
    with t3:
        offerings_tab()

if __name__ == "__main__":
    if not API_KEY:
        st.error("API_KEY is not set. Please configure it in your environment variables.")
        logger.critical("RM_API_KEY environment variable not found.")
    elif not API_BASE:
        st.error("API_BASE is not set. Please configure it in your environment variables.")
        logger.critical("API_BASE environment variable not found.")
    else:
        main()
