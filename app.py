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
def search_openalex(query):
    try:
        # Fetch the top 50 works matching the search query
        # You can increase the per_page limit later if needed
        results = Works().search(query).paginate(per_page=50, page=1)
        
        data = []
        for res in results:
            # Safely extract author names
            authorships = res.get("authorships", [])
            author_names = [a.get("author", {}).get("display_name", "") for a in authorship]
            author_string = ", ".join(filter(None, author_names))
            
            # Safely extract journal/source name
            primary_location = res.get("primary_location", {}) or {}
            source = primary_location.get("source", {}) or {}
            journal_name = source.get("display_name", "Unknown Journal")
            
            data.append({
                "Keep": True,  # Checkbox for Step 2
                "Title": res.get("title", "No Title"),
                "Author(s)": author_string if author_string else "Unknown Authors",
                "Year": res.get("publication_year", "N/A"),
                "Journal": journal_name,
                "DOI": res.get("doi", "No DOI")
            })
        
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"An error occurred during the search: {e}")
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
