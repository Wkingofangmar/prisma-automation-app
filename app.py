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
    "3. Export Data",
    "4. PDF LLM Extraction"
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
elif step == "3. Export Data":
    st.subheader("Step 3: Export Curated Results")
    
    # Check if we have filtered data to export
    if 'filtered_results' not in st.session_state or st.session_state['filtered_results'].empty:
        st.warning("No filtered results found. Please go back to Step 2 and save your curated list first.")
    else:
        st.write("Your curated list of papers is ready. Choose your preferred export format below.")
        
        # Load the final dataset
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
