import streamlit as st
import pandas as pd
import requests
import time
from pyalex import Works
from Bio import Entrez

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

# ==========================================
# HELPER FUNCTIONS & DATABASE ENGINES
# ==========================================

def reconstruct_abstract(inverted_index):
    if not inverted_index or not isinstance(inverted_index, dict):
        return "No abstract available."
    word_index = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_index.append((pos, word))
    word_index.sort(key=lambda x: x[0])
    return " ".join([word for pos, word in word_index])

def search_openalex(query, max_results):
    try:
        base_query = Works().search(query)
        data = []
        page = 1
        per_page = 100
        max_pages = (max_results // per_page) + (1 if max_results % per_page > 0 else 0)
        
        while page <= max_pages:
            batch, meta = base_query.get(return_meta=True, per_page=per_page, page=page)
            if not batch: break
                
            for res in batch:
                if not isinstance(res, dict): continue
                
                authorships = res.get("authorships") or []
                author_names = [a.get("author", {}).get("display_name") for a in authorships if a.get("author", {}).get("display_name")]
                
                journal_name = res.get("primary_location", {}).get("source", {}).get("display_name") or "Unknown Journal"
                abstract = reconstruct_abstract(res.get("abstract_inverted_index"))
                keywords = "; ".join([kw.get("display_name") for kw in res.get("keywords", []) if kw.get("display_name")])
                
                data.append({
                    "Keep": True, "Title": str(res.get("title") or "No Title"),
                    "Author(s)": ", ".join(author_names) if author_names else "Unknown Authors",
                    "Year": str(res.get("publication_year") or "N/A"),
                    "Journal": str(journal_name), "Abstract": str(abstract),
                    "Keywords": str(keywords) if keywords else "No keywords available.", 
                    "DOI": str(res.get("doi") or "No DOI"),
                    "Source": "OpenAlex"
                })
                if len(data) >= max_results: break
            if len(data) >= meta.get("count", 0) or len(data) >= max_results: break
            page += 1
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"OpenAlex Error: {e}")
        return pd.DataFrame()

def search_pubmed(query, max_results, email):
    Entrez.email = email if email else "prisma_automator@example.com"
    try:
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        
        id_list = record.get("IdList", [])
        if not id_list: return pd.DataFrame()
        
        data = []
        # Fetch in batches of 100 to avoid timeout
        for i in range(0, len(id_list), 100):
            batch_ids = id_list[i:i+100]
            handle = Entrez.efetch(db="pubmed", id=batch_ids, retmode="xml")
            records = Entrez.read(handle)
            handle.close()
            
            for pubmed_article in records.get('PubmedArticle', []):
                medline = pubmed_article['MedlineCitation']
                article = medline['Article']
                
                title = article.get('ArticleTitle', 'No Title')
                year = article.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {}).get('Year', 'N/A')
                journal = article.get('Journal', {}).get('Title', 'Unknown Journal')
                
                authors = ", ".join([f"{a.get('LastName', '')} {a.get('Initials', '')}".strip() for a in article.get('AuthorList', []) if isinstance(a, dict)])
                
                abstract_list = article.get('Abstract', {}).get('AbstractText', [])
                abstract = " ".join([str(a) for a in abstract_list]) if abstract_list else "No abstract available."
                
                doi = "No DOI"
                for article_id in pubmed_article.get('PubmedData', {}).get('ArticleIdList', []):
                    if article_id.attributes.get('IdType') == 'doi':
                        doi = f"https://doi.org/{str(article_id)}"
                        break
                        
                keywords = "; ".join([str(k) for k in medline.get('KeywordList', [[]])[0]]) if medline.get('KeywordList') else "No keywords available."
                
                data.append({
                    "Keep": True, "Title": title, "Author(s)": authors or "Unknown Authors",
                    "Year": year, "Journal": journal, "Abstract": abstract,
                    "Keywords": keywords, "DOI": doi, "Source": "PubMed"
                })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"PubMed Error: {e}")
        return pd.DataFrame()

def search_semanticscholar(query, max_results):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    data = []
    offset = 0
    try:
        while len(data) < max_results:
            params = {
                "query": query, 
                "limit": min(100, max_results - len(data)), 
                "offset": offset, 
                "fields": "title,authors,year,venue,abstract,externalIds"
            }
            res = requests.get(url, params=params).json()
            if 'data' not in res or not res['data']: break
            
            for item in res['data']:
                authors = ", ".join([a.get('name', '') for a in item.get('authors', [])])
                doi = item.get('externalIds', {}).get('DOI')
                doi_str = f"https://doi.org/{doi}" if doi else "No DOI"
                
                data.append({
                    "Keep": True, "Title": item.get('title', 'No Title'),
                    "Author(s)": authors or "Unknown Authors",
                    "Year": str(item.get('year', 'N/A')),
                    "Journal": item.get('venue', 'Unknown Journal') or "Unknown Journal",
                    "Abstract": item.get('abstract') or "No abstract available.",
                    "Keywords": "N/A", "DOI": doi_str, "Source": "Semantic Scholar"
                })
            offset += 100
            time.sleep(0.5) # Respect rate limits
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Semantic Scholar Error: {e}")
        return pd.DataFrame()

def search_crossref(query, max_results):
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": min(max_results, 1000)}
    try:
        response = requests.get(url, params=params).json()
        data = []
        for item in response.get('message', {}).get('items', []):
            authors = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get('author', [])])
            year = item.get('published-print', {}).get('date-parts', [[None]])[0][0]
            if not year: year = item.get('created', {}).get('date-parts', [[None]])[0][0]
            
            doi = item.get('DOI')
            doi_str = f"https://doi.org/{doi}" if doi else "No DOI"
            
            data.append({
                "Keep": True, "Title": item.get('title', ['No Title'])[0],
                "Author(s)": authors or "Unknown Authors", "Year": str(year) if year else "N/A",
                "Journal": item.get('container-title', ['Unknown Journal'])[0],
                "Abstract": item.get('abstract', 'No abstract available.'),
                "Keywords": "N/A", "DOI": doi_str, "Source": "Crossref"
            })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Crossref Error: {e}")
        return pd.DataFrame()

def search_europepmc(query, max_results):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": min(max_results, 1000)}
    try:
        response = requests.get(url, params=params).json()
        data = []
        for item in response.get('resultList', {}).get('result', []):
            doi = item.get('doi')
            doi_str = f"https://doi.org/{doi}" if doi else "No DOI"
            
            kw_data = item.get('keywordList', {}).get('keyword', [])
            keywords = "; ".join(kw_data) if isinstance(kw_data, list) else str(kw_data)
            
            data.append({
                "Keep": True, "Title": item.get('title', 'No Title'),
                "Author(s)": item.get('authorString', 'Unknown Authors'),
                "Year": str(item.get('pubYear', 'N/A')),
                "Journal": item.get('journalTitle', 'Unknown Journal'),
                "Abstract": item.get('abstractText', 'No abstract available.'),
                "Keywords": keywords if keywords else "N/A",
                "DOI": doi_str, "Source": "Europe PMC"
            })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Europe PMC Error: {e}")
        return pd.DataFrame()

def search_scopus(query, max_results, api_key):
    if not api_key: return pd.DataFrame()
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    data = []
    start = 0
    try:
        while len(data) < max_results:
            params = {"query": query, "count": min(25, max_results - len(data)), "start": start}
            response = requests.get(url, headers=headers, params=params).json()
            entries = response.get('search-results', {}).get('entry', [])
            if not entries: break
            
            for item in entries:
                doi = item.get('prism:doi')
                doi_str = f"https://doi.org/{doi}" if doi else "No DOI"
                
                data.append({
                    "Keep": True, "Title": item.get('dc:title', 'No Title'),
                    "Author(s)": item.get('dc:creator', 'Unknown Authors'),
                    "Year": str(item.get('prism:coverDate', 'N/A'))[:4],
                    "Journal": item.get('prism:publicationName', 'Unknown Journal'),
                    "Abstract": "N/A (Scopus requires Full Text API for abstracts)",
                    "Keywords": "N/A", "DOI": doi_str, "Source": "Scopus"
                })
            start += 25
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Scopus Error: {e}")
        return pd.DataFrame()

# ==========================================
# STEP 1: SEARCH DATABASES
# ==========================================
if step == "1. Search Databases":
    st.subheader("Step 1: Search Literature Databases")
    
    search_query = st.text_input("Enter your search keywords:", placeholder="e.g., 'Microplastic ingestion sea turtles'")
    max_results_limit = st.slider("Max results PER DATABASE:", min_value=100, max_value=2000, value=500, step=100)
    
    st.write("### Select Databases to Query")
    col1, col2, col3 = st.columns(3)
    with col1:
        use_openalex = st.checkbox("OpenAlex (Multidisciplinary)", value=True)
        use_pubmed = st.checkbox("PubMed (Life Sciences/Medicine)", value=True)
    with col2:
        use_s2 = st.checkbox("Semantic Scholar (AI Graph)", value=True)
        use_crossref = st.checkbox("Crossref (DOI Registry)")
    with col3:
        use_epmc = st.checkbox("Europe PMC (Life Sciences)")
        use_scopus = st.checkbox("Scopus (Requires API Key)")
        
    pubmed_email = ""
    if use_pubmed:
        pubmed_email = st.text_input("PubMed Email (Required by NCBI):", placeholder="your.email@example.com")
        
    scopus_key = ""
    if use_scopus:
        scopus_key = st.text_input("Scopus API Key (Institutional):", type="password")
    
    if st.button("Run Multi-Database Search", type="primary"):
        if search_query.strip() == "":
            st.warning("Please enter a keyword before searching.")
        elif use_pubmed and not pubmed_email:
            st.warning("Please enter an email address for PubMed access.")
        elif use_scopus and not scopus_key:
            st.warning("Please enter a Scopus API Key.")
        else:
            all_results = []
            
            with st.spinner("Querying selected databases... This may take a minute."):
                if use_openalex:
                    st.toast("Querying OpenAlex...")
                    all_results.append(search_openalex(search_query, max_results_limit))
                if use_pubmed:
                    st.toast("Querying PubMed...")
                    all_results.append(search_pubmed(search_query, max_results_limit, pubmed_email))
                if use_s2:
                    st.toast("Querying Semantic Scholar...")
                    all_results.append(search_semanticscholar(search_query, max_results_limit))
                if use_crossref:
                    st.toast("Querying Crossref...")
                    all_results.append(search_crossref(search_query, max_results_limit))
                if use_epmc:
                    st.toast("Querying Europe PMC...")
                    all_results.append(search_europepmc(search_query, max_results_limit))
                if use_scopus:
                    st.toast("Querying Scopus...")
                    all_results.append(search_scopus(search_query, max_results_limit, scopus_key))
                
                # Combine all dataframes
                combined_df = pd.concat([df for df in all_results if not df.empty], ignore_index=True)
                
                if not combined_df.empty:
                    # Basic initial deduplication by DOI (keeps the first occurrence)
                    initial_count = len(combined_df)
                    combined_df = combined_df.drop_duplicates(subset=['DOI'], keep='first')
                    # Put back papers that had "No DOI" since they were wrongly deduplicated
                    no_dois = combined_df[combined_df['DOI'] == "No DOI"]
                    has_dois = combined_df[combined_df['DOI'] != "No DOI"]
                    combined_df = pd.concat([has_dois, no_dois], ignore_index=True)
                    
                    st.session_state['raw_results'] = combined_df
                    st.success(f"Successfully retrieved {initial_count} total records. After basic DOI deduplication, {len(combined_df)} unique records remain!")
                else:
                    st.info("No results found across the selected databases.")

    if 'raw_results' in st.session_state:
        st.write("### Current Search Results")
        st.dataframe(st.session_state['raw_results'])

# ==========================================
# STEP 2: FILTER RESULTS
# ==========================================
elif step == "2. Filter Results":
    st.subheader("Step 2: Manually Filter 'Noise' from Results")
    
    if 'raw_results' not in st.session_state or st.session_state['raw_results'].empty:
        st.warning("No search results found. Please go back to Step 1 and run a search first.")
    else:
        st.write("Review your search results below. Uncheck the 'Keep' box for any papers you want to exclude.")
        
        search_filter = st.text_input("🔍 Filter table to specific records (e.g., 'GBIF'):", placeholder="Type to filter...")
        
        df_to_edit = st.session_state['raw_results']
        if search_filter:
            mask = df_to_edit.astype(str).apply(lambda col: col.str.contains(search_filter, case=False)).any(axis=1)
            display_df = df_to_edit[mask]
        else:
            display_df = df_to_edit
            
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            btn_label_1 = "Select Visible" if search_filter else "Select All"
            if st.button(btn_label_1, use_container_width=True):
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = True
                st.rerun()
                
        with col2:
            btn_label_2 = "Deselect Visible" if search_filter else "Deselect All"
            if st.button(btn_label_2, use_container_width=True):
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = False
                st.rerun()
                
        st.caption(f"Showing {len(display_df)} of {len(df_to_edit)} total records.")
        
        edited_display_df = st.data_editor(
            display_df,
            column_config={"Keep": st.column_config.CheckboxColumn("Keep?", default=True)},
            disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "Source"], 
            hide_index=True,
            use_container_width=True,
            height=500 
        )
        
        st.session_state['raw_results'].loc[edited_display_df.index, 'Keep'] = edited_display_df['Keep']
        
        if st.button("Save Filtered Results", type="primary"):
            master_df = st.session_state['raw_results']
            final_filtered_df = master_df[master_df["Keep"] == True].copy()
            final_filtered_df = final_filtered_df.drop(columns=["Keep"])
            st.session_state['filtered_results'] = final_filtered_df
            
            st.success(f"Filtered list saved! You kept {len(final_filtered_df)} out of {len(master_df)} total papers.")
            
        if 'filtered_results' in st.session_state:
            st.divider()
            st.write("### Current Curated List Preview")
            st.dataframe(st.session_state['filtered_results'], hide_index=True)

# ==========================================
# STEP 3: EXPORT DATA
# ==========================================
elif step == "3. Export Data (Optional Rayyan Route)":
    st.subheader("Step 3: Export Curated Results (Optional)")
    
    if 'filtered_results' not in st.session_state or st.session_state['filtered_results'].empty:
        st.warning("No filtered results found. Please go back to Step 2 and save your curated list first.")
    else:
        st.write("If you prefer to use **Rayyan** for your title/abstract screening, download your files below.")
        final_df = st.session_state['filtered_results']
        st.dataframe(final_df, hide_index=True)
        st.divider()
        st.write("### Download Options")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            csv_data = final_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="📄 Download Standard CSV", data=csv_data, file_name="PRISMA_filtered_results.csv", mime="text/csv", use_container_width=True)
            
        with col2:
            import io
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name="Filtered Papers")
            st.download_button(label="📊 Download Excel (.xlsx)", data=excel_buffer.getvalue(), file_name="PRISMA_filtered_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            
        with col3:
            rayyan_df = final_df.rename(columns={
                "Title": "title", "Author(s)": "authors", "Year": "year",
                "Journal": "journal", "Abstract": "abstract", "Keywords": "keywords", 
                "DOI": "url", "Source": "notes" # Map Source to Notes in Rayyan
            })
            rayyan_csv = rayyan_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="🔄 Download for Rayyan", data=rayyan_csv, file_name="Rayyan_Import.csv", mime="text/csv", use_container_width=True)

# ==========================================
# STEP 4: DEDUPLICATION & SCREENING
# ==========================================
elif step == "4. Deduplicate & Screen (In-App Route)":
    st.subheader("Step 4: Title & Abstract Screening (Rayyan Bypass)")
    
    if 'filtered_results' not in st.session_state or st.session_state['filtered_results'].empty:
        st.warning("No results found. Please complete Step 2 first.")
    else:
        if 'screening_data' not in st.session_state:
            df = st.session_state['filtered_results'].copy()
            df['Screening_Keep'] = True
            st.session_state['screening_data'] = df
        
        df_screen = st.session_state['screening_data']
        
        st.write("### 1. Deep Duplicate Checker")
        df_screen['temp_title'] = df_screen['Title'].str.lower().str.strip()
        
        # Find ALL duplicates to display them in the table
        title_dupes = df_screen.duplicated(subset=['temp_title'], keep=False)
        doi_dupes = df_screen.duplicated(subset=['DOI'], keep=False) & (df_screen['DOI'] != "No DOI")
        
        duplicates_df = df_screen[title_dupes | doi_dupes].sort_values(by=['temp_title'])
        
        if not duplicates_df.empty:
            st.warning(f"Found {len(duplicates_df)} potential duplicate records! They are grouped together below.")
            
            # --- NEW: AUTO-RESOLVE BUTTON ---
            if st.button("🤖 Auto-Resolve Duplicates (Keep First)", type="primary", help="Automatically unchecks redundant copies, keeping only one version of each paper."):
                # Find the duplicates but KEEP the first occurrence. 
                # This creates a mask of only the REDUNDANT rows that need to be thrown out.
                discard_title = df_screen.duplicated(subset=['temp_title'], keep='first')
                discard_doi = df_screen.duplicated(subset=['DOI'], keep='first') & (df_screen['DOI'] != "No DOI")
                
                # Set 'Screening_Keep' to False for all redundant rows
                st.session_state['screening_data'].loc[discard_title | discard_doi, 'Screening_Keep'] = False
                
                # Rerun the app to refresh the table UI
                st.rerun()
                
            st.write("Review the duplicates below. You can use the Auto-Resolve button above, or manually uncheck the 'Keep?' box for the versions you want to discard.")
            
            edited_dupes = st.data_editor(
                duplicates_df,
                column_config={"Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)},
                column_order=["Screening_Keep", "Title", "Author(s)", "Year", "Journal", "DOI", "Source"],
                disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "Source", "temp_title"],
                hide_index=True, use_container_width=True
            )
            # Sync any manual clicks back to the session state
            st.session_state['screening_data'].loc[edited_dupes.index, 'Screening_Keep'] = edited_dupes['Screening_Keep']
        else:
            st.success("No duplicates found!")
            
        st.divider()
        
        st.write("### 2. Keyword Screening (Title / Abstract / Keywords)")
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
            column_config={"Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)},
            column_order=["Screening_Keep", "Title", "Author(s)", "Year", "Abstract", "Keywords", "Source"],
            disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "Source", "temp_title"], 
            hide_index=True, use_container_width=True, height=500 
        )
        
        st.session_state['screening_data'].loc[edited_display_df.index, 'Screening_Keep'] = edited_display_df['Screening_Keep']
        
        if st.button("Save Final Screened Results", type="primary"):
            master_df = st.session_state['screening_data']
            final_screened_df = master_df[master_df["Screening_Keep"] == True].copy()
            final_screened_df = final_screened_df.drop(columns=["Screening_Keep", "temp_title"], errors="ignore")
            st.session_state['screened_results'] = final_screened_df
            st.success(f"Screening complete! You kept {len(final_screened_df)} out of {len(master_df)} papers.")
            
        if 'screened_results' in st.session_state:
            st.divider()
            st.write("### Final Curated List Ready")
            csv_data = st.session_state['screened_results'].to_csv(index=False).encode('utf-8')
            st.download_button(label="📄 Download Final Screened CSV", data=csv_data, file_name="PRISMA_Final_Screened.csv", mime="text/csv", use_container_width=True)
# ==========================================
# STEP 5: PDF LLM EXTRACTION
# ==========================================
elif step == "5. PDF LLM Extraction":
    st.subheader("Step 5: AI-Powered PDF Extraction")
    st.write("Upload a downloaded paper to automatically extract structured data.")
    
    api_key = st.text_input("Enter your Google Gemini API Key:", type="password", help="Get a free API key at aistudio.google.com")
    st.divider()
    
    research_subject = st.text_input("Target Species / Research Subject:", placeholder="e.g., Caretta caretta")
    uploaded_file = st.file_uploader("Upload a PDF paper", type="pdf")
    
    if 'extraction_history' not in st.session_state:
        st.session_state['extraction_history'] = []

    if st.button("Extract Data", type="primary"):
        if not api_key: st.error("Please enter your API Key first.")
        elif not research_subject: st.error("Please enter a research subject to guide the AI.")
        elif not uploaded_file: st.error("Please upload a PDF file.")
        else:
            with st.spinner("Analyzing PDF... (Running OCR, translation, and data extraction)"):
                try:
                    from google import genai
                    import tempfile
                    import os
                    
                    client = genai.Client(api_key=api_key)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name

                    gemini_file = client.files.upload(file=tmp_file_path)
                    
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

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[gemini_file, prompt]
                    )
                    
                    client.files.delete(name=gemini_file.name)
                    os.remove(tmp_file_path)
                    
                    st.success("Extraction Complete!")
                    st.markdown("### Extracted Result")
                    st.markdown(response.text)
                    st.session_state['extraction_history'].append(response.text)
                    
                except Exception as e:
                    st.error(f"An error occurred during extraction: {e}")

    if st.session_state.get('extraction_history'):
        st.divider()
        st.write(f"### Current Session Extractions ({len(st.session_state['extraction_history'])} papers processed)")
        for idx, res in enumerate(st.session_state['extraction_history']):
            st.markdown(res)
