import streamlit as st

from src.data import (enable_cache)

st.set_page_config(page_title='F1 Pit Wall', layout= 'wide', icon=":material/sports_score")
enable_cache()

home_page = st.Page("views/home.py", title = "Home", icon = ":material/home")
tyre_deg_page = st.Page("views/tyre_deg.py", title="Tyre Degradation", icon=":material/tire_repair:")

pg = st.navigation([home_page, tyre_deg_page])
pg.run()


