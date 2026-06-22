import streamlit as st
import pandas as pd
import requests
import time
import io
import os
import tempfile
import re
from pyalex import Works
from Bio import Entrez

# Set the page configuration
st.set_page_config(page_title="PRISMA Automator", page_icon="📚", layout="wide")

st.title("📚 PRISMA Systematic Review Automator")
st.write("Welcome to your automated literature review pipeline.")

# Initialize PRISMA Statistics Tracker
if 'prisma_stats' not in st.session_state:
    st.session_state['prisma_stats'] = {
        'records_identified': 0,
        'duplicates_removed': 0,
        'step2_excluded': 0,
        'step4_excluded': 0,
        'final_included': 0
    }

# Sidebar Navigation
st.sidebar.header("Pipeline Steps")
step = st.sidebar.radio("Select a step:", [
    "1. Search Databases",
    "2. Filter Results",
    "3. Export Data (Optional)",
    "4. Deduplicate & Screen",
    "5. AI Extraction Dashboard",
    "6. Generate PRISMA Flowchart"
])

st.divider()

# ==========================================
# HELPER FUNCTIONS & DATABASE ENGINES
# ==========================================

def reconstruct_abstract(inverted_index):
    if not inverted_index or not isinstance(inverted_index, dict): return "No abstract available."
    word_index = [(pos, word) for word, positions in inverted_index.items() for pos in positions]
    word_index.sort(key=lambda x: x[0])
    return " ".join([word for pos, word in word_index])

def parse_markdown_table(md_text):
    """Parses the strict Markdown table returned by Gemini into a list of values."""
    lines = md_text.strip().split('\n')
    for line in lines:
        # Look for the data row (starts with |, doesn't contain ---, doesn't contain the header 'Study')
        if line.strip().startswith('|') and '---' not in line and 'Study' not in line:
            cols = [c.strip() for c in line.split('|')[1:-1]]
            if len(cols) == 5:
                return cols
    return None

def download_pdf(url):
    """Attempts to download a PDF from an Open Access URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10, stream=True)
        # Check if the response is actually a PDF and not a publisher's HTML landing page
        if 'application/pdf' in response.headers.get('Content-Type', '').lower():
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)
            tmp_file.close()
            return tmp_file.name
    except Exception:
        pass
    return None

def search_openalex(query, max_results):
    try:
        base_query = Works().search(query)
        data, page, per_page = [], 1, 100
        max_pages = (max_results // per_page) + (1 if max_results % per_page > 0 else 0)
        
        while page <= max_pages:
            batch, meta = base_query.get(return_meta=True, per_page=per_page, page=page)
            if not batch: break
                
            for res in batch:
                if not isinstance(res, dict): continue
                authorships = res.get("authorships") or []
                author_names = [a.get("author", {}).get("display_name") for a in authorships if a.get("author", {}).get("display_name")]
                journal_name = res.get("primary_location", {}).get("source", {}).get("display_name") or "Unknown Journal"
                
                # Extract Open Access PDF URL if available
                oa_url = res.get("open_access", {}).get("oa_url")
                
                data.append({
                    "Keep": True, "Title": str(res.get("title") or "No Title"),
                    "Author(s)": ", ".join(author_names) if author_names else "Unknown Authors",
                    "Year": str(res.get("publication_year") or "N/A"),
                    "Journal": str(journal_name), 
                    "Abstract": str(reconstruct_abstract(res.get("abstract_inverted_index"))),
                    "Keywords": "; ".join([kw.get("display_name") for kw in res.get("keywords", []) if kw.get("display_name")]) or "N/A", 
                    "DOI": str(res.get("doi") or "No DOI"),
                    "PDF_URL": oa_url, "Source": "OpenAlex"
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
                
                doi, pmc_url = "No DOI", None
                for article_id in pubmed_article.get('PubmedData', {}).get('ArticleIdList', []):
                    if article_id.attributes.get('IdType') == 'doi':
                        doi = f"https://doi.org/{str(article_id)}"
                    elif article_id.attributes.get('IdType') == 'pmc':
                        # Construct direct EuropePMC PDF link using the PMC ID
                        pmc_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={str(article_id).upper()}&blobtype=pdf"
                        
                data.append({
                    "Keep": True, "Title": title, 
                    "Author(s)": ", ".join([f"{a.get('LastName', '')} {a.get('Initials', '')}".strip() for a in article.get('AuthorList', []) if isinstance(a, dict)]) or "Unknown",
                    "Year": year, "Journal": article.get('Journal', {}).get('Title', 'Unknown Journal'), 
                    "Abstract": " ".join([str(a) for a in article.get('Abstract', {}).get('AbstractText', [])]) or "N/A",
                    "Keywords": "; ".join([str(k) for k in medline.get('KeywordList', [[]])[0]]) if medline.get('KeywordList') else "N/A", 
                    "DOI": doi, "PDF_URL": pmc_url, "Source": "PubMed"
                })
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"PubMed Error: {e}")
        return pd.DataFrame()

def search_semanticscholar(query, max_results):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    data, offset = [], 0
    try:
        while len(data) < max_results:
            params = {"query": query, "limit": min(100, max_results - len(data)), "offset": offset, "fields": "title,authors,year,venue,abstract,externalIds,openAccessPdf"}
            res = requests.get(url, params=params).json()
            if 'data' not in res or not res['data']: break
            
            for item in res['data']:
                doi = item.get('externalIds', {}).get('DOI')
                oa_url = item.get('openAccessPdf', {}).get('url') if item.get('openAccessPdf') else None
                
                data.append({
                    "Keep": True, "Title": item.get('title', 'No Title'),
                    "Author(s)": ", ".join([a.get('name', '') for a in item.get('authors', [])]) or "Unknown",
                    "Year": str(item.get('year', 'N/A')), "Journal": item.get('venue', 'Unknown Journal') or "Unknown Journal",
                    "Abstract": item.get('abstract') or "N/A", "Keywords": "N/A", 
                    "DOI": f"https://doi.org/{doi}" if doi else "No DOI",
                    "PDF_URL": oa_url, "Source": "Semantic Scholar"
                })
            offset += 100
            time.sleep(0.5)
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Semantic Scholar Error: {e}")
        return pd.DataFrame()

# ==========================================
# STEP 1: SEARCH DATABASES
# ==========================================
if step == "1. Search Databases":
    st.subheader("Step 1: Search Literature Databases")
    
    search_query = st.text_input("Enter your search keywords:", placeholder="e.g., 'Microplastic ingestion sea turtles'")
    max_results_limit = st.slider("Max results PER DATABASE:", min_value=100, max_value=2000, value=500, step=100)
    
    col1, col2 = st.columns(2)
    with col1:
        use_openalex = st.checkbox("OpenAlex (Multidisciplinary)", value=True)
        use_pubmed = st.checkbox("PubMed (Life Sciences/Medicine)", value=True)
    with col2:
        use_s2 = st.checkbox("Semantic Scholar (AI Graph)", value=True)
        pubmed_email = st.text_input("PubMed Email (Required by NCBI):", placeholder="your.email@example.com") if use_pubmed else ""
    
    if st.button("Run Multi-Database Search", type="primary"):
        if not search_query.strip(): st.warning("Please enter a keyword.")
        elif use_pubmed and not pubmed_email: st.warning("Please enter an email for PubMed.")
        else:
            all_results = []
            with st.spinner("Querying databases & extracting Open Access links..."):
                if use_openalex: all_results.append(search_openalex(search_query, max_results_limit))
                if use_pubmed: all_results.append(search_pubmed(search_query, max_results_limit, pubmed_email))
                if use_s2: all_results.append(search_semanticscholar(search_query, max_results_limit))
                
                combined_df = pd.concat([df for df in all_results if not df.empty], ignore_index=True)
                
                if not combined_df.empty:
                    # Basic DOI deduplication
                    combined_df = combined_df.drop_duplicates(subset=['DOI'], keep='first')
                    no_dois = combined_df[combined_df['DOI'] == "No DOI"]
                    has_dois = combined_df[combined_df['DOI'] != "No DOI"]
                    combined_df = pd.concat([has_dois, no_dois], ignore_index=True)
                    
                    st.session_state['raw_results'] = combined_df
                    st.session_state['prisma_stats']['records_identified'] = len(combined_df)
                    st.success(f"Found {len(combined_df)} unique records!")
                else:
                    st.info("No results found.")

    if 'raw_results' in st.session_state:
        st.dataframe(st.session_state['raw_results'], hide_index=True)

# ==========================================
# STEP 2: FILTER RESULTS
# ==========================================
elif step == "2. Filter Results":
    st.subheader("Step 2: Manually Filter 'Noise' from Results")
    
    if 'raw_results' not in st.session_state:
        st.warning("Please run a search in Step 1 first.")
    else:
        search_filter = st.text_input("🔍 Filter table to specific records (e.g., 'GBIF'):")
        df_to_edit = st.session_state['raw_results']
        
        display_df = df_to_edit[df_to_edit.astype(str).apply(lambda col: col.str.contains(search_filter, case=False)).any(axis=1)] if search_filter else df_to_edit
            
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if st.button("Select Visible", use_container_width=True):
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = True
                st.rerun()
        with col2:
            if st.button("Deselect Visible", use_container_width=True):
                st.session_state['raw_results'].loc[display_df.index, 'Keep'] = False
                st.rerun()
                
        edited_display_df = st.data_editor(
            display_df,
            column_config={"Keep": st.column_config.CheckboxColumn("Keep?", default=True), "PDF_URL": st.column_config.LinkColumn("OA Link")},
            disabled=["Title", "Author(s)", "Year", "Journal", "Abstract", "Keywords", "DOI", "Source", "PDF_URL"], 
            hide_index=True, use_container_width=True, height=400 
        )
        st.session_state['raw_results'].loc[edited_display_df.index, 'Keep'] = edited_display_df['Keep']
        
        if st.button("Save Filtered Results", type="primary"):
            master_df = st.session_state['raw_results']
            final_filtered_df = master_df[master_df["Keep"] == True].drop(columns=["Keep"])
            st.session_state['filtered_results'] = final_filtered_df
            
            # Update PRISMA Stats
            st.session_state['prisma_stats']['step2_excluded'] = len(master_df) - len(final_filtered_df)
            st.success(f"Saved! You kept {len(final_filtered_df)} papers.")

# ==========================================
# STEP 3: EXPORT DATA
# ==========================================
elif step == "3. Export Data (Optional)":
    st.subheader("Step 3: Export Curated Results")
    if 'filtered_results' not in st.session_state:
        st.warning("Please complete Step 2 first.")
    else:
        final_df = st.session_state['filtered_results']
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 Download CSV", data=final_df.to_csv(index=False).encode('utf-8'), file_name="PRISMA_filtered.csv", mime="text/csv", use_container_width=True)
        with col2:
            rayyan_df = final_df.rename(columns={"Title": "title", "Author(s)": "authors", "Year": "year", "Journal": "journal", "Abstract": "abstract", "DOI": "url", "Source": "notes"})
            st.download_button("🔄 Download for Rayyan", data=rayyan_df.to_csv(index=False).encode('utf-8'), file_name="Rayyan_Import.csv", mime="text/csv", use_container_width=True)

# ==========================================
# STEP 4: DEDUPLICATE & SCREEN
# ==========================================
elif step == "4. Deduplicate & Screen":
    st.subheader("Step 4: Title & Abstract Screening")
    
    if 'filtered_results' not in st.session_state:
        st.warning("Please complete Step 2 first.")
    else:
        if 'screening_data' not in st.session_state:
            df = st.session_state['filtered_results'].copy()
            df['Screening_Keep'] = True
            st.session_state['screening_data'] = df
        
        df_screen = st.session_state['screening_data']
        df_screen['temp_title'] = df_screen['Title'].str.lower().str.strip()
        
        st.write("### 1. Deep Duplicate Checker")
        title_dupes = df_screen.duplicated(subset=['temp_title'], keep=False)
        doi_dupes = df_screen.duplicated(subset=['DOI'], keep=False) & (df_screen['DOI'] != "No DOI")
        duplicates_df = df_screen[title_dupes | doi_dupes].sort_values(by=['temp_title'])
        
        if not duplicates_df.empty:
            st.warning(f"Found {len(duplicates_df)} potential duplicate records!")
            if st.button("🤖 Auto-Resolve Duplicates (Keep First)", type="primary"):
                discard_mask = df_screen.duplicated(subset=['temp_title'], keep='first') | (df_screen.duplicated(subset=['DOI'], keep='first') & (df_screen['DOI'] != "No DOI"))
                st.session_state['screening_data'].loc[discard_mask, 'Screening_Keep'] = False
                
                # Update PRISMA Stats
                st.session_state['prisma_stats']['duplicates_removed'] = discard_mask.sum()
                st.rerun()
                
            edited_dupes = st.data_editor(duplicates_df, column_config={"Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)}, disabled=["Title", "Author(s)", "Year", "Journal", "DOI", "Source", "temp_title", "PDF_URL", "Abstract", "Keywords"], hide_index=True, use_container_width=True)
            st.session_state['screening_data'].loc[edited_dupes.index, 'Screening_Keep'] = edited_dupes['Screening_Keep']
        else:
            st.success("No duplicates found!")
            
        st.divider()
        st.write("### 2. Keyword Screening")
        search_filter = st.text_input("🔍 Search for keywords (e.g., 'microplastic'):")
        display_df = df_screen[df_screen[['Title', 'Abstract', 'Keywords']].astype(str).apply(lambda col: col.str.contains(search_filter, case=False)).any(axis=1)] if search_filter else df_screen
            
        edited_display_df = st.data_editor(display_df, column_config={"Screening_Keep": st.column_config.CheckboxColumn("Keep?", default=True)}, disabled=["Title", "Author(s)", "Year", "Abstract", "Keywords", "Source", "temp_title", "PDF_URL", "DOI", "Journal"], hide_index=True, use_container_width=True, height=400)
        st.session_state['screening_data'].loc[edited_display_df.index, 'Screening_Keep'] = edited_display_df['Screening_Keep']
        
        if st.button("Save Final Screened Results", type="primary"):
            master_df = st.session_state['screening_data']
            final_screened_df = master_df[master_df["Screening_Keep"] == True].drop(columns=["Screening_Keep", "temp_title"], errors="ignore")
            st.session_state['screened_results'] = final_screened_df
            
            # Update PRISMA Stats
            st.session_state['prisma_stats']['step4_excluded'] = len(master_df) - len(final_screened_df) - st.session_state['prisma_stats']['duplicates_removed']
            st.session_state['prisma_stats']['final_included'] = len(final_screened_df)
            
            st.success(f"Screening complete! {len(final_screened_df)} papers moving to extraction.")

# ==========================================
# STEP 5: AI EXTRACTION DASHBOARD
# ==========================================
elif step == "5. AI Extraction Dashboard":
    st.subheader("Step 5: AI Extraction Dashboard")
    
    if 'screened_results' not in st.session_state:
        st.warning("Please complete Step 4 first.")
    else:
        # Initialize extraction tracking
        if 'extraction_status' not in st.session_state:
            df = st.session_state['screened_results'].copy()
            df['Status'] = "Pending"
            st.session_state['extraction_status'] = df
            st.session_state['extracted_data_matrix'] = []

        api_key = st.text_input("Enter your Google Gemini API Key:", type="password")
        research_subject = st.text_input("Target Species / Research Subject:", placeholder="e.g., Caretta caretta")
        
        st.write("### Extraction To-Do List")
        status_df = st.session_state['extraction_status']
        st.dataframe(status_df[['Status', 'Title', 'Author(s)', 'Year', 'PDF_URL']], hide_index=True, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        # --- FEATURE: AUTO-FETCH OPEN ACCESS ---
        with col1:
            st.write("#### Auto-Process Open Access")
            if st.button("🤖 Auto-Fetch & Extract OA Papers", type="primary"):
                if not api_key or not research_subject:
                    st.error("API Key and Research Subject required.")
                else:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    
                    pending_oa = status_df[(status_df['Status'] == 'Pending') & (status_df['PDF_URL'].notna())]
                    
                    if pending_oa.empty:
                        st.info("No pending Open Access papers found.")
                    else:
                        progress_bar = st.progress(0)
                        for i, (idx, row) in enumerate(pending_oa.iterrows()):
                            st.toast(f"Fetching: {row['Title'][:30]}...")
                            pdf_path = download_pdf(row['PDF_URL'])
                            
                            if pdf_path:
                                try:
                                    gemini_file = client.files.upload(file=pdf_path)
                                    prompt = f"""You are an expert researcher. Extract data related to [{research_subject}].
                                    Output strictly as a Markdown table with 5 columns: Study, Country, Original Language, Primary Theme, Key Finding.
                                    Primary Theme MUST be one of: "Taxonomy & Morphology", "Distribution & Habitat Preferences", "Ecology & Behavior", "Conservation & Threats".
                                    Only output the 1-row table."""
                                    
                                    response = client.models.generate_content(model='gemini-2.5-flash', contents=[gemini_file, prompt])
                                    client.files.delete(name=gemini_file.name)
                                    os.remove(pdf_path)
                                    
                                    parsed_data = parse_markdown_table(response.text)
                                    if parsed_data:
                                        st.session_state['extracted_data_matrix'].append([row['Title']] + parsed_data)
                                        st.session_state['extraction_status'].at[idx, 'Status'] = "✅ Success"
                                    else:
                                        st.session_state['extraction_status'].at[idx, 'Status'] = "⚠️ Parse Error"
                                except Exception as e:
                                    st.session_state['extraction_status'].at[idx, 'Status'] = "❌ API Error"
                            else:
                                st.session_state['extraction_status'].at[idx, 'Status'] = "🔒 Paywalled (Manual)"
                            
                            progress_bar.progress((i + 1) / len(pending_oa))
                            time.sleep(2) # Prevent rate limiting
                        st.rerun()

        # --- FEATURE: MANUAL UPLOAD FALLBACK ---
        with col2:
            st.write("#### Manual Upload (Paywalled Papers)")
            pending_manual = status_df[status_df['Status'] != '✅ Success']
            if not pending_manual.empty:
                selected_paper = st.selectbox("Select a paper to upload:", pending_manual['Title'].tolist())
                uploaded_file = st.file_uploader("Upload PDF", type="pdf")
                
                if st.button("Extract Manual Upload"):
                    if not api_key or not research_subject or not uploaded_file:
                        st.error("Missing Key, Subject, or File.")
                    else:
                        with st.spinner("Extracting..."):
                            from google import genai
                            client = genai.Client(api_key=api_key)
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                tmp_file_path = tmp_file.name

                            gemini_file = client.files.upload(file=tmp_file_path)
                            prompt = f"""You are an expert researcher. Extract data related to [{research_subject}].
                            Output strictly as a Markdown table with 5 columns: Study, Country, Original Language, Primary Theme, Key Finding.
                            Primary Theme MUST be one of: "Taxonomy & Morphology", "Distribution & Habitat Preferences", "Ecology & Behavior", "Conservation & Threats".
                            Only output the 1-row table."""
                            
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=[gemini_file, prompt])
                            client.files.delete(name=gemini_file.name)
                            os.remove(tmp_file_path)
                            
                            parsed_data = parse_markdown_table(response.text)
                            if parsed_data:
                                st.session_state['extracted_data_matrix'].append([selected_paper] + parsed_data)
                                idx_to_update = status_df[status_df['Title'] == selected_paper].index[0]
                                st.session_state['extraction_status'].at[idx_to_update, 'Status'] = "✅ Success"
                                st.success("Extraction successful!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Failed to parse AI output into table.")
            else:
                st.success("All papers successfully extracted!")

        # --- FEATURE: FINAL DATA MATRIX EXPORT ---
        st.divider()
        st.write("### Final Extracted Data Matrix")
        if st.session_state['extracted_data_matrix']:
            matrix_df = pd.DataFrame(st.session_state['extracted_data_matrix'], columns=["Original Title", "Study", "Country", "Original Language", "Primary Theme", "Key Finding"])
            st.dataframe(matrix_df, hide_index=True)
            
            csv_data = matrix_df.to_csv(index=False).encode('utf-8')
            st.download_button("📊 Download Final Data Matrix (CSV)", data=csv_data, file_name="Final_Extraction_Matrix.csv", mime="text/csv", type="primary")

# ==========================================
# STEP 6: PRISMA FLOWCHART
# ==========================================
elif step == "6. Generate PRISMA Flowchart":
    st.subheader("Step 6: Automated PRISMA Flow Diagram")
    st.write("This diagram is generated automatically based on your actions in the previous steps.")
    
    stats = st.session_state['prisma_stats']
    
    # Create the Graphviz DOT string
    dot_string = f"""
    digraph PRISMA {{
        node [shape=box, fontname="Helvetica", fontsize=10, style="rounded,filled", fillcolor="#f9f9f9", color="#333333"];
        edge [fontname="Helvetica", fontsize=10, color="#666666"];
        
        Identification [label="Records identified from databases\\n(n = {stats['records_identified']})", fillcolor="#d4edda"];
        Duplicates [label="Records removed before screening:\\nDuplicate records removed (n = {stats['duplicates_removed']})", fillcolor="#f8d7da"];
        Screening1 [label="Records screened manually (Step 2)\\n(n = {stats['records_identified'] - stats['duplicates_removed']})"];
        Excluded1 [label="Records excluded manually\\n(n = {stats['step2_excluded']})", fillcolor="#f8d7da"];
        Screening2 [label="Records sought for retrieval (Step 4)\\n(n = {stats['records_identified'] - stats['duplicates_removed'] - stats['step2_excluded']})"];
        Excluded2 [label="Records excluded via Keyword/Abstract\\n(n = {stats['step4_excluded']})", fillcolor="#f8d7da"];
        Included [label="Studies included in review\\n(n = {stats['final_included']})", fillcolor="#d1ecf1"];
        
        Identification -> Duplicates [label=" Deduplication"];
        Identification -> Screening1;
        Screening1 -> Excluded1 [label=" Excluded"];
        Screening1 -> Screening2;
        Screening2 -> Excluded2 [label=" Excluded"];
        Screening2 -> Included;
        
        {{rank=same; Screening1 Excluded1}}
        {{rank=same; Screening2 Excluded2}}
    }}
    """
    
    # Render the flowchart natively in Streamlit
    st.graphviz_chart(dot_string, use_container_width=True)
    
    st.info("💡 **Tip:** You can right-click the image above and select 'Save Image As...' to download it for your publication.")
