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

# Core Function: Search OpenAlex
# Core Function: Search OpenAlex
# Core Function: Search OpenAlex
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

                data.append({
                    "Keep": True,
                    "Title": str(title),
                    "Author(s)": str(author_string),
                    "Year": str(year),
                    "Journal": str(journal_name),
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
    
    # Check if the user has actually run a search yet
    if 'raw_results' not in st.session_state or st.session_state['raw_results'].empty:
        st.warning("No search results found. Please go back to Step 1 and run a search first.")
    else:
        st.write("Review your search results below. Uncheck the 'Keep' box for any papers you want to exclude (e.g., GBIF datasets, irrelevant titles).")
        
        # --- NEW: Bulk Select/Deselect Buttons ---
        col1, col2, col3 = st.columns([1, 1, 4]) # Creates two small columns for buttons and empty space
        
        with col1:
            if st.button("Select All", use_container_width=True):
                st.session_state['raw_results']['Keep'] = True
                st.rerun() # Refreshes the page to show the updated table
                
        with col2:
            if st.button("Deselect All", use_container_width=True):
                st.session_state['raw_results']['Keep'] = False
                st.rerun()
        # -----------------------------------------
        
        # Load the raw dataframe
        df_to_edit = st.session_state['raw_results']
        
        # Display the interactive data editor
        edited_df = st.data_editor(
            df_to_edit,
            column_config={
                "Keep": st.column_config.CheckboxColumn(
                    "Keep?",
                    help="Uncheck to remove this paper from your final export.",
                    default=True,
                )
            },
            # Disable editing on metadata to prevent accidental typos
            disabled=["Title", "Author(s)", "Year", "Journal", "DOI"], 
            hide_index=True,
            use_container_width=True,
            height=600 # Gives a nice large viewing window
        )
        
        # Save button to lock in the filters
        if st.button("Save Filtered Results", type="primary"):
            # Overwrite the raw results with the edited dataframe so manual checks persist across pages
            st.session_state['raw_results'] = edited_df 
            
            # Filter the dataframe to only rows where 'Keep' is True
            final_filtered_df = edited_df[edited_df["Keep"] == True].copy()
            
            # Drop the 'Keep' column now since it served its purpose
            final_filtered_df = final_filtered_df.drop(columns=["Keep"])
            
            # Save the curated list to session state for the next steps
            st.session_state['filtered_results'] = final_filtered_df
            
            st.success(f"Filtered list saved! You kept {len(final_filtered_df)} out of {len(edited_df)} papers.")
            st.info("You can now proceed to Step 3: Export Data.")
            
        # Quick preview of the current saved filtered list if it exists
        if 'filtered_results' in st.session_state:
            st.divider()
            st.write("### Current Curated List Preview")
            st.dataframe(st.session_state['filtered_results'], hide_index=True)
