import streamlit as st

st.set_page_config(page_title='F1 Pit Wall', layout= 'wide')

#Main page title
st.title('F1 Pit Wall Dashboard')

#Sidebar setup 
st.sidebar.header('Session Controls')
st.sidebar.info('Year, Race and driver selection will be placed here')

#Main area placeholder
st.write('Welcome to the pit wall')