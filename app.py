import streamlit as st
import pandas as pd
import urllib.parse
import os
import zipfile
import json
import re
from datetime import datetime
import time

# --- Page Config ---
st.set_page_config(page_title="PDF Manual Downloader", layout="wide")
st.title("📄 PDF Manual Downloader")

# --- Configuration Class ---
class Config:
    """Configuration class for app settings"""
    def __init__(self):
        self.prioritize_url = True
        self.max_title_length = 60
        self.supported_encodings = ['utf-8', 'latin-1', 'cp1252']
        self.invalid_filename_chars = '<>:"/\\|?*'
    
    def to_dict(self):
        return self.__dict__

# --- Initialize Session State ---
def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        'downloaded_keys': set(),
        'failed_keys': set(),
        'csv_uploaded': False,
        'config': Config().to_dict(),
        'search_term': '',
        'status_filter': 'All'
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()

# --- Helper Functions ---
def validate_filename(filename):
    """Validate filename for filesystem compatibility"""
    if not filename:
        return False
    config = Config()
    return not any(char in filename for char in config.invalid_filename_chars)

def validate_url(url):
    """Validate URL format"""
    if not url:
        return False
    url_pattern = re.compile(
        r'https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(url_pattern.match(url))

def copy_to_clipboard(text, key):
    """Helper function to copy text to clipboard if supported"""
    try:
        import pyperclip
        pyperclip.copy(text)
        st.toast(f"✅ Copied: {text}")
        return True
    except (ImportError, pyperclip.PyperclipException):
        st.warning("📋 Auto-copy is not available in this environment. Please copy manually.", icon="⚠️")
        return False
    except Exception as e:
        st.error(f"⚠️ Clipboard error: {str(e)}")
        return False

def preprocess_url(url):
    """Cleans URLs by removing backslashes and upgrading HTTP to HTTPS."""
    if not url:
        return url
    
    # Clean the URL
    cleaned_url = url.strip().replace('\\', '')
    
    # Upgrade HTTP to HTTPS
    if cleaned_url.startswith('http://'):
        cleaned_url = 'https://' + cleaned_url[len('http://'):]
    
    # Validate the URL
    if not validate_url(cleaned_url):
        st.warning(f"⚠️ Invalid URL format: {cleaned_url}")
        return url  # Return original if validation fails
    
    return cleaned_url

def safe_read_csv(uploaded_file):
    """Safely read CSV with better error handling"""
    config = Config()
    
    for encoding in config.supported_encodings:
        try:
            uploaded_file.seek(0)  # Reset file pointer
            df = pd.read_csv(uploaded_file, dtype=str, encoding=encoding).fillna('')
            st.success(f"✅ CSV loaded successfully with {encoding} encoding")
            return df
        except UnicodeDecodeError:
            continue
        except Exception as e:
            st.error(f"Error reading CSV with {encoding} encoding: {str(e)}")
            break
    
    st.error("❌ Could not decode CSV file with any supported encoding")
    return None

@st.cache_data
def process_csv_data(csv_content, prioritize_url=True):
    """Cache processed CSV data to avoid reprocessing"""
    try:
        # Convert bytes to string for hashing
        if isinstance(csv_content, bytes):
            csv_string = csv_content.decode('utf-8')
        else:
            csv_string = str(csv_content)
        
        # This function will be called with the CSV content as a string
        # In practice, you'd need to parse this back to a DataFrame
        # For now, we'll return a placeholder
        return None, None
    except Exception as e:
        st.error(f"Error processing CSV data: {e}")
        return None, None

def calculate_detailed_progress():
    """Calculate detailed progress metrics"""
    if 'current_df' not in st.session_state:
        return {
            'total': 0, 'completed': 0, 'failed': 0, 'remaining': 0,
            'completion_rate': 0, 'failure_rate': 0
        }
    
    total = len(st.session_state.current_df)
    completed = len(st.session_state.downloaded_keys)
    failed = len(st.session_state.failed_keys)
    remaining = total - completed - failed
    
    return {
        'total': total,
        'completed': completed,
        'failed': failed,
        'remaining': remaining,
        'completion_rate': (completed / total * 100) if total > 0 else 0,
        'failure_rate': (failed / total * 100) if total > 0 else 0
    }

def bulk_mark_status(bib_keys, status):
    """Mark multiple items as done/failed at once"""
    if status == 'done':
        st.session_state.downloaded_keys.update(bib_keys)
        st.session_state.failed_keys.difference_update(bib_keys)
    elif status == 'failed':
        st.session_state.failed_keys.update(bib_keys)
        st.session_state.downloaded_keys.difference_update(bib_keys)

def export_results():
    """Export complete results including metadata"""
    if 'current_df' not in st.session_state:
        return None
    
    df = st.session_state.current_df.copy()
    df['status'] = df['Bib Key'].apply(
        lambda x: 'completed' if x in st.session_state.downloaded_keys 
        else 'failed' if x in st.session_state.failed_keys 
        else 'pending'
    )
    df['processed_date'] = datetime.now().isoformat()
    
    return df.to_csv(index=False)

def apply_filters(df):
    """Apply search and filter functionality"""
    filtered_df = df.copy()
    
    # Apply search filter
    if st.session_state.search_term:
        search_mask = (
            df['Title'].str.contains(st.session_state.search_term, case=False, na=False) |
            df['Bib Key'].str.contains(st.session_state.search_term, case=False, na=False)
        )
        filtered_df = filtered_df[search_mask]
    
    # Apply status filter
    if st.session_state.status_filter != 'All':
        if st.session_state.status_filter == 'Pending':
            status_mask = (~df["Bib Key"].isin(st.session_state.downloaded_keys) & 
                          ~df["Bib Key"].isin(st.session_state.failed_keys))
        elif st.session_state.status_filter == 'Completed':
            status_mask = df["Bib Key"].isin(st.session_state.downloaded_keys)
        elif st.session_state.status_filter == 'Failed':
            status_mask = df["Bib Key"].isin(st.session_state.failed_keys)
        
        filtered_df = filtered_df[status_mask]
    
    return filtered_df

# --- Sidebar ---
with st.sidebar:
    st.header("📊 Progress Management")

    # Display progress metrics
    progress = calculate_detailed_progress()
    
    if progress['total'] > 0:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Files", progress['total'])
            st.metric("✅ Completed", progress['completed'])
        with col2:
            st.metric("❌ Failed", progress['failed'])
            st.metric("⏳ Remaining", progress['remaining'])

        # Progress bar
        progress_percentage = ((progress['completed'] + progress['failed']) / progress['total']) * 100
        st.progress(progress_percentage / 100)
        st.caption(f"{progress_percentage:.1f}% Processed")
        
        # Additional metrics
        st.caption(f"Success Rate: {progress['completion_rate']:.1f}%")
        if progress['failed'] > 0:
            st.caption(f"Failure Rate: {progress['failure_rate']:.1f}%")

    st.divider()
    
    # Configuration section
    st.header("⚙️ Processing Options")
    st.session_state.config['prioritize_url'] = st.checkbox(
        "Prioritize URL from CSV for 'Open Link'",
        value=st.session_state.config['prioritize_url'],
        help="If checked, use the URL column first. If unchecked or URL is empty, use the DOI column."
    )
    
    # Batch operations
    if progress['total'] > 0:
        st.subheader("🔄 Batch Operations")
        col1, col2 = st.columns(2)
        
        # Get pending items for batch operations
        if 'current_df' in st.session_state:
            pending_keys = set(st.session_state.current_df['Bib Key']) - st.session_state.downloaded_keys - st.session_state.failed_keys
            
            with col1:
                if st.button("✅ Mark All Done", disabled=len(pending_keys) == 0, use_container_width=True):
                    bulk_mark_status(pending_keys, 'done')
                    st.rerun()
            
            with col2:
                if st.button("❌ Mark All Failed", disabled=len(pending_keys) == 0, use_container_width=True):
                    bulk_mark_status(pending_keys, 'failed')
                    st.rerun()

    st.divider()
    
    # Save/Load Progress
    st.subheader("💾 Progress Management")
    
    # Save progress
    if st.session_state.downloaded_keys or st.session_state.failed_keys:
        progress_data = {
            'downloaded_keys': list(st.session_state.downloaded_keys),
            'failed_keys': list(st.session_state.failed_keys),
            'timestamp': datetime.now().isoformat(),
            'total_files': progress['total'],
            'config': st.session_state.config
        }
        st.download_button(
            label="⬇️ Download Progress",
            data=json.dumps(progress_data, indent=2),
            file_name=f"progress_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True
        )
        
        # Export results
        if 'current_df' in st.session_state:
            results_csv = export_results()
            if results_csv:
                st.download_button(
                    label="📊 Export Results CSV",
                    data=results_csv,
                    file_name=f"results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    else:
        st.info("No progress to save yet.")
    
    # Load progress
    st.subheader("📂 Load Progress")
    progress_file = st.file_uploader("Upload Progress File", type=["json"])
    if progress_file:
        try:
            progress_data = json.loads(progress_file.read())
            st.session_state.downloaded_keys.update(progress_data.get('downloaded_keys', []))
            st.session_state.failed_keys.update(progress_data.get('failed_keys', []))
            
            # Load config if available
            if 'config' in progress_data:
                st.session_state.config.update(progress_data['config'])
            
            st.success("✅ Progress loaded successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error loading progress: {e}")
    
    st.divider()
    
    # Clear progress
    if st.button("🗑️ Clear All Progress", type="secondary", use_container_width=True):
        if st.session_state.downloaded_keys or st.session_state.failed_keys:
            # Add confirmation
            if st.button("⚠️ Confirm Clear", type="secondary", use_container_width=True):
                st.session_state.downloaded_keys.clear()
                st.session_state.failed_keys.clear()
                st.success("All progress cleared!")
                st.rerun()
        else:
            st.info("No progress to clear.")

# --- Main Content Area ---
uploaded_file = st.file_uploader("📄 Upload your CSV", type=["csv"])

if uploaded_file:
    with st.spinner("📊 Processing CSV file..."):
        try:
            df_original = safe_read_csv(uploaded_file)
            
            if df_original is None:
                st.stop()
            
            st.session_state.csv_uploaded = True

            # Validate required columns
            required_cols = ["Bib Key", "Title"]
            missing_cols = [col for col in required_cols if col not in df_original.columns]
            
            if missing_cols:
                st.error(f"❌ CSV must contain the columns: {', '.join(missing_cols)}")
                st.info(f"Available columns: {', '.join(df_original.columns.tolist())}")
                st.stop()

            # Process entries
            displayable_entries = []
            skipped_entries = []

            for index, row in df_original.iterrows():
                entry = row.to_dict()
                bib_key = str(entry.get("Bib Key", "")).strip()
                title = str(entry.get("Title", "")).strip()
                doi_val = str(entry.get("DOI", "")).strip()
                url_val = str(entry.get("URL", "")).strip()
                
                # Skip entries without Bib Key
                if not bib_key:
                    skipped_entries.append({
                        'Row': index + 1, 
                        'Reason': "Missing Bib Key"
                    })
                    continue
                
                entry['link'] = None
                entry['google_search_link'] = None
                entry['entry_type'] = 'no_link'

                # Create Google search link if title exists
                if title:
                    safe_title = urllib.parse.quote_plus(title)
                    entry['google_search_link'] = f"https://www.google.com/search?q={safe_title}"

                # Determine link priority
                if st.session_state.config['prioritize_url'] and url_val:
                    entry['entry_type'] = 'url'
                    entry['link'] = preprocess_url(url_val)
                elif doi_val:
                    entry['entry_type'] = 'doi'
                    entry['link'] = f"https://doi.org/{doi_val}"

                if entry['link'] or entry['google_search_link']:
                    displayable_entries.append(entry)
                else:
                    skipped_entries.append({
                        'Bib Key': bib_key, 
                        'Reason': "No DOI, URL, or Title to process."
                    })

            df = pd.DataFrame(displayable_entries)
            st.session_state.current_df = df

            # Display processing results
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Total Rows", len(df_original))
            with col2:
                st.metric("✅ Processable", len(df))
            with col3:
                st.metric("⚠️ Skipped", len(skipped_entries))

            if skipped_entries:
                with st.expander(f"⚠️ View {len(skipped_entries)} Skipped Rows"):
                    st.dataframe(pd.DataFrame(skipped_entries), use_container_width=True)

            if df.empty:
                st.warning("No processable entries found in the uploaded file.")
                st.stop()

        except Exception as e:
            st.error(f"❌ An error occurred while processing the file: {e}")
            st.info("Please ensure your CSV is correctly formatted and uses UTF-8 encoding.")
            st.stop()

# --- Search and Filter Interface ---
if 'current_df' in st.session_state and not st.session_state.current_df.empty:
    st.subheader("🔍 Search and Filter")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.session_state.search_term = st.text_input(
            "🔍 Search by Title or Bib Key", 
            value=st.session_state.search_term,
            placeholder="Enter search term..."
        )
    
    with col2:
        st.session_state.status_filter = st.selectbox(
            "Filter by Status", 
            ["All", "Pending", "Completed", "Failed"],
            index=["All", "Pending", "Completed", "Failed"].index(st.session_state.status_filter)
        )
    
    with col3:
        if st.button("🔄 Reset Filters", use_container_width=True):
            st.session_state.search_term = ''
            st.session_state.status_filter = 'All'
            st.rerun()

    # Apply filters and get data
    df = st.session_state.current_df
    filtered_df = apply_filters(df)
    
    # Show filtering results
    if len(filtered_df) < len(df):
        st.info(f"Showing {len(filtered_df)} of {len(df)} items")

    # Separate items by status
    pending_df = filtered_df[
        (~filtered_df["Bib Key"].isin(st.session_state.downloaded_keys)) & 
        (~filtered_df["Bib Key"].isin(st.session_state.failed_keys))
    ]
    completed_df = filtered_df[filtered_df["Bib Key"].isin(st.session_state.downloaded_keys)]
    failed_df = filtered_df[filtered_df["Bib Key"].isin(st.session_state.failed_keys)]

    # Display pending items
    if not pending_df.empty:
        st.subheader(f"🔄 Pending Downloads ({len(pending_df)} items)")

        for i, (_, row) in enumerate(pending_df.iterrows()):
            bibkey = row["Bib Key"]
            filename = f"{bibkey}.pdf"
            link_url = row.get("link")
            google_link = row.get("google_search_link")
            entry_type = row["entry_type"]
            
            # Create unique key combining bibkey and index
            unique_key_base = f"{bibkey}_{i}_{hash(bibkey) % 1000}"

            with st.container(border=True):
                col1, col2, col3, col4, col5, col6 = st.columns([2.5, 1.2, 1.2, 2.5, 1.2, 1.2])

                with col1:
                    st.markdown(f"**{bibkey}**")
                    if entry_type == 'url':
                        st.caption("🔗 Using URL")
                    elif entry_type == 'doi':
                        st.caption("📄 Using DOI")
                    elif entry_type == 'no_link':
                        st.caption("⚠️ No Direct Link")
                    
                    if "Title" in row and row["Title"]:
                        max_length = st.session_state.config['max_title_length']
                        title_display = str(row['Title'])[:max_length]
                        if len(str(row['Title'])) > max_length:
                            title_display += "..."
                        st.caption(title_display)

                with col2:
                    if link_url:
                        st.link_button(
                            "🔗 Open Link", 
                            link_url, 
                            use_container_width=True,
                            # key=f"link_{unique_key_base}"
                        )
                    else:
                        st.button(
                            "🔗 Open Link", 
                            use_container_width=True, 
                            disabled=True, 
                            help="No direct DOI or URL available.",
                            key=f"disabled_link_{unique_key_base}"
                        )

                with col3:
                    if google_link:
                        st.link_button(
                            "🔍 Search", 
                            google_link, 
                            use_container_width=True,
                            # key=f"search_{unique_key_base}"
                        )
                    else:
                        st.button(
                            "🔍 Search", 
                            use_container_width=True, 
                            disabled=True, 
                            help="No title available to search.",
                            key=f"disabled_search_{unique_key_base}"
                        )

                with col4:
                    filename_col, copy_col = st.columns([4, 1])
                    
                    # Filename input with validation
                    custom_filename = filename_col.text_input(
                        "Filename:", 
                        value=filename, 
                        key=f"filename_{unique_key_base}", 
                        label_visibility="collapsed"
                    )
                    
                    # Validate filename
                    is_valid_filename = validate_filename(custom_filename)
                    if not is_valid_filename and custom_filename:
                        st.caption("⚠️ Invalid filename characters")
                    
                    if copy_col.button("📋", key=f"copy_{unique_key_base}", help="Copy filename"):
                        if is_valid_filename:
                            copy_to_clipboard(custom_filename, f"copy_{unique_key_base}")
                        else:
                            st.error("Cannot copy invalid filename")

                with col5:
                    if st.button(
                        "✅ Done", 
                        key=f"done_{unique_key_base}", 
                        type="primary", 
                        use_container_width=True
                    ):
                        st.session_state.downloaded_keys.add(bibkey)
                        st.rerun()

                with col6:
                    if st.button(
                        "❌ Failed", 
                        key=f"failed_{unique_key_base}", 
                        type="secondary", 
                        use_container_width=True
                    ):
                        st.session_state.failed_keys.add(bibkey)
                        st.rerun()
    else:
        if st.session_state.status_filter == 'Pending':
            st.success("🎉 No pending items found!")
        elif len(filtered_df) == 0:
            st.info("No items match your current filters.")

    # Display completed items
    if not completed_df.empty:
        with st.expander(f"✅ Completed Downloads ({len(completed_df)} files)", expanded=False):
            for _, row in completed_df.iterrows():
                col1, col2, col3 = st.columns([3, 4, 1.5])
                col1.markdown(f"**✅ {row['Bib Key']}**")
                col2.markdown(f"~~`{row['Bib Key']}.pdf`~~")
                if col3.button("↩️ Undo", key=f"undo_{row['Bib Key']}_{hash(row['Bib Key']) % 1000}"):
                    st.session_state.downloaded_keys.discard(row['Bib Key'])
                    st.rerun()

    # Display failed items
    if not failed_df.empty:
        with st.expander(f"❌ Failed Items ({len(failed_df)} files)", expanded=False):
            for _, row in failed_df.iterrows():
                col1, col2, col3 = st.columns([3, 4, 1.5])
                col1.markdown(f"**❌ {row['Bib Key']}**")
                col2.markdown(f"*{row.get('Title', 'No Title')}*")
                if col3.button("🔄 Retry", key=f"retry_{row['Bib Key']}_{hash(row['Bib Key']) % 1000}"):
                    st.session_state.failed_keys.discard(row['Bib Key'])
                    st.rerun()

    # ZIP Creation Section
    if st.session_state.downloaded_keys:
        st.divider()
        with st.expander("📦 Create ZIP from Downloaded Files", expanded=False):
            zip_folder = st.text_input(
                "📁 Folder path with renamed PDFs:",
                help="Enter the full path to the folder containing your renamed PDF files"
            )
            zip_name = st.text_input(
                "📋 ZIP filename:", 
                value=f"papers_{datetime.now().strftime('%Y%m%d')}.zip"
            )
            
            if st.button("📁 Create ZIP File", type="primary"):
                if not zip_folder or not os.path.isdir(zip_folder):
                    st.error("❌ Please provide a valid folder path.")
                else:
                    try:
                        with st.spinner("Creating ZIP file..."):
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
                                st.warning(f"⚠️ Could not find {len(missing_files)} files:")
                                with st.expander("View missing files"):
                                    for missing_file in missing_files:
                                        st.write(f"- {missing_file}")
                                        
                    except Exception as e:
                        st.error(f"❌ Error creating ZIP file: {e}")

# --- Footer and Instructions ---
st.markdown("---")
st.markdown("""
### 📝 How to Use This App

#### 🚀 Getting Started
1. **Configure Settings**: Use the sidebar to configure your preferences (URL vs DOI priority)
2. **Upload CSV**: Your CSV must contain `Bib Key` and `Title` columns. `DOI` and `URL` columns are optional but recommended
3. **Review Processing**: Check the processing summary and any skipped entries

#### 📋 Processing Workflow
1. **Search & Filter**: Use the search box to find specific papers or filter by status
2. **For Each Paper**:
   - **🔗 Open Link**: Opens the direct URL or DOI link
   - **🔍 Search**: Opens Google search for the paper title
   - **Download**: Find and download the PDF from the opened link
   - **Rename**: Copy the suggested filename and rename your downloaded PDF
   - **Mark Status**: Click **✅ Done** when successful or **❌ Failed** if not found

#### 💡 Pro Tips
- Use **Batch Operations** in the sidebar for bulk status updates
- **Save Progress** regularly to avoid losing your work
- **Export Results** to get a complete CSV with processing status
- Invalid filename characters (`<>:"/\\|?*`) will be highlighted
- The app remembers your progress even if you refresh the page

#### 🔧 Advanced Features
- **Progress Tracking**: Monitor completion rates and success metrics
- **Search & Filter**: Find specific papers quickly
- **Bulk Operations**: Mark multiple items at once
- **ZIP Creation**: Package all downloaded PDFs into a single archive
- **Progress Import/Export**: Share progress between sessions or collaborators

#### ⚠️ Troubleshooting
- If CSV upload fails, try saving as UTF-8 encoding
- Clear browser cache if buttons become unresponsive
- Use the "Reset Filters" button if search results seem incorrect
""")

# Display app info
st.sidebar.markdown("---")
st.sidebar.markdown("**📊 App Info**")
st.sidebar.caption(f"Version: 2.0")
st.sidebar.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d')}")
if 'current_df' in st.session_state:
    st.sidebar.caption(f"Loaded: {len(st.session_state.current_df)} items")