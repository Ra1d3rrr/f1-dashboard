import streamlit as st
import fastf1
from fastf1 import plotting
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Enable FastF1 cache
fastf1.Cache.enable_cache('cache')
plotting.setup_mpl()

# Auto-refresh every 30 seconds to simulate "live" lap times
st_autorefresh(interval=30 * 1000, key="datarefresh")

st.set_page_config(page_title="F1 Live Dashboard", layout="wide")

# Sidebar navigation
page = st.sidebar.selectbox("Select Page", ["Lap Times (Live)", "Event Schedule", "Track Status"])

# Sidebar inputs
year = st.sidebar.number_input("Year", min_value=2018, max_value=datetime.now().year, value=datetime.now().year)
round_number = st.sidebar.number_input("Round", min_value=1, max_value=23, value=1)

# Load session
@st.cache_data(ttl=20)  # Refresh cache every 20 seconds
def load_session(year, rnd):
    try:
        session = fastf1.get_session(year, rnd, 'R')
        session.load()
        return session
    except Exception as e:
        return None

session = load_session(year, round_number)

# -------- PAGE: LAP TIMES (LIVE) --------
if page == "Lap Times (Live)":
    st.title("Live Lap Times")

    if session:
        laps = session.laps

        if laps.empty:
            st.warning("No lap data available yet.")
        else:
            st.subheader("All Lap Times")
            st.dataframe(laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]].sort_values(by=["LapNumber", "Driver"]))

            st.subheader("Fastest Lap Per Driver")
            fastest_laps = laps.pick_fastest()
            st.dataframe(fastest_laps[["Driver", "LapTime", "Compound"]].sort_values(by="LapTime"))

            st.subheader("Lap Time Chart")
            fig, ax = plt.subplots(figsize=(10, 5))
            for drv in laps['Driver'].unique():
                dr_laps = laps.pick_driver(drv)
                ax.plot(dr_laps['LapNumber'], dr_laps['LapTime'].dt.total_seconds(), label=drv)
            ax.set_xlabel("Lap Number")
            ax.set_ylabel("Lap Time (s)")
            ax.legend()
            st.pyplot(fig)
    else:
        st.error("Could not load session. Try another round or year.")


# -------- PAGE: EVENT SCHEDULE --------
elif page == "Event Schedule":
    st.title("Event Schedule")
    try:
        sched = fastf1.get_event_schedule(year)
        race_event = sched[sched['RoundNumber'] == round_number]
        if race_event.empty:
            st.warning("No schedule found for selected round.")
        else:
            st.dataframe(race_event)
    except Exception as e:
        st.error(f"Could not load schedule: {e}")


# -------- PAGE: TRACK STATUS --------
elif page == "Track Status":
    st.title("Track Status & Race Control")
    if session:
        st.subheader("Track Status")
        try:
            status = session.track_status
            if status.empty:
                st.info("No track status available.")
            else:
                st.dataframe(status)
        except:
            st.warning("No track status data available.")

        st.subheader("Race Control Messages")
        try:
            rc = session.race_control_messages
            if rc.empty:
                st.info("No race control messages.")
            else:
                st.dataframe(rc)
        except:
            st.warning("No race control messages available.")
