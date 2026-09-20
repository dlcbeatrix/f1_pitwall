import streamlit as st

st.title("🏎️ F1 Pit Wall Dashboard")
st.write("Select what you want to analyse:")

col1, col2, col3, col4 = st.columns(4)

with col1: 
    if st.button("Tyre Degradation", icon = ":material/tire_repair:", use_container_width=True):
        st.switch_page("views/tyre_degradation.py")

with col2: 
    if st.button("Qualifying Gap", icon= ":material/timer:", use_container_width=True):
        st.switch_page("views/quali_gap.py")
    
with col3: 
    if st.button("The Noisy Radio", icon= ":material/settings_input_antenna:", use_container_width=True):
        st.switch_page("views/noisy_radio.py")
        
with col4: 
    if st.button("Coming soon", icon= ":material/upcoming:", use_container_width=True):
        pass