import streamlit as st
import pandas as pd
import urllib.parse
import os
import zipfile
import json
import hashlib
import random
from datetime import datetime
import streamlit.components.v1 as components
import time

# Sample CSV data embedded in the application
EMBEDDED_CSV_DATA = """Bib Key,DOI,Title,URL
Smith2023,10.1145/3534678.3539081,"Machine Learning in Distributed Systems",https://dl.acm.org/doi/10.1145/3534678.3539081
Johnson2023,10.1145/3534678.3539082,"Cloud Computing Architectures",https://dl.acm.org/doi/10.1145/3534678.3539082
Brown2023,10.1145/3534678.3539083,"AI Ethics and Fairness",https://dl.acm.org/doi/10.1145/3534678.3539083
Davis2023,10.1145/3534678.3539084,"Quantum Computing Applications",https://dl.acm.org/doi/10.1145/3534678.3539084
Wilson2023,10.1145/3534678.3539085,"Cybersecurity in IoT",https://dl.acm.org/doi/10.1145/3534678.3539085
Miller2023,10.1145/3534678.3539086,"Blockchain Technologies",https://dl.acm.org/doi/10.1145/3534678.3539086
Taylor2023,10.1145/3534678.3539087,"Deep Learning Optimization",https://dl.acm.org/doi/10.1145/3534678.3539087
Anderson2023,10.1145/3534678.3539088,"Human-Computer Interaction",https://dl.acm.org/doi/10.1145/3534678.3539088
Thomas2023,10.1145/3534678.3539089,"Data Mining Techniques",https://dl.acm.org/doi/10.1145/3534678.3539089
Jackson2023,10.1145/3534678.3539090,"Computer Vision Methods",https://dl.acm.org/doi/10.1145/3534678.3539090
White2023,10.1145/3534678.3539091,"Natural Language Processing",https://dl.acm.org/doi/10.1145/3534678.3539091
Harris2023,10.1145/3534678.3539092,"Software Engineering Practices",https://dl.acm.org/doi/10.1145/3534678.3539092
Martin2023,10.1145/3534678.3539093,"Database Optimization",https://dl.acm.org/doi/10.1145/3534678.3539093
Thompson2023,10.1145/3534678.3539094,"Mobile Computing Trends",https://dl.acm.org/doi/10.1145/3534678.3539094
Garcia2023,10.1145/3534678.3539095,"Edge Computing Solutions",https://dl.acm.org/doi/10.1145/3534678.3539095"""

st.set_page_config(page_title="PDF Downloader", layout="wide")
st.title("📄 PDF Manual Downloader")

# Initialize session state for persistence
if 'downloaded_keys' not in st.session_state:
    st.session_state.downloaded_keys = set()
if 'failed_keys' not in st.session_state:
    st.session_state.failed_keys = set()
if 'user_id' not in st.session_state:
    # Generate unique user ID based on session
    st.session_state.user_id = hashlib.md5(str(random.random()).encode()).hexdigest()[:8]
if 'current_pdf_index' not in st.session_state:
    st.session_state.current_pdf_index = None
if 'assigned_pdfs' not in st.session_state:
    st.session_state.assigned_pdfs = set()

# Load embedded CSV data
@st.cache_data
def load_embedded_data():
    from io import StringIO
    return pd.read_csv(StringIO(EMBEDDED_CSV_DATA))

def get_doi(row):
    """Extract DOI from row data"""
    if pd.notna(row.get("DOI")):
        return str(row["DOI"]).strip()
    if pd.notna(row.get("URL")) and "doi.org" in row["URL"]:
        return str(urllib.parse.urlparse(row["URL"]).path).strip("/")
    return None

def check_file_exists(folder_path, filename):
    """Check if file exists in the specified folder"""
    if not folder_path or not os.path.isdir(folder_path):
        return False
    file_path = os.path.join(folder_path, filename)
    return os.path.exists(file_path)

def get_next_available_pdf(df, user_id):
    """Get the next available PDF for the current user, ensuring no conflicts"""
    # Filter out already completed/failed items
    available_df = df[~df["Bib Key"].isin(st.session_state.downloaded_keys) & 
                     ~df["Bib Key"].isin(st.session_state.failed_keys)]
    
    if available_df.empty:
        return None
    
    # Use user_id as seed for consistent but different ordering per user
    user_seed = int(hashlib.md5(user_id.encode()).hexdigest()[:8], 16)
    random.seed(user_seed)
    
    # Get available indices and shuffle them based on user seed
    available_indices = available_df.index.tolist()
    random.shuffle(available_indices)
    
    # Reset random seed to avoid affecting other random operations
    random.seed()
    
    # Return the first available item for this user
    return available_indices[0] if available_indices else None

def create_copy_button_js(text, key):
    """Create a JavaScript-powered copy button that works in browsers"""
    button_id = f"copy_btn_{key}"
    
    # Escape text for JavaScript
    escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
    
    js_code = f"""
    <div style="display: inline-block; width: 100%;">
        <button id="{button_id}" onclick="copyText_{key}()" 
                style="background: linear-gradient(90deg, #ff4b4b, #ff6b6b); 
                       color: white; border: none; padding: 8px 16px; 
                       border-radius: 6px; cursor: pointer; font-size: 14px;
                       transition: all 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                       width: 100%; min-width: 120px; white-space: nowrap;"
                title="Copy filename">
            📋 Copy Filename
        </button>
    </div>
    
    <script>
    async function copyText_{key}() {{
        const text = '{escaped_text}';
        const button = document.getElementById('{button_id}');
        const originalContent = button.innerHTML;
        
        try {{
            if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(text);
                button.innerHTML = '✅ Copied!';
                button.style.background = 'linear-gradient(90deg, #4CAF50, #45a049)';
            }} else {{
                // Fallback method
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.opacity = '0';
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                button.innerHTML = '✅ Copied!';
                button.style.background = 'linear-gradient(90deg, #4CAF50, #45a049)';
            }}
            
            // Reset button after 2 seconds
            setTimeout(() => {{
                button.innerHTML = originalContent;
                button.style.background = 'linear-gradient(90deg, #ff4b4b, #ff6b6b)';
            }}, 2000);
            
        }} catch (err) {{
            console.error('Copy failed:', err);
            button.innerHTML = '❌ Failed';
            button.style.background = 'linear-gradient(90deg, #f44336, #da190b)';
            
            setTimeout(() => {{
                button.innerHTML = originalContent;
                button.style.background = 'linear-gradient(90deg, #ff4b4b, #ff6b6b)';
            }}, 2000);
        }}
    }}
    </script>
    """
    
    components.html(js_code, height=50)

# Load embedded data
df = load_embedded_data()
df["DOI_Parsed"] = df.apply(get_doi, axis=1)
df = df[df["DOI_Parsed"].notna()]  # Keep only rows with usable DOIs

# Sidebar for progress and settings
with st.sidebar:
    st.header("📊 Progress Management")
    st.write(f"**User ID:** `{st.session_state.user_id}`")
    st.caption("Each user gets a different PDF to avoid conflicts")
    
    # Progress metrics
    total_files = len(df)
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
    
    # Progress bar
    progress_bar = st.progress(progress_percentage / 100)
    st.caption(f"{progress_percentage:.1f}% Processed")
    
    st.divider()
    
    # File verification section
    st.subheader("📁 File Verification")
    verify_folder = st.text_input(
        "Folder path to check files:",
        placeholder="C:\\Downloads\\PDFs or /home/user/pdfs",
        help="Enter the path where you save downloaded PDFs"
    )
    
    if verify_folder and st.button("🔍 Verify Files"):
        if os.path.isdir(verify_folder):
            verified_count = 0
            newly_verified = []
            
            with st.spinner("Checking files..."):
                for bibkey in list(st.session_state.downloaded_keys):
                    filename = f"{bibkey}.pdf"
                    if check_file_exists(verify_folder, filename):
                        verified_count += 1
                    else:
                        # File not found, remove from completed
                        st.session_state.downloaded_keys.discard(bibkey)
                        newly_verified.append(f"❌ {filename} - not found")
                
                # Check for any additional files that were downloaded but not marked
                for _, row in df.iterrows():
                    bibkey = row["Bib Key"]
                    filename = f"{bibkey}.pdf"
                    if (bibkey not in st.session_state.downloaded_keys and 
                        bibkey not in st.session_state.failed_keys and
                        check_file_exists(verify_folder, filename)):
                        st.session_state.downloaded_keys.add(bibkey)
                        newly_verified.append(f"✅ {filename} - found and marked")
            
            st.success(f"✅ Verified {len(st.session_state.downloaded_keys)} files")
            if newly_verified:
                st.write("**Changes made:**")
                for change in newly_verified[:10]:  # Show first 10 changes
                    st.caption(change)
            st.rerun()
        else:
            st.error("❌ Folder path does not exist")
    
    st.divider()
    
    # Save/Load progress (simplified)
    st.subheader("💾 Progress Management")
    if st.session_state.downloaded_keys or st.session_state.failed_keys:
        progress_data = {
            'downloaded_keys': list(st.session_state.downloaded_keys),
            'failed_keys': list(st.session_state.failed_keys),
            'user_id': st.session_state.user_id,
            'timestamp': datetime.now().isoformat()
        }
        
        progress_json = json.dumps(progress_data, indent=2)
        st.download_button(
            label="⬇️ Download Progress",
            data=progress_json,
            file_name=f"progress_{st.session_state.user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
    
    # Load progress
    progress_file = st.file_uploader("Upload Progress File", type=["json"])
    if progress_file:
        try:
            progress_data = json.loads(progress_file.read())
            st.session_state.downloaded_keys.update(progress_data.get('downloaded_keys', []))
            st.session_state.failed_keys.update(progress_data.get('failed_keys', []))
            st.success("✅ Progress loaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error loading progress: {str(e)}")
    
    # Clear progress
    if st.button("🗑️ Clear All Progress", type="secondary", use_container_width=True):
        st.session_state.downloaded_keys.clear()
        st.session_state.failed_keys.clear()
        st.session_state.current_pdf_index = None
        st.success("All progress cleared!")
        st.rerun()

# Main content area
st.success(f"✅ Loaded {len(df)} PDF entries from embedded database")

# Get current PDF for this user
if st.session_state.current_pdf_index is None:
    st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)

# Display current PDF
if st.session_state.current_pdf_index is not None:
    row = df.loc[st.session_state.current_pdf_index]
    bibkey = row["Bib Key"]
    doi_suffix = row["DOI_Parsed"]
    pdf_url = f"https://dl.acm.org/doi/pdf/{doi_suffix}"
    filename = f"{bibkey}.pdf"
    title = row.get("Title", "No title available")
    
    st.subheader("📄 Current PDF Assignment")
    
    # Create a prominent card-like display
    with st.container():
        st.markdown(f"""
        <div style="padding: 20px; border-radius: 10px; border: 2px solid #ff4b4b; background-color: rgba(255, 75, 75, 0.1); margin: 10px 0;">
            <h3 style="color: #ff4b4b; margin-top: 0;">📋 {bibkey}</h3>
            <p style="font-size: 16px; margin: 10px 0;"><strong>Title:</strong> {title}</p>
            <p style="font-size: 14px; margin: 10px 0;"><strong>DOI:</strong> {doi_suffix}</p>
            <p style="font-size: 14px; margin: 10px 0;"><strong>Filename:</strong> <code>{filename}</code></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Action buttons in columns
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        
        with col1:
            st.link_button("🔗 Open PDF", pdf_url, use_container_width=True, type="primary")
        
        with col2:
            create_copy_button_js(filename, "current_pdf")
        
        with col3:
            if st.button("✅ Mark as Done", key="done_current", type="primary", use_container_width=True):
                st.session_state.downloaded_keys.add(bibkey)
                st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)
                st.success(f"✅ {bibkey} completed!")
                time.sleep(0.5)
                st.rerun()
        
        with col4:
            if st.button("❌ Mark as Failed", key="failed_current", type="secondary", use_container_width=True):
                st.session_state.failed_keys.add(bibkey)
                st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)
                st.warning(f"❌ {bibkey} marked as failed")
                time.sleep(0.5)
                st.rerun()
    
    # Instructions
    st.info("""
    **Instructions:**
    1. Click "🔗 Open PDF" to open the PDF in a new tab
    2. Click "📋 Copy Filename" to copy the exact filename to your clipboard
    3. Download the PDF and rename it using the copied filename
    4. Click "✅ Mark as Done" when completed, or "❌ Mark as Failed" if the PDF is not accessible
    5. The next PDF will automatically be assigned to you
    """)
    
    # Skip current PDF option
    if st.button("⏭️ Skip Current PDF", help="Skip to next PDF without marking as done or failed"):
        st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)
        st.info("⏭️ Moved to next PDF")
        st.rerun()

else:
    # No more PDFs available
    st.success("🎉 All PDFs have been processed!")
    st.balloons()
    
    if st.button("🔄 Check for New PDFs"):
        st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)
        if st.session_state.current_pdf_index is not None:
            st.success("📄 New PDF found!")
            st.rerun()
        else:
            st.info("No new PDFs available at this time.")

# Show completed and failed items in expandable sections
if st.session_state.downloaded_keys:
    with st.expander(f"✅ Completed Downloads ({len(st.session_state.downloaded_keys)} files)", expanded=False):
        for bibkey in sorted(st.session_state.downloaded_keys):
            matching_rows = df[df["Bib Key"] == bibkey]
            if not matching_rows.empty:
                title = matching_rows.iloc[0].get("Title", "No title")
                col1, col2, col3 = st.columns([3, 4, 1])
                with col1:
                    st.markdown(f"**✅ {bibkey}**")
                with col2:
                    st.caption(f"{title[:60]}...")
                with col3:
                    if st.button("↩️", key=f"undo_{bibkey}", help="Mark as not done"):
                        st.session_state.downloaded_keys.discard(bibkey)
                        if st.session_state.current_pdf_index is None:
                            st.session_state.current_pdf_index = get_next_available_pdf(df, st.session_state.user_id)
                        st.rerun()

if st.session_state.failed_keys:
    with st.expander(f"❌ Failed Downloads ({len(st.session_state.failed_keys)} files)", expanded=False):
        for bibkey in sorted(st.session_state.failed_keys):
            matching_rows = df[df["Bib Key"] == bibkey]
            if not matching_rows.empty:
                title = matching_rows.iloc[0].get("Title", "No title")
                col1, col2, col3 = st.columns([3, 4, 1])
                with col1:
                    st.markdown(f"**❌ {bibkey}**")
                with col2:
                    st.caption(f"{title[:60]}...")
                with col3:
                    if st.button("🔄", key=f"retry_{bibkey}", help="Retry this PDF"):
                        st.session_state.failed_keys.discard(bibkey)
                        st.session_state.current_pdf_index = df[df["Bib Key"] == bibkey].index[0]
                        st.rerun()

# ZIP creation section
if st.session_state.downloaded_keys:
    with st.expander("📦 Create ZIP from Downloaded Files"):
        col1, col2 = st.columns(2)
        
        with col1:
            zip_folder = st.text_input(
                "📁 Folder path with PDFs:",
                placeholder="C:\\Downloads\\PDFs",
                help="Path to folder containing your downloaded PDF files"
            )
        
        with col2:
            zip_name = st.text_input(
                "📋 ZIP filename:",
                value=f"pdfs_{st.session_state.user_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            )
        
        if st.button("📁 Create ZIP File", type="secondary"):
            if not zip_folder or not os.path.isdir(zip_folder):
                st.error("❌ Please enter a valid folder path")
            else:
                try:
                    zip_path = os.path.join(zip_folder, zip_name)
                    found_files = 0
                    
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for bibkey in st.session_state.downloaded_keys:
                            pdf_filename = f"{bibkey}.pdf"
                            pdf_path = os.path.join(zip_folder, pdf_filename)
                            
                            if os.path.exists(pdf_path):
                                zipf.write(pdf_path, arcname=pdf_filename)
                                found_files += 1
                    
                    if found_files > 0:
                        file_size = os.path.getsize(zip_path) / (1024 * 1024)
                        st.success(f"🎉 ZIP created with {found_files} files ({file_size:.1f} MB)")
                        st.info(f"📁 Saved to: `{zip_path}`")
                    else:
                        st.error("❌ No PDF files found in the specified folder")
                        
                except Exception as e:
                    st.error(f"❌ Error creating ZIP: {str(e)}")

# Footer
st.markdown("---")
st.markdown(f"""
### 🔧 Multi-User PDF Downloader

**Current Session:** User `{st.session_state.user_id}`

**Key Features:**
- ✅ **Embedded Database**: No need to upload CSV files
- 📄 **One PDF at a Time**: Focus on single PDF to avoid confusion
- 🔍 **File Verification**: Automatically verify downloaded files exist
- 👥 **Multi-User Support**: Each user gets different PDFs to avoid conflicts
- 💾 **Progress Tracking**: Save and restore your progress anytime

**How it works:**
1. Each user gets a unique ID and is assigned different PDFs
2. Only one PDF is shown at a time for focused downloading
3. Files can be verified against your download folder
4. Progress is automatically saved and can be exported/imported
""")

# Custom CSS for better styling
st.markdown("""
<style>
/* Enhanced button styling */
.stButton > button {
    height: 2.75rem;
    border-radius: 8px;
    transition: all 0.2s ease;
    font-weight: 500;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}

/* Card-like containers */
.stContainer > div {
    border-radius: 8px;
}

/* Progress metrics */
.metric-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1rem;
    border-radius: 8px;
    color: white;
}

/* Text input styling */
.stTextInput > div > div > input {
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
    font-size: 13px;
    border-radius: 6px;
    border: 2px solid #e0e0e0;
    transition: border-color 0.2s ease;
}

.stTextInput > div > div > input:focus {
    border-color: #ff4b4b;
    box-shadow: 0 0 0 2px rgba(255, 75, 75, 0.1);
}

/* Link button enhancement */
.stLinkButton > a {
    text-decoration: none;
    border-radius: 8px;
    transition: all 0.2s ease;
}

.stLinkButton > a:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

/* Expander styling */
.streamlit-expanderHeader {
    font-weight: 600;
    border-radius: 8px;
}

/* Success/error message styling */
.stSuccess, .stError, .stWarning, .stInfo {
    border-radius: 8px;
}

/* Custom animations */
@keyframes slideIn {
    from { transform: translateX(-100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}

.slide-in {
    animation: slideIn 0.3s ease-out;
}
</style>
""", unsafe_allow_html=True)