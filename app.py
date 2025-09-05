import pandas as pd
import streamlit as st

st.title("Stock Analysis Dashboard")

# Temporary data
df = pd.DataFrame({
    "Stock": ["AAPL", "GOOG", "TSLA"],
    "Price": [150, 2800, 720],
    "Score": [85, 90, 75]
})

st.dataframe(df)


