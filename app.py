import streamlit as st

from src.data import (enable_cache)

st.set_page_config(page_title='F1 Pit Wall', layout= 'wide', page_icon=":material/sports_score:", initial_sidebar_state= "expanded")
enable_cache()

home_page = st.Page("views/home.py", title = "Home", icon = ":material/home:")
tyre_deg_page = st.Page("views/tyre_degradation.py", title="Tyre Degradation", icon=":material/tire_repair:")
noisy_page = st.Page("views/noisy_radio.py", title="The Noisy Radio", icon=":material/settings_input_antenna:")
quali_gap_page =st.Page("views/quali_gap.py", title="Qualifying Gap", icon=":material/timer:")

pg = st.navigation([home_page, tyre_deg_page, noisy_page, quali_gap_page])
pg.run()


