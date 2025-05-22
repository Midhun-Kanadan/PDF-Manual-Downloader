import streamlit as st
import pandas as pd
import urllib.parse
import os
import zipfile
import json
from datetime import datetime
import pyperclip
import time

st.set_page_config(page_title="PDF Downloader", layout="wide")
st.title("📄 PDF Manual Downloader")

# st.markdown("""
# Upload a CSV file with the following columns:
# - `DOI` (preferred) or `URL`
# - `Bib Key`

# For each entry, you'll get:
# - A direct link to open/download the PDF
# - The correct filename to rename the file after download
# - A one-click copy button for the filename
# - A checkbox to mark as downloaded
# """)

# Initialize session state for persistence
if 'downloaded_keys' not in st.session_state:
    st.session_state.downloaded_keys = set()
if 'failed_keys' not in st.session_state:
    st.session_state.failed_keys = set()
if 'csv_uploaded' not in st.session_state:
    st.session_state.csv_uploaded = False

# Progress management in sidebar
with st.sidebar:
    st.header("📊 Progress Management")
    
    # Show current progress if CSV is loaded
    if 'current_df' in st.session_state and st.session_state.csv_uploaded:
        total_files = len(st.session_state.current_df)
        completed_files = len(st.session_state.downloaded_keys)
        failed_files = len(st.session_state.failed_keys)
        remaining_files = total_files - completed_files - failed_files
        progress_percentage = ((completed_files + failed_files) / total_files) * 100 if total_files > 0 else 0
        
        # Progress metrics with color coding
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Files", total_files)
            st.metric("✅ Completed", completed_files, delta=None if completed_files == 0 else f"+{completed_files}")
        with col2:
            st.metric("❌ Failed", failed_files, delta=None if failed_files == 0 else f"+{failed_files}")
            st.metric("⏳ Remaining", remaining_files, delta=None if remaining_files == total_files else f"-{completed_files + failed_files}")
        
        # Enhanced progress bar
        progress_bar = st.progress(progress_percentage / 100)
        st.caption(f"{progress_percentage:.1f}% Processed ({completed_files} completed, {failed_files} failed)")
        
        # Time estimation (rough)
        if (completed_files + failed_files) > 0 and remaining_files > 0:
            avg_time_per_file = 2  # Assume 2 minutes per file
            estimated_time = remaining_files * avg_time_per_file
            st.caption(f"⏱️ Est. {estimated_time} min remaining")
        
        st.divider()
    

    
    # Save progress
    st.subheader("💾 Save Progress")
    if st.session_state.downloaded_keys or st.session_state.failed_keys:
        progress_data = {
            'downloaded_keys': list(st.session_state.downloaded_keys),
            'failed_keys': list(st.session_state.failed_keys),
            'timestamp': datetime.now().isoformat(),
            'total_files': len(st.session_state.get('current_df', [])) if 'current_df' in st.session_state else 0
        }
        
        progress_json = json.dumps(progress_data, indent=2)
        st.download_button(
            label="⬇️ Download Progress File",
            data=progress_json,
            file_name=f"acm_progress_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
            help=f"Save progress: {len(st.session_state.downloaded_keys)} completed, {len(st.session_state.failed_keys)} failed"
        )
    else:
        st.info("No progress to save yet")
    
    st.divider()
    
    # Load progress with better feedback
    st.subheader("📂 Load Progress")
    st.info("💡 Upload a previously saved progress file to resume where you left off")
    progress_file = st.file_uploader("Upload Progress File", type=["json"], help="Upload a previously saved progress file")
    
    if progress_file:
        try:
            progress_data = json.loads(progress_file.read())
            loaded_downloaded = set(progress_data.get('downloaded_keys', []))
            loaded_failed = set(progress_data.get('failed_keys', []))
            
            # Show what was loaded
            st.write("**Progress file contents:**")
            st.write(f"- Timestamp: {progress_data.get('timestamp', 'Unknown')}")
            st.write(f"- Total files in progress: {progress_data.get('total_files', 'Unknown')}")
            st.write(f"- Completed files: {len(loaded_downloaded)}")
            st.write(f"- Failed files: {len(loaded_failed)}")
            
            # Calculate new additions
            old_downloaded = len(st.session_state.downloaded_keys)
            old_failed = len(st.session_state.failed_keys)
            before_downloaded = st.session_state.downloaded_keys.copy()
            before_failed = st.session_state.failed_keys.copy()
            
            # Merge with existing progress
            st.session_state.downloaded_keys.update(loaded_downloaded)
            st.session_state.failed_keys.update(loaded_failed)
            
            new_downloaded = len(st.session_state.downloaded_keys) - old_downloaded
            new_failed = len(st.session_state.failed_keys) - old_failed
            
            if new_downloaded > 0 or new_failed > 0:
                st.success(f"✅ Added {new_downloaded} completed and {new_failed} failed files to your progress")
                
                # Show which files were added
                added_downloaded = loaded_downloaded - before_downloaded
                added_failed = loaded_failed - before_failed
                
                if added_downloaded and len(added_downloaded) <= 5:
                    st.write("**Newly added completed files:**")
                    for file in sorted(added_downloaded):
                        st.write(f"• ✅ {file}")
                
                if added_failed and len(added_failed) <= 5:
                    st.write("**Newly added failed files:**")
                    for file in sorted(added_failed):
                        st.write(f"• ❌ {file}")
                        
                st.rerun()
            elif len(loaded_downloaded) > 0 or len(loaded_failed) > 0:
                st.info(f"ℹ️ Progress file loaded, but all files were already in your current progress")
            else:
                st.warning("⚠️ No progress data found in the file")
                
        except Exception as e:
            st.error(f"❌ Error loading progress: {str(e)}")
            st.error("Make sure you're uploading a valid progress file saved from this app")
    
    st.divider()
    
    # Clear progress
    if st.button("🗑️ Clear All Progress", type="secondary", use_container_width=True):
        st.session_state.downloaded_keys.clear()
        st.session_state.failed_keys.clear()
        st.success("All progress cleared!")
        st.rerun()

# Main content area
uploaded_file = st.file_uploader("📄 Upload your ACM CSV", type=["csv"])

def copy_to_clipboard(text, key):
    """Helper function to copy text to clipboard"""
    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        st.error(f"Failed to copy to clipboard: {str(e)}")
        return False

def get_doi(row):
    """Extract DOI from row data"""
    if pd.notna(row.get("DOI")):
        return str(row["DOI"]).strip()
    if pd.notna(row.get("URL")) and "doi.org" in row["URL"]:
        return str(urllib.parse.urlparse(row["URL"]).path).strip("/")
    return None

if uploaded_file:
    try:
        df = pd.read_csv(uploaded_file)
        st.session_state.current_df = df
        st.session_state.csv_uploaded = True

        # Validate required columns
        required_cols = ["Bib Key"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"❌ CSV must contain the following columns: {', '.join(missing_cols)}")
            st.info("Available columns: " + ", ".join(df.columns.tolist()))
            st.stop()

        # Process DOIs
        df["DOI_Parsed"] = df.apply(get_doi, axis=1)
        
        # Show statistics about DOI parsing
        total_rows = len(df)
        valid_dois = df["DOI_Parsed"].notna().sum()
        invalid_dois = total_rows - valid_dois
        
        if invalid_dois > 0:
            st.warning(f"⚠️ {invalid_dois} rows have no valid DOI and will be skipped")
            if st.checkbox("Show invalid rows"):
                invalid_df = df[df["DOI_Parsed"].isna()][["Bib Key", "DOI", "URL"] if "URL" in df.columns else ["Bib Key", "DOI"]]
                st.dataframe(invalid_df, use_container_width=True)
        
        df = df[df["DOI_Parsed"].notna()]  # Keep only rows with usable DOIs
        st.session_state.current_df = df  # Update with filtered data

        st.success(f"✅ Loaded {len(df)} entries with valid DOIs")

        # Filter items based on completion status (show only pending)
        pending_df = df[~df["Bib Key"].isin(st.session_state.downloaded_keys) & ~df["Bib Key"].isin(st.session_state.failed_keys)]
        completed_df = df[df["Bib Key"].isin(st.session_state.downloaded_keys)]
        failed_df = df[df["Bib Key"].isin(st.session_state.failed_keys)]
        
        # Show only pending items (completed/failed items automatically hidden)
        pending_items = [(i, row) for i, row in pending_df.iterrows()]
        completed_items = [(i, row) for i, row in completed_df.iterrows()]
        failed_items = [(i, row) for i, row in failed_df.iterrows()]

        if pending_items:
            st.subheader(f"🔄 Pending Downloads ({len(pending_items)} remaining)")
            
            # Option to show items in batches
            batch_size = st.selectbox("Items per page:", [10, 20, 50, 100], index=1, key="batch_size")
            total_pages = (len(pending_items) + batch_size - 1) // batch_size
            
            if total_pages > 1:
                page = st.selectbox(f"Page (1-{total_pages}):", range(1, total_pages + 1), key="page_selector") - 1
                start_idx = page * batch_size
                end_idx = min(start_idx + batch_size, len(pending_items))
                page_items = pending_items[start_idx:end_idx]
                st.caption(f"Showing items {start_idx + 1}-{end_idx} of {len(pending_items)}")
            else:
                page_items = pending_items
            
            for i, row in page_items:
                bibkey = row["Bib Key"]
                doi_suffix = row["DOI_Parsed"]
                pdf_url = f"https://dl.acm.org/doi/pdf/{doi_suffix}"
                filename = f"{bibkey}.pdf"

                with st.container():
                    # Enhanced layout with better spacing
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 1.5, 1.5])
                    
                    with col1:
                        st.markdown(f"**{bibkey}**")
                        # Show additional info if available
                        if "Title" in row and pd.notna(row["Title"]):
                            st.caption(f"{str(row['Title'])[:50]}...")
                    
                    with col2:
                        st.link_button("🔗 Open PDF", pdf_url, use_container_width=True)
                    
                    with col3:
                        # Use columns for filename display and copy
                        filename_col, copy_col = st.columns([4, 1])
                        with filename_col:
                            st.text_input(
                                "Filename:",
                                value=filename,
                                key=f"filename_{i}",
                                help="Select text and Ctrl+C to copy manually",
                                label_visibility="collapsed"
                            )
                        with copy_col:
                            # Copy button with actual functionality
                            if st.button("📋", key=f"copy_{i}", help="Copy filename to clipboard"):
                                if copy_to_clipboard(filename, f"copy_{i}"):
                                    st.success("✅ Copied!")
                                    time.sleep(0.5)  # Brief pause to show success
                                    st.rerun()
                    
                    with col4:
                        # Interactive Done button with state management
                        if st.button("✅ Done", key=f"done_{i}", type="primary", use_container_width=True):
                            st.session_state.downloaded_keys.add(bibkey)
                            st.success(f"✓ {bibkey} marked as completed")
                            time.sleep(0.3)
                            st.rerun()
                    
                    with col5:
                        # Failed button for tracking failed downloads
                        if st.button("❌ Failed", key=f"failed_{i}", type="secondary", use_container_width=True):
                            st.session_state.failed_keys.add(bibkey)
                            st.warning(f"⚠ {bibkey} marked as failed")
                            time.sleep(0.3)
                            st.rerun()
                    
                    st.divider()
        
        # Show completed items in a collapsible section
        if completed_items:
            with st.expander(f"✅ Completed Downloads ({len(completed_items)} files)", expanded=False):
                for i, row in completed_items:
                    bibkey = row["Bib Key"]
                    filename = f"{bibkey}.pdf"
                    
                    col1, col2, col3 = st.columns([3, 4, 1.5])
                    
                    with col1:
                        st.markdown(f"**✅ {bibkey}**")
                    
                    with col2:
                        st.markdown(f"~~`{filename}`~~ *(completed)*")
                    
                    with col3:
                        if st.button("↩️ Undo", key=f"undo_{i}", help="Mark as not done"):
                            st.session_state.downloaded_keys.discard(bibkey)
                            st.toast(f"↩️ Unmarked {bibkey}")
                            st.rerun()

        # Summary section
        total_count = len(df)
        completed_count = len(st.session_state.downloaded_keys & set(df["Bib Key"]))
        failed_count = len(st.session_state.failed_keys & set(df["Bib Key"]))
        
        if completed_count > 0 or failed_count > 0:
            processed_count = completed_count + failed_count
            progress_pct = (processed_count / total_count) * 100
            st.success(f"📊 Progress: {processed_count}/{total_count} processed ({progress_pct:.1f}%) - {completed_count} completed, {failed_count} failed")
            
            # Completion celebration (professional)
            if processed_count == total_count and total_count > 0:
                st.success("🎯 All files processed!")
                if completed_count == total_count:
                    st.info("Perfect! All files downloaded successfully. You can now create a ZIP file below.")
                else:
                    st.info(f"Processing complete: {completed_count} successful, {failed_count} failed. Check the failed section to retry problematic downloads.")

        # ZIP creation section (enhanced)
        if st.session_state.downloaded_keys:
            with st.expander("📦 Create ZIP from Downloaded Files"):
                st.info("After downloading and renaming your PDFs, create a ZIP file containing all completed files.")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    zip_folder = st.text_input(
                        "📁 Folder path with renamed PDFs:",
                        placeholder="C:\\Downloads\\PDFs or /home/user/pdfs",
                        help="Enter the full path to the folder containing your renamed PDF files"
                    )
                
                with col2:
                    zip_name = st.text_input(
                        "📋 ZIP filename:",
                        value=f"acm_papers_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                        help="Name for the ZIP file to be created"
                    )
                
                # Preview what will be included
                if zip_folder and os.path.isdir(zip_folder):
                    st.caption("Files to include:")
                    preview_files = []
                    for bibkey in list(st.session_state.downloaded_keys)[:5]:  # Show first 5
                        pdf_filename = f"{bibkey}.pdf"
                        pdf_path = os.path.join(zip_folder, pdf_filename)
                        status = "✅" if os.path.exists(pdf_path) else "❌"
                        preview_files.append(f"{status} {pdf_filename}")
                    
                    st.code("\n".join(preview_files))
                    if len(st.session_state.downloaded_keys) > 5:
                        st.caption(f"... and {len(st.session_state.downloaded_keys) - 5} more files")
                
                if st.button("📁 Create ZIP File", type="secondary"):
                    if not zip_folder:
                        st.error("❌ Please enter a folder path")
                    elif not os.path.isdir(zip_folder):
                        st.error("❌ Folder path does not exist")
                    else:
                        try:
                            zip_path = os.path.join(zip_folder, zip_name)
                            found_files = 0
                            missing_files = []
                            
                            with st.spinner("Creating ZIP file..."):
                                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                    for bibkey in st.session_state.downloaded_keys:
                                        pdf_filename = f"{bibkey}.pdf"
                                        pdf_path = os.path.join(zip_folder, pdf_filename)
                                        
                                        if os.path.exists(pdf_path):
                                            zipf.write(pdf_path, arcname=pdf_filename)
                                            found_files += 1
                                        else:
                                            missing_files.append(pdf_filename)
                            
                            if found_files > 0:
                                st.success(f"🎉 ZIP created successfully!")
                                file_size = os.path.getsize(zip_path) / (1024 * 1024)  # Size in MB
                                st.info(f"📊 Added {found_files} files ({file_size:.1f} MB): `{zip_path}`")
                                
                                if missing_files:
                                    st.warning(f"⚠️ {len(missing_files)} files not found:")
                                    for missing in missing_files[:10]:  # Show first 10
                                        st.caption(f"• {missing}")
                                    if len(missing_files) > 10:
                                        st.caption(f"• ... and {len(missing_files) - 10} more")
                            else:
                                st.error("❌ No PDF files found in the specified folder")
                                
                        except Exception as e:
                            st.error(f"❌ Error creating ZIP: {str(e)}")

    except Exception as e:
        st.error(f"❌ Error reading CSV file: {str(e)}")
        st.info("Please make sure your CSV file is properly formatted.")

elif st.session_state.csv_uploaded and 'current_df' in st.session_state:
    # Show progress even when CSV is not currently uploaded but was before
    st.info("📁 CSV file was loaded previously. Upload again to continue or manage your progress in the sidebar.")
    
    if st.session_state.downloaded_keys or st.session_state.failed_keys:
        st.success(f"💾 Saved progress: {len(st.session_state.downloaded_keys)} completed, {len(st.session_state.failed_keys)} failed")

# Footer with instructions
st.markdown("---")
st.markdown("""
### 📝 How to Use This App:

#### **Step 1: Upload Your CSV**
- Your CSV should have columns: `DOI` (or `URL`) and `Bib Key`
- The app will show only papers with valid DOIs

#### **Step 2: Download PDFs**
1. **Click PDF links** to open papers in new browser tabs
2. **Copy filenames** using the 📋 button (copies to clipboard automatically)
3. **Download PDFs** from the opened tabs  
4. **Rename downloaded files** using the copied filenames
5. **Mark as Done** ✅ - successfully downloaded items disappear from the main list
6. **Mark as Failed** ❌ - for broken links or inaccessible papers (also disappear from main list)

#### **Step 3: Save Your Progress**
- **Save Progress**: Download a progress file anytime to backup your work (includes both completed and failed items)
- **Load Progress**: Upload a saved progress file to resume later
- **Use Case**: Perfect for large batches that take multiple sessions


""")

# # Add progress explanation
# st.markdown("""
# ---
# ### 🔄 Understanding Progress Files

# **What is a Progress File?**
# - A small JSON file that remembers which papers you've downloaded AND which ones failed
# - Contains: completed Bib Keys, failed Bib Keys, timestamp, and total count
# - Does NOT contain actual PDFs (just the completion and failure status)

# **When to Use Progress Files:**
# - **Large batches**: When working with 50+ papers across multiple sessions  
# - **Collaboration**: Share progress with team members working on the same batch
# - **Backup**: Save your work before closing the browser
# - **Resume later**: Continue where you left off in a new session
# - **Failed tracking**: Keep track of problematic papers that need attention

# **How Progress Files Work:**
# 1. **Save**: Downloads a small JSON file with your current progress (completed + failed)
# 2. **Load**: Upload the JSON file to restore your completion and failure status
# 3. **Merge**: Loading progress adds to (doesn't replace) your current progress
# """)

st.markdown("""
*Tip: Progress files are lightweight (few KB) and safe to share - they contain no actual content, just completion and failure tracking!*
""")

# Custom CSS for better styling and theme adaptation
st.markdown("""
<style>
/* Theme-adaptive text input styling */
.stTextInput > div > div > input {
    font-family: 'Courier New', monospace;
    font-size: 12px;
    border: 1px solid var(--text-color-light);
    border-radius: 4px;
    padding: 8px;
}

/* Dark mode adaptations */
@media (prefers-color-scheme: dark) {
    .stTextInput > div > div > input {
        background-color: #262730;
        color: #fafafa;
        border-color: #4a4a4a;
    }
    
    .stTextInput > div > div > input:focus {
        background-color: #1e1e1e;
        border-color: #0078d4;
        color: #ffffff;
    }
}

/* Light mode adaptations */
@media (prefers-color-scheme: light) {
    .stTextInput > div > div > input {
        background-color: #ffffff;
        color: #262626;
        border-color: #d0d0d0;
    }
    
    .stTextInput > div > div > input:focus {
        background-color: #f8f9fa;
        border-color: #2196f3;
        color: #000000;
    }
}

/* Streamlit's built-in dark mode override */
[data-theme="dark"] .stTextInput > div > div > input {
    background-color: #262730 !important;
    color: #fafafa !important;
    border-color: #4a4a4a !important;
}

[data-theme="dark"] .stTextInput > div > div > input:focus {
    background-color: #1e1e1e !important;
    border-color: #0078d4 !important;
    color: #ffffff !important;
}

[data-theme="light"] .stTextInput > div > div > input {
    background-color: #ffffff !important;
    color: #262626 !important;
    border-color: #d0d0d0 !important;
}

[data-theme="light"] .stTextInput > div > div > input:focus {
    background-color: #f8f9fa !important;
    border-color: #2196f3 !important;
    color: #000000 !important;
}

/* Enhanced button styling */
.stButton > button {
    height: 2.5rem;
    padding: 0.25rem 0.75rem;
    border-radius: 6px;
    transition: all 0.2s ease;
}

/* Copy button specific styling */
.stButton > button[kind="secondary"] {
    border: 1px solid #ccc;
}

[data-theme="dark"] .stButton > button[kind="secondary"] {
    border: 1px solid #4a4a4a;
    background-color: #262730;
}

/* Progress bar styling */
.stProgress > div > div > div {
    background-color: #4caf50;
    transition: width 0.3s ease;
}

/* Expandable sections */
div[data-testid="stExpander"] > div > div > div > div {
    border-radius: 6px;
}

[data-theme="dark"] div[data-testid="stExpander"] > div > div > div > div {
    background-color: #1e1e1e;
}

[data-theme="light"] div[data-testid="stExpander"] > div > div > div > div {
    background-color: #f8f9fa;
}

/* Improve container spacing */
.stContainer > div {
    gap: 0.5rem;
}

/* Success/completion styling */
.completion-success {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 6px;
    padding: 8px;
    margin: 4px 0;
}

[data-theme="dark"] .completion-success {
    background-color: #1d4428;
    border-color: #2d5a35;
}

/* Interactive button hover effects */
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

[data-theme="dark"] .stButton > button:hover {
    box-shadow: 0 2px 4px rgba(255,255,255,0.1);
}

/* Toast-like notifications */
.copy-notification {
    position: fixed;
    top: 20px;
    right: 20px;
    background-color: #4caf50;
    color: white;
    padding: 10px 20px;
    border-radius: 6px;
    z-index: 1000;
    animation: slideIn 0.3s ease;
}

@keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
}
</style>
""", unsafe_allow_html=True)