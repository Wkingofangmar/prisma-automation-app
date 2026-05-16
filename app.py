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
def search_openalex(query):
    try:
        # Fetch up to 100 results natively. .get() is much safer than .paginate() for single batches.
        # OpenAlex's .search() automatically looks through full text, titles, and abstracts.
        query_result = Works().search(query).get(per_page=100)
        
        # Safety catch: ensuring we are working with the list of results
        if isinstance(query_result, dict) and "results" in query_result:
            query_result = query_result["results"]
        elif isinstance(query_result, tuple):
            query_result = query_result[0]
            
        data = []
        for res in query_result:
            # Skip any malformed API entries
            if not isinstance(res, dict):
                continue
                
            # 1. Safely extract authors (OpenAlex often returns None instead of empty lists)
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
            
            # 3. Safely get metadata fields (using 'or' catches the 'None' values)
            title = res.get("title") or "No Title"
            year = res.get("publication_year") or "N/A"
            doi = res.get("doi") or "No DOI"

            # 4. Append to data list with forced string conversion so Streamlit never renders a blank None type
            data.append({
                "Keep": True,
                "Title": str(title),
                "Author(s)": str(author_string),
                "Year": str(year),
                "Journal": str(journal_name),
                "DOI": str(doi)
            })
        
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
    
    if st.button("Run Search"):
        if search_query.strip() == "":
            st.warning("Please enter a keyword before searching.")
        else:
            with st.spinner("Searching OpenAlex database..."):
                results_df = search_openalex(search_query)
                
                if not results_df.empty:
                    # Store the results in Streamlit's session state so they persist across pages
                    st.session_state['raw_results'] = results_df
                    st.success(f"Found {len(results_df)} results!")
                else:
                    st.info("No results found or an issue occurred.")

    # Display the results if they exist in the session state
    if 'raw_results' in st.session_state:
        st.write("### Current Search Results")
        st.dataframe(st.session_state['raw_results'])
