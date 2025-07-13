import streamlit as st
import fastf1
from fastf1 import plotting
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Enable FastF1 cache
import os
os.makedirs('cache', exist_ok=True)
fastf1.Cache.enable_cache('cache')

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
            # Function to format lap times to milliseconds
            def format_laptime(timedelta_obj):
                if pd.isna(timedelta_obj):
                    return "N/A"
                total_seconds = timedelta_obj.total_seconds()
                minutes = int(total_seconds // 60)
                seconds = total_seconds % 60
                return f"{minutes}:{seconds:06.3f}"

            st.subheader("All Lap Times")
            # Create a copy of the dataframe with formatted lap times
            display_laps = laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]].copy()
            display_laps["LapTime_Formatted"] = display_laps["LapTime"].apply(format_laptime)
            display_laps = display_laps.drop("LapTime", axis=1)
            display_laps = display_laps.rename(columns={"LapTime_Formatted": "LapTime"})
            # Reorder columns to put LapTime in the right position
            display_laps = display_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]]
            st.dataframe(display_laps.sort_values(by=["LapNumber", "Driver"]))

            st.subheader("Fastest Lap Per Driver")
            fastest_laps = laps.pick_fastest()
            # Format fastest lap times
            display_fastest = fastest_laps[["Driver", "LapTime", "Compound"]].copy()
            display_fastest["LapTime_Formatted"] = display_fastest["LapTime"].apply(format_laptime)
            display_fastest = display_fastest.drop("LapTime", axis=1)
            display_fastest = display_fastest.rename(columns={"LapTime_Formatted": "LapTime"})
            display_fastest = display_fastest[["Driver", "LapTime", "Compound"]]
            st.dataframe(display_fastest.sort_values(by="LapTime"))

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
    st.title(f"F1 {year} Event Schedule")
    try:
        sched = fastf1.get_event_schedule(year)
        if sched.empty:
            st.warning("No schedule found for the selected year.")
        else:
            # Display the full schedule with better formatting
            st.subheader(f"All {len(sched)} races in {year}")

            # Select relevant columns for display
            display_columns = ['RoundNumber', 'EventName', 'Location', 'Country', 'EventDate', 'EventFormat']
            available_columns = [col for col in display_columns if col in sched.columns]

            # Format the dataframe for better readability
            schedule_df = sched[available_columns].copy()

            # Sort by round number
            schedule_df = schedule_df.sort_values('RoundNumber')

            # Display the schedule
            st.dataframe(
                schedule_df,
                use_container_width=True,
                hide_index=True
            )

            # Show some statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Races", len(sched))
            with col2:
                if 'EventDate' in sched.columns:
                    next_race = sched[sched['EventDate'] > datetime.now().date()]
                    if not next_race.empty:
                        st.metric("Next Race", next_race.iloc[0]['EventName'])
                    else:
                        st.metric("Next Race", "Season Complete")
            with col3:
                unique_countries = sched['Country'].nunique() if 'Country' in sched.columns else 0
                st.metric("Countries", unique_countries)

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
