import streamlit as st
import pandas as pd
from pyalex import Works

# Set the page configuration
st.set_page_config(page_title="PRISMA Automator", page_icon="📚", layout="wide")

st.title("📚 PRISMA Systematic Review Automator")
st.write("Welcome to your automated literature review pipeline.")

# Sidebar Navigation
st.sidebar.header("Pipeline Steps")
step = st.sidebar.radio("Select a step:", [
    "1. Search Databases",
    "2. Filter Results",
    "3. Export Data (Optional Rayyan Route)",
    "4. Deduplicate & Screen (In-App Route)",
    "5. PDF LLM Extraction"
])

st.divider()

# Helper Function: Decode OpenAlex Inverted Index
def reconstruct_abstract(inverted_index):
    if not inverted_index or not isinstance(inverted_index, dict):
        return "No abstract available."
    
    # Create a list of tuples: (position, word)
    word_index = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_index.append((pos, word))
    
    # Sort the list by the numerical position to put the sentence in order
    word_index.sort(key=lambda x: x[0])
    
    # Extract just the words and join them with spaces
    return " ".join([word for pos, word in word_index])

# Core Function: Search OpenAlex
def search_openalex(query, max_results):
    try:
        # Initialize the search query object
        base_query = Works().search(query)
        
        data = []
        page = 1
        per_page = 100
        
        # Calculate how many pages we need to fetch based on user input
        max_pages = (max_results // per_page) + (1 if max_results % per_page > 0 else 0)
        
        # Streamlit UI elements for progress tracking
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        while page <= max_pages:
            progress_text.text(f"Fetching page {page} of {max_pages}...")
            progress_bar.progress(page / max_pages)
            
            # return_meta=True gives us a tuple: (the batch of results, metadata about total results)
            batch, meta = base_query.get(return_meta=True, per_page=per_page, page=page)
            
            if not batch:
                break  # Exit loop if no more results exist
                
            for res in batch:
                if not isinstance(res, dict):
                    continue
                    
                # 1. Safely extract authors
                authorships = res.get("authorships") or []
                author_names = []
                for a in authorships:
                    author_data = a.get("author") or {}
                    name = author_data.get("display_name")
                    if name:
                        author_names.append(name)
                author_string = ", ".join(author_names) if author_names else "Unknown Authors"
                
                # 2. Safely extract journal/source
                primary_location = res.get("primary_location") or {}
                source = primary_location.get("source") or {}
                journal_name = source.get("display_name") or "Unknown Journal"
                
                # 3. Safely get metadata fields
                title = res.get("title") or "No Title"
                year = res.get("publication_year") or "N/A"
                doi = res.get("doi") or "No DOI"
                
                # FIXED: Extract the scrambled index and reconstruct it
                raw_inverted_index = res.get("abstract_inverted_index")
                abstract = reconstruct_abstract(raw_inverted_index)
                
                # Extract OpenAlex Keywords
                raw_keywords = res.get("keywords") or []
                keyword_names = [kw.get("display_name") for kw in raw_keywords if isinstance(kw, dict) and kw.get("display_name")]
                keywords_string = "; ".join(keyword_names) if keyword_names else "No keywords available."

                data.append({
                    "Keep": True,
                    "Title": str(title),
                    "Author(s)": str(author_string),
                    "Year": str(year),
                    "Journal": str(journal_name),
                    "Abstract": str(abstract),
                    "Keywords": str(keywords_string), 
                    "DOI": str(doi)
                })
                
                # If we've hit the exact user-defined limit, stop appending
                if len(data) >= max_results:
                    break
            
            # If the database has fewer results than our limit, stop early
            total_available = meta.get("count", 0)
            if len(data) >= total_available or len(data) >= max_results:
                break
                
            page += 1
            
        # Clean up the progress bar once done
        progress_text.empty()
        progress_bar.empty()
        
        return pd.DataFrame(data)
    
    except Exception as e:
        st.error(f"An error occurred during the search: {e}")
        import traceback
        st.code(traceback.format_exc())
        return pd.DataFrame()

# STEP 1: SEARCH DATABASES
if step == "1. Search Databases":
    st.subheader("Step 1: Search Literature Databases (OpenAlex)")
    
    # User inputs keywords
    search_query = st.text_input(
        "Enter your search keywords (e.g., 'Microplastic ingestion sea turtles'):",
        placeholder="Type keywords here..."
    )
    
    # NEW: Slider for user to control the maximum fetch limit
    max_results_limit = st.slider(
        "Maximum number of results to fetch:", 
        min_value=100, 
        max_value=2000, 
        value=500, 
        step=100
    )
    
    if st.button("Run Search"):
        if search_query.strip() == "":
            st.warning("Please enter a keyword before searching.")
        else:
            with st.spinner("Initializing search sequence..."):
                # Pass the slider value to the function
                results_df = search_openalex(search_query, max_results_limit)
                
                if not results_df.empty:
                    st.session_state['raw_results'] = results_df
                    st.success(f"Successfully retrieved {len(results_df)} results!")
                else:
                    st.info("No results found or an issue occurred.")

    # Display the results if they exist in the session state
    if 'raw_results' in st.session_state:
        st.write("### Current Search Results")
        st.dataframe(st.session_state['raw_results'])

# STEP 2: FILTER RESULTS
elif step == "2. Filter Results":
    st.subheader("Step 2: Manually Filter 'Noise' from Results")
    
    if 'raw_results' not in st.session_state or st.session_state['raw_results'].empty:
        st.warning("No search results found. Please go back to Step 1 and run a search first.")
    else:
        st.write("Review your search results below. Uncheck the 'Keep' box for any papers you want to exclude.")
        
        # --- NEW: Custom Python-Side Search/Filter Bar ---
        search_filter = st.text_input("🔍 Filter table to specific records (e.g., 'GBIF'):", placeholder="Type to filter...")
        
        # Slice the dataframe based on the custom search input
        df_to_edit = st.session_state['raw_results']
        if search_filter:
            # Check if the search term exists in ANY column (case-insensitive)
            mask = df_to_edit.astype(str).apply(lambda col: col.str.contains(search_filter, case=False)).any(axis=1)
            display_df = df_to_edit[mask]
        else:
            display_df = df_to_edit
            
        # --- NEW: Context-Aware Bulk Buttons ---
        col1, col2, col3 = st.columns([1, 1, 4])
        
        with col1:
            # Change label based on whether a filter is active
            btn_label_1 = "Select Visible" if search_filter else "Select All"
            if st.button(btn_label_1, use_container_width=True):
                # Apply True only to the indices currently visible in display_df
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = True
                st.rerun()
                
        with col2:
            btn_label_2 = "Deselect Visible" if search_filter else "Deselect All"
            if st.button(btn_label_2, use_container_width=True):
                # Apply False only to the indices currently visible in display_df
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = False
                st.rerun()
                
        # Show the user how many records they are looking at
        st.caption(f"Showing {len(display_df)} of {len(df_to_edit)} total records.")
        
        # Display the interactive data editor with the SLICED data
        edited_display_df = st.data_editor(
            display_df,
            column_config={
                "Keep": st.column_config.CheckboxColumn(
                    "Keep?",
                    help="Uncheck to remove this paper from your final export.",
                    default=True,
                )
            },
            # NEW: Added "Keywords" to the disabled list
            disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI"], 
            hide_index=True,
            use_container_width=True,
            height=500 
        )
        
        # Sync any manual, individual checkbox clicks back to the master dataframe
        st.session_state['raw_results'].loc[edited_display_df.index, 'Keep'] = edited_display_df['Keep']
        
        # Save button to lock in the filters
        if st.button("Save Filtered Results", type="primary"):
            # Work directly off the master dataframe
            master_df = st.session_state['raw_results']
            
            # Filter down to only what is kept
            final_filtered_df = master_df[master_df["Keep"] == True].copy()
            final_filtered_df = final_filtered_df.drop(columns=["Keep"])
            
            # Save the curated list to session state for the next steps
            st.session_state['filtered_results'] = final_filtered_df
            
            st.success(f"Filtered list saved! You kept {len(final_filtered_df)} out of {len(master_df)} total papers.")
            st.info("You can now proceed to Step 3: Export Data.")
            
        # Quick preview of the current saved filtered list if it exists
        if 'filtered_results' in st.session_state:
            st.divider()
            st.write("### Current Curated List Preview")
            st.dataframe(st.session_state['filtered_results'], hide_index=True)
# STEP 3: EXPORT DATA
elif step == "3. Export Data (Optional Rayyan Route)":
    st.subheader("Step 3: Export Curated Results (Optional)")
    
    if 'filtered_results' not in st.session_state or st.session_state['filtered_results'].empty:
        st.warning("No filtered results found. Please go back to Step 2 and save your curated list first.")
    else:
        st.write("If you prefer to use **Rayyan** for your title/abstract screening, download your files below. Otherwise, skip to Step 4 to screen directly in this app.")
        
        # Load the dataset from Step 2
        final_df = st.session_state['filtered_results']
        
        # Show a final preview
        st.dataframe(final_df, hide_index=True)
        st.divider()
        st.write("### Download Options")
        
        # Create 3 columns for side-by-side buttons
        col1, col2, col3 = st.columns(3)
        
        # --- Option 1: Standard CSV ---
        with col1:
            csv_data = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Download Standard CSV",
                data=csv_data,
                file_name="PRISMA_filtered_results.csv",
                mime="text/csv",
                use_container_width=True,
                help="Standard comma-separated format."
            )
            
        # --- Option 2: Excel Workbook ---
        with col2:
            import io
            # We use an in-memory buffer so we don't have to save a physical file to your hard drive first
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name="Filtered Papers")
            
            st.download_button(
                label="📊 Download Excel (.xlsx)",
                data=excel_buffer.getvalue(),
                file_name="PRISMA_filtered_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Formatted Excel workbook."
            )
            
        # --- Option 3: Rayyan Compatible CSV ---
        with col3:
            # Rayyan requires specific lowercase headers to auto-map the data
            rayyan_df = final_df.rename(columns={
                "Title": "title",
                "Author(s)": "authors",
                "Year": "year",
                "Journal": "journal",
                "Abstract": "abstract",
                "Keywords": "keywords", # NEW: Map keywords perfectly for Rayyan
                "DOI": "url"  
            })
            rayyan_csv = rayyan_df.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="🔄 Download for Rayyan",
                data=rayyan_csv,
                file_name="Rayyan_Import.csv",
                mime="text/csv",
                use_container_width=True,
                help="Automatically renames columns so Rayyan accepts the upload flawlessly."
            )
# STEP 4: DEDUPLICATION & SCREENING (In-App Route)
elif step == "4. Deduplicate & Screen (In-App Route)":
    st.subheader("Step 4: Title & Abstract Screening (Rayyan Bypass)")
    
    if 'filtered_results' not in st.session_state or st.session_state['filtered_results'].empty:
        st.warning("No results found. Please complete Step 2 first.")
    else:
        # Initialize the screening dataframe in session state so changes persist
        if 'screening_data' not in st.session_state:
            df = st.session_state['filtered_results'].copy()
            df['Screening_Keep'] = True
            st.session_state['screening_data'] = df
        
        df_screen = st.session_state['screening_data']
        
        # --- 1. DEDUPLICATION MODULE ---
        st.write("### 1. Duplicate Checker")
        
        df_screen['temp_title'] = df_screen['Title'].str.lower().str.strip()
        title_dupes = df_screen.duplicated(subset=['temp_title'], keep=False)
        doi_dupes = df_screen.duplicated(subset=['DOI'], keep=False) & (df_screen['DOI'] != "No DOI")
        
        duplicates_df = df_screen[title_dupes | doi_dupes].sort_values(by=['temp_title'])
        
        if not duplicates_df.empty:
            st.warning(f"Found {len(duplicates_df)} potential duplicate records! They are grouped together below.")
            st.write("Uncheck the 'Keep?' box for the duplicate versions you want to discard.")
            
            edited_dupes = st.data_editor(
                duplicates_df,
                column_config={
                    "Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)
                },
                column_order=["Screening_Keep", "Title", "Author(s)", "Year", "Journal", "DOI"],
                disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "temp_title"],
                hide_index=True,
                use_container_width=True
            )
            st.session_state['screening_data'].loc[edited_dupes.index, 'Screening_Keep'] = edited_dupes['Screening_Keep']
        else:
            st.success("No duplicates found!")
            
        st.divider()
        
        # --- 2. KEYWORD SCREENING MODULE ---
        st.write("### 2. Keyword Screening (Title / Abstract / Keywords)")
        st.write("Filter the dataset for specific inclusion/exclusion criteria. Uncheck papers that don't meet your PRISMA criteria.")
        
        search_filter = st.text_input("🔍 Search for keywords (e.g., 'microplastic', 'ingestion'):", placeholder="Type to filter...")
        
        if search_filter:
            mask = df_screen[['Title', 'Abstract', 'Keywords']].astype(str).apply(lambda col: col.str.contains(search_filter, case=False)).any(axis=1)
            display_df = df_screen[mask]
        else:
            display_df = df_screen
            
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            btn_label_1 = "Select Visible" if search_filter else "Select All"
            if st.button(btn_label_1, use_container_width=True):
                st.session_state['screening_data'].loc[display_df.index, 'Screening_Keep'] = True
                st.rerun()
                
        with col2:
            btn_label_2 = "Deselect Visible" if search_filter else "Deselect All"
            if st.button(btn_label_2, use_container_width=True):
                st.session_state['screening_data'].loc[display_df.index, 'Screening_Keep'] = False
                st.rerun()
        
        st.caption(f"Showing {len(display_df)} of {len(df_screen)} records.")
        
        edited_display_df = st.data_editor(
            display_df,
            column_config={
                "Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)
            },
            column_order=["Screening_Keep", "Title", "Author(s)", "Year", "Abstract", "Keywords"],
            disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "temp_title"], 
            hide_index=True,
            use_container_width=True,
            height=500 
        )
        
        st.session_state['screening_data'].loc[edited_display_df.index, 'Screening_Keep'] = edited_display_df['Screening_Keep']
        
        # --- 3. SAVE AND EXPORT MODULE ---
        if st.button("Save Final Screened Results", type="primary"):
            master_df = st.session_state['screening_data']
            final_screened_df = master_df[master_df["Screening_Keep"] == True].copy()
            final_screened_df = final_screened_df.drop(columns=["Screening_Keep", "temp_title"], errors="ignore")
            
            st.session_state['screened_results'] = final_screened_df
            st.success(f"Screening complete! You kept {len(final_screened_df)} out of {len(master_df)} papers.")
            
        # If they saved, offer them a quick download of the final list
        if 'screened_results' in st.session_state:
            st.divider()
            st.write("### Final Curated List Ready")
            csv_data = st.session_state['screened_results'].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Download Final Screened CSV",
                data=csv_data,
                file_name="PRISMA_Final_Screened.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.info("You can now proceed to Step 5: PDF LLM Extraction.")

# STEP 5: PDF LLM EXTRACTION
elif step == "5. PDF LLM Extraction":
    st.subheader("Step 4: AI-Powered PDF Extraction")
    st.write("Upload a downloaded paper to automatically extract structured data.")
    
    # Secure API Key input
    api_key = st.text_input(
        "Enter your Google Gemini API Key:", 
        type="password", 
        help="Get a free API key at aistudio.google.com"
    )
    
    st.divider()
    
    # Dynamic variables from your prompt
    research_subject = st.text_input("Target Species / Research Subject:", placeholder="e.g., Caretta caretta")
    uploaded_file = st.file_uploader("Upload a PDF paper", type="pdf")
    
    # Initialize a place to store our extracted rows for Step 5
    if 'extraction_history' not in st.session_state:
        st.session_state['extraction_history'] = []

    if st.button("Extract Data", type="primary"):
        if not api_key:
            st.error("Please enter your API Key first.")
        elif not research_subject:
            st.error("Please enter a research subject to guide the AI.")
        elif not uploaded_file:
            st.error("Please upload a PDF file.")
        else:
            with st.spinner("Analyzing PDF... (Running OCR, translation, and data extraction)"):
                try:
                    from google import genai
                    import tempfile
                    import os
                    
                    # 1. Initialize the new modern client
                    client = genai.Client(api_key=api_key)
                    
                    # The Gemini File API requires a file path, so we temporarily save the Streamlit upload
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name

                    # 2. Upload using the new client's files service
                    gemini_file = client.files.upload(file=tmp_file_path)
                    
                    # Your exact prompt with the dynamic subject injected
                    prompt = f"""You are an expert researcher. Extract the primary research data specifically related to the [{research_subject}] from the provided paper.
CRITICAL INSTRUCTIONS:
Focus ONLY on the primary findings of this specific paper.
DO NOT extract data, authors, or studies from the bibliography, reference list, or literature review sections.
Since I am uploading ONE paper, your output table must contain EXACTLY ONE ROW of data.
If the document is a scanned PDF or image, perform OCR. If the text is not in English, translate it into English before processing.
Please format your final output strictly as a Markdown table with the following 5 columns:
Study: The Author and Year of the uploaded paper (e.g., Iversen et al., 2013).
Country: The specific country where the study or observations took place.
Original Language: The language the provided PDF is written in.
Primary Theme: You MUST choose exactly ONE of the following exact phrases. It is STRICTLY FORBIDDEN to invent your own categories. Choose only from this list:
"Taxonomy & Morphology"
"Distribution & Habitat Preferences"
"Ecology & Behavior"
"Conservation & Threats"
Key Finding: A very brief, 1-to-2 sentence summary of this specific paper's primary conclusion.
Only provide the 1-row table in your response, with no extra conversational text."""

                    # 3. Generate the content using the active gemini-2.5-flash model
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[gemini_file, prompt]
                    )
                    
                    # 4. Clean up: delete the file from Google's servers and your app's temporary local storage
                    client.files.delete(name=gemini_file.name)
                    os.remove(tmp_file_path)
                    
                    st.success("Extraction Complete!")
                    
                    # Display the extracted markdown table
                    st.markdown("### Extracted Result")
                    st.markdown(response.text)
                    
                    # Save the raw markdown to session state so we can compile it in Step 5
                    st.session_state['extraction_history'].append(response.text)
                    
                except Exception as e:
                    st.error(f"An error occurred during extraction: {e}")

    # Display the running log of extracted tables
    if st.session_state.get('extraction_history'):
        st.divider()
        st.write(f"### Current Session Extractions ({len(st.session_state['extraction_history'])} papers processed)")
        for idx, res in enumerate(st.session_state['extraction_history']):
            st.markdown(res)
