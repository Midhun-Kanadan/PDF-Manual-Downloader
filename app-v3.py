import streamlit as st
import pandas as pd
import urllib.parse
import os
import zipfile
import json
from datetime import datetime
import time

# --- Page Config ---
st.set_page_config(page_title="PDF Manual Downloader", layout="wide")
st.title("📄 PDF Manual Downloader")

# --- Initialize Session State ---
if 'downloaded_keys' not in st.session_state:
    st.session_state.downloaded_keys = set()
if 'failed_keys' not in st.session_state:
    st.session_state.failed_keys = set()
if 'csv_uploaded' not in st.session_state:
    st.session_state.csv_uploaded = False

# --- Helper Functions ---
def copy_to_clipboard(text, key):
    """Helper function to copy text to clipboard if supported"""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except (ImportError, pyperclip.PyperclipException):
        st.warning("📋 Auto-copy is not available in this environment. Please copy manually.", icon="⚠️")
        return False
    except Exception as e:
        st.error(f"⚠️ Clipboard error: {str(e)}")
        return False

def get_doi_from_row(row):
    """Extracts a valid DOI from a row, checking DOI and URL columns."""
    # Check DOI column first
    if 'DOI' in row and pd.notna(row["DOI"]):
        doi = str(row["DOI"]).strip()
        if doi:
            return doi
    # Check URL column for a doi.org link
    if 'URL' in row and pd.notna(row["URL"]):
        url = str(row["URL"]).strip()
        if "doi.org" in url:
            # Extract the path part, which is the DOI
            return str(urllib.parse.urlparse(url).path).strip("/")
    return None

# --- Sidebar ---
with st.sidebar:
    st.header("📊 Progress Management")

    # Progress metrics
    if 'current_df' in st.session_state and st.session_state.csv_uploaded:
        total_files = len(st.session_state.current_df)
        completed_files = len(st.session_state.downloaded_keys)
        failed_files = len(st.session_state.failed_keys)
        remaining_files = total_files - completed_files - failed_files
        progress_percentage = ((completed_files + failed_files) / total_files) * 100 if total_files > 0 else 0

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Files", total_files)
            st.metric("✅ Completed", completed_files)
        with col2:
            st.metric("❌ Failed", failed_files)
            st.metric("⏳ Remaining", remaining_files)
        
        st.progress(progress_percentage / 100)
        st.caption(f"{progress_percentage:.1f}% Processed")

    st.divider()

    st.header("⚙️ Processing Options")
    # NEW: Checkbox to control URL fallback behavior
    include_url_fallback = st.checkbox(
        "Include entries with invalid DOIs using their URL",
        value=True,
        help="If a row has no valid DOI, use the value in the 'URL' column as a direct link."
    )

    st.divider()

    st.subheader("💾 Save Progress")
    if st.session_state.downloaded_keys or st.session_state.failed_keys:
        progress_data = {
            'downloaded_keys': list(st.session_state.downloaded_keys),
            'failed_keys': list(st.session_state.failed_keys),
            'timestamp': datetime.now().isoformat(),
            'total_files': len(st.session_state.get('current_df', [])) if 'current_df' in st.session_state else 0
        }
        st.download_button(
            label="⬇️ Download Progress File",
            data=json.dumps(progress_data, indent=2),
            file_name=f"progress_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
    else:
        st.info("No progress to save yet.")

    st.divider()

    st.subheader("📂 Load Progress")
    progress_file = st.file_uploader("Upload Progress File", type=["json"])
    if progress_file:
        try:
            progress_data = json.loads(progress_file.read())
            st.session_state.downloaded_keys.update(progress_data.get('downloaded_keys', []))
            st.session_state.failed_keys.update(progress_data.get('failed_keys', []))
            st.success("✅ Progress loaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error loading progress: {e}")

    st.divider()

    if st.button("🗑️ Clear All Progress", type="secondary", use_container_width=True):
        st.session_state.downloaded_keys.clear()
        st.session_state.failed_keys.clear()
        st.success("All progress cleared!")
        st.rerun()

# --- Main Content Area ---
uploaded_file = st.file_uploader("📄 Upload your CSV", type=["csv"])

if uploaded_file:
    try:
        df_original = pd.read_csv(uploaded_file, dtype=str).fillna('')
        st.session_state.csv_uploaded = True

        required_cols = ["Bib Key"]
        if not all(col in df_original.columns for col in required_cols):
            st.error(f"❌ CSV must contain the column: {', '.join(required_cols)}")
            st.stop()

        # --- NEW & ENHANCED PROCESSING LOGIC ---
        displayable_entries = []
        skipped_entries = []

        for index, row in df_original.iterrows():
            entry = row.to_dict()
            bib_key = entry.get("Bib Key")
            doi = get_doi_from_row(row)
            url = str(entry.get("URL", "")).strip()

            if doi:
                entry['entry_type'] = 'doi'
                entry['link'] = f"https://dl.acm.org/doi/pdf/{doi}"
                entry['doi_parsed'] = doi
                displayable_entries.append(entry)
            elif include_url_fallback and url:
                entry['entry_type'] = 'url_fallback'
                entry['link'] = url
                displayable_entries.append(entry)
            else:
                reason = "No valid DOI and no fallback URL provided." if not url else "No valid DOI (URL fallback disabled)."
                skipped_entries.append({'Bib Key': bib_key, 'Reason': reason})
        
        df = pd.DataFrame(displayable_entries)
        st.session_state.current_df = df
        
        # --- Display processing summary ---
        st.success(f"✅ Loaded {len(df_original)} total rows. Found {len(df)} displayable entries.")

        num_doi = len(df[df['entry_type'] == 'doi']) if not df.empty else 0
        num_fallback = len(df[df['entry_type'] == 'url_fallback']) if not df.empty else 0

        st.info(f"🔍 Breakdown: **{num_doi}** entries with valid DOIs, **{num_fallback}** entries using URL fallback.")

        if skipped_entries:
            st.warning(f"⚠️ {len(skipped_entries)} rows were skipped.")
            with st.expander(f"View {len(skipped_entries)} Skipped Rows"):
                st.dataframe(pd.DataFrame(skipped_entries), use_container_width=True)

        if df.empty:
            st.warning("No processable entries found in the uploaded file.")
            st.stop()

        # --- Filter items based on completion status ---
        pending_df = df[~df["Bib Key"].isin(st.session_state.downloaded_keys) & ~df["Bib Key"].isin(st.session_state.failed_keys)]
        completed_df = df[df["Bib Key"].isin(st.session_state.downloaded_keys)]
        failed_df = df[df["Bib Key"].isin(st.session_state.failed_keys)]

        pending_items = list(pending_df.to_dict('records'))

        if pending_items:
            st.subheader(f"🔄 Pending Downloads ({len(pending_items)} remaining)")
            
            for i, row in enumerate(pending_items):
                bibkey = row["Bib Key"]
                filename = f"{bibkey}.pdf"
                link_url = row["link"]
                entry_type = row["entry_type"]
                
                with st.container(border=True):
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 1.5, 1.5])
                    
                    with col1:
                        st.markdown(f"**{bibkey}**")
                        if entry_type == 'url_fallback':
                            st.caption("🔗 URL Fallback")
                        if "Title" in row and row["Title"]:
                            st.caption(f"{str(row['Title'])[:50]}...")
                    
                    with col2:
                        button_label = "🔗 Open PDF" if entry_type == 'doi' else "🔗 Open URL"
                        st.link_button(button_label, link_url, use_container_width=True)
                    
                    with col3:
                        filename_col, copy_col = st.columns([4, 1])
                        filename_col.text_input("Filename:", value=filename, key=f"filename_{i}", label_visibility="collapsed")
                        if copy_col.button("📋", key=f"copy_{i}", help="Copy filename"):
                            if copy_to_clipboard(filename, f"copy_{i}"):
                                st.toast(f"✅ Copied: {filename}")
                    
                    with col4:
                        if st.button("✅ Done", key=f"done_{i}", type="primary", use_container_width=True):
                            st.session_state.downloaded_keys.add(bibkey)
                            st.rerun()
                    
                    with col5:
                        if st.button("❌ Failed", key=f"failed_{i}", type="secondary", use_container_width=True):
                            st.session_state.failed_keys.add(bibkey)
                            st.rerun()

        else:
            st.success("🎉 All items have been processed! Check the sections below.")
        
        # --- Completed and Failed sections ---
        if not completed_df.empty:
            with st.expander(f"✅ Completed Downloads ({len(completed_df)} files)", expanded=False):
                for i, row in completed_df.iterrows():
                    col1, col2, col3 = st.columns([3, 4, 1.5])
                    col1.markdown(f"**✅ {row['Bib Key']}**")
                    col2.markdown(f"~~`{row['Bib Key']}.pdf`~~")
                    if col3.button("↩️ Undo", key=f"undo_{i}"):
                        st.session_state.downloaded_keys.discard(row['Bib Key'])
                        st.rerun()

        if not failed_df.empty:
            with st.expander(f"❌ Failed Items ({len(failed_df)} files)", expanded=True):
                for i, row in failed_df.iterrows():
                    col1, col2, col3 = st.columns([3, 4, 1.5])
                    col1.markdown(f"**❌ {row['Bib Key']}**")
                    col2.markdown(f"*{row.get('Title', 'No Title')}*")
                    if col3.button("🔄 Retry", key=f"retry_{i}"):
                        st.session_state.failed_keys.discard(row['Bib Key'])
                        st.rerun()
        
        # --- ZIP creation section ---
        if st.session_state.downloaded_keys:
            with st.expander("📦 Create ZIP from Downloaded Files"):
                zip_folder = st.text_input("📁 Folder path with renamed PDFs:")
                zip_name = st.text_input("📋 ZIP filename:", value=f"papers_{datetime.now().strftime('%Y%m%d')}.zip")
                
                if st.button("📁 Create ZIP File", type="primary"):
                    if not zip_folder or not os.path.isdir(zip_folder):
                        st.error("❌ Please provide a valid folder path.")
                    else:
                        zip_path = os.path.join(zip_folder, zip_name)
                        found_files, missing_files = 0, []
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for bibkey in st.session_state.downloaded_keys:
                                pdf_path = os.path.join(zip_folder, f"{bibkey}.pdf")
                                if os.path.exists(pdf_path):
                                    zipf.write(pdf_path, arcname=f"{bibkey}.pdf")
                                    found_files += 1
                                else:
                                    missing_files.append(f"{bibkey}.pdf")
                        
                        st.success(f"🎉 ZIP created at `{zip_path}` with {found_files} files.")
                        if missing_files:
                            st.warning(f"⚠️ Could not find {len(missing_files)} files: {', '.join(missing_files[:5])}...")

    except Exception as e:
        st.error(f"❌ An error occurred while processing the file: {e}")
        st.info("Please ensure your CSV is correctly formatted and UTF-8 encoded.")

# --- Footer and Instructions ---
st.markdown("---")
st.markdown("""
### 📝 How to Use This App
1.  **Configure Options**: Use the sidebar to enable URL fallbacks if needed.
2.  **Upload CSV**: Provide a CSV with `Bib Key`, `DOI`, and/or `URL` columns.
3.  **Process List**:
    - Click **Open PDF/URL** to view the paper.
    - Click **📋** to copy the correct filename (`Bib Key.pdf`).
    - Download and rename the file.
    - Click **✅ Done** to mark as complete or **❌ Failed** for broken links.
4.  **Manage Progress**: Use the sidebar to save your progress for later or load a previous session.
""")