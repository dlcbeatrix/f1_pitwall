#COMING SOON

"""import streamlit as st


if code not in RACE_LIKE:
    st.subheader(title)
    q = laps.dropna(subset=["LapTime"])
    if "Deleted" in q.columns:
        q = q[q["Deleted"]== False]
        
        if q.empty: 
            st.warning('No valid laps in this session')
            st.stop()
            
        q["Seconds"] = q["LapTime"].dt.total_seconds()
    
    best = q.sort_values("Seconds").drop_duplicates(subset="Driver")
    
    best["Gap"] = best["Seconds"] - best["Seconds"].min()
    
    #Bar chart, one bar per driver coloured by team and sorted by gap
    fig = px.bar(best, x="Driver", y="Gap", color = "Team", color_discrete_map= colors, labels={"Gap" : "Gap to fastest lap(s)"})
    fig.update_xaxes (categoryorder = "total ascending")
    st.plotly_chart(fig)
    
    st.caption("Tyre degradation is only available for races and sprints")
    st.stop()"""