import streamlit as st
import pandas as pd

# Set the page configuration
st.set_page_config(page_title="PRISMA Automator", page_icon="📚", layout="wide")

# App Title
st.title("📚 PRISMA Systematic Review Automator")
st.write("Welcome to your automated literature review pipeline. Use the sidebar to navigate through the steps.")

# Sidebar Navigation (Skeleton for future steps)
st.sidebar.header("Pipeline Steps")
step = st.sidebar.radio("Select a step:", [
    "1. Search Databases",
    "2. Filter Results",
    "3. Export Data",
    "4. PDF LLM Extraction"
])

st.divider()

if step == "1. Search Databases":
    st.subheader("Step 1: Search Literature Databases (OpenAlex)")
    st.info("Search functionality will be built here next!")
