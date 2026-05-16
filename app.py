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
