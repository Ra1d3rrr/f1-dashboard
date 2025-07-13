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
page = st.sidebar.selectbox("Select Page", ["Lap Times (Live)", "Race Results", "Driver Standings", "Constructor Standings", "Event Schedule", "Track Status"])

# Sidebar inputs
year = st.sidebar.number_input("Year", min_value=2018, max_value=datetime.now().year, value=datetime.now().year)

# Get race schedule for dropdown
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_race_schedule(year):
    try:
        schedule = fastf1.get_event_schedule(year)
        if not schedule.empty:
            # Create race options with name and round number
            race_options = {}
            for _, race in schedule.iterrows():
                race_name = race.get('EventName', f'Round {race["RoundNumber"]}')
                round_num = race['RoundNumber']
                race_options[f"{race_name} ({round_num})"] = round_num
            return race_options
        return {}
    except:
        # Fallback to simple round numbers if schedule fails
        return {f"Round {i}": i for i in range(1, 24)}

race_options = get_race_schedule(year)
if race_options:
    # Default to first race if available
    default_race = list(race_options.keys())[0]
    selected_race = st.sidebar.selectbox("Select Race", options=list(race_options.keys()), index=0)
    round_number = race_options[selected_race]
else:
    # Fallback to number input if schedule loading fails
    round_number = st.sidebar.number_input("Round", min_value=1, max_value=23, value=1)

# Optimized session loading with better caching
@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes, hide spinner
def load_session_fast(year, rnd, session_type='R'):
    try:
        session = fastf1.get_session(year, rnd, session_type)
        # Only load what we need for better performance
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        return session
    except Exception as e:
        return None

# Load session with minimal data for basic info
@st.cache_data(ttl=600, show_spinner=False)  # Cache for 10 minutes
def load_session_minimal(year, rnd, session_type='R'):
    try:
        session = fastf1.get_session(year, rnd, session_type)
        # Load only basic session info, no lap data
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        return session
    except Exception as e:
        return None

# Ultra-fast session creation - no loading until needed
def create_session_reference(year, rnd, session_type):
    """Create session reference without loading any data"""
    try:
        return fastf1.get_session(year, rnd, session_type)
    except:
        return None

# Create session references only (no data loading)
session = create_session_reference(year, round_number, 'R')
qualifying_session = create_session_reference(year, round_number, 'Q')
sprint_session = create_session_reference(year, round_number, 'S')
sprint_qualifying_session = create_session_reference(year, round_number, 'SQ')

# Get event schedule for the selected round to show dates
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_event_info(year, rnd):
    try:
        sched = fastf1.get_event_schedule(year)
        event = sched[sched['RoundNumber'] == rnd]
        if not event.empty:
            return event.iloc[0]
        return None
    except Exception as e:
        return None

event_info = get_event_info(year, round_number)

# -------- PAGE: LAP TIMES (LIVE) --------
if page == "Lap Times (Live)":
    st.title("Live Lap Times")

    # Function to format lap times to milliseconds
    def format_laptime(timedelta_obj):
        if pd.isna(timedelta_obj):
            return "N/A"
        total_seconds = timedelta_obj.total_seconds()
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:06.3f}"

    # Determine if it's a Sprint weekend
    is_sprint_weekend = sprint_session is not None or sprint_qualifying_session is not None

    # Create tabs based on weekend format
    if is_sprint_weekend:
        tab1, tab2, tab3, tab4 = st.tabs(["Race", "Qualifying", "Sprint Race", "Sprint Qualifying"])
    else:
        tab1, tab2 = st.tabs(["Race", "Qualifying"])

    with tab1:
        st.subheader("Race Session")
        if session:
            # Cached session loading for better performance
            @st.cache_data(ttl=600, show_spinner=False)
            def load_race_laps(year, rnd):
                try:
                    race_session = fastf1.get_session(year, rnd, 'R')
                    race_session.load(laps=True, telemetry=False, weather=False, messages=False)
                    return race_session.laps
                except:
                    return pd.DataFrame()

            with st.spinner("Loading race data..."):
                laps = load_race_laps(year, round_number)

            if laps.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("No race lap data available yet.")
                else:
                    st.warning("No race lap data available yet.")
            else:
                st.subheader("All Race Lap Times")
                # Create a copy of the dataframe with formatted lap times
                display_laps = laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]].copy()
                display_laps["LapTime_Formatted"] = display_laps["LapTime"].apply(format_laptime)

                # Sort by lap number first, then by actual lap time within each lap (race order)
                display_laps = display_laps.sort_values(by=["LapNumber", "LapTime"])

                display_laps = display_laps.drop("LapTime", axis=1)
                display_laps = display_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                # Reorder columns to put LapTime in the right position
                display_laps = display_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]]
                st.dataframe(display_laps)

                st.subheader("Fastest Race Lap Per Driver")
                fastest_laps = laps.pick_fastest()
                # Check available columns and select appropriate ones
                available_cols = ["Driver", "LapTime"]
                if "Compound" in fastest_laps.columns:
                    available_cols.append("Compound")

                # Sort by actual lap time first (before formatting)
                display_fastest = fastest_laps[available_cols].copy().sort_values(by="LapTime")
                # Then format the lap times
                display_fastest["LapTime_Formatted"] = display_fastest["LapTime"].apply(format_laptime)
                display_fastest = display_fastest.drop("LapTime", axis=1)
                display_fastest = display_fastest.rename(columns={"LapTime_Formatted": "LapTime"})
                # Reorder columns to put LapTime in the right position
                final_cols = ["Driver", "LapTime"]
                if "Compound" in display_fastest.columns:
                    final_cols.append("Compound")
                display_fastest = display_fastest[final_cols]
                st.dataframe(display_fastest)

                st.subheader("Race Lap Time Chart")
                fig, ax = plt.subplots(figsize=(10, 5))
                for drv in laps['Driver'].unique():
                    dr_laps = laps.pick_driver(drv)
                    ax.plot(dr_laps['LapNumber'], dr_laps['LapTime'].dt.total_seconds(), label=drv)
                ax.set_xlabel("Lap Number")
                ax.set_ylabel("Lap Time (s)")
                ax.legend()
                st.pyplot(fig)
        else:
            if event_info is not None:
                event_date = event_info.get('EventDate', 'Unknown')
                event_name = event_info.get('EventName', 'Unknown Event')
                st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                st.error("Could not load race session. The race may not have started yet.")
            else:
                st.error("Could not load race session. Try another round or year.")

    with tab2:
        st.subheader("Qualifying Session")
        if qualifying_session:
            # Cached session loading for better performance
            @st.cache_data(ttl=600, show_spinner=False)
            def load_qualifying_laps(year, rnd):
                try:
                    quali_session = fastf1.get_session(year, rnd, 'Q')
                    quali_session.load(laps=True, telemetry=False, weather=False, messages=False)
                    return quali_session.laps
                except:
                    return pd.DataFrame()

            with st.spinner("Loading qualifying data..."):
                quali_laps = load_qualifying_laps(year, round_number)

            if quali_laps.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("No qualifying lap data available yet.")
                else:
                    st.warning("No qualifying lap data available yet.")
            else:
                st.subheader("All Qualifying Lap Times")
                # Create a copy of the dataframe with formatted lap times
                display_quali_laps = quali_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife"]].copy()
                display_quali_laps["LapTime_Formatted"] = display_quali_laps["LapTime"].apply(format_laptime)

                # Sort by lap number first, then by actual lap time within each lap
                display_quali_laps = display_quali_laps.sort_values(by=["LapNumber", "LapTime"])

                display_quali_laps = display_quali_laps.drop("LapTime", axis=1)
                display_quali_laps = display_quali_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                # Reorder columns to put LapTime in the right position
                display_quali_laps = display_quali_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife"]]
                st.dataframe(display_quali_laps)

                st.subheader("Fastest Qualifying Lap Per Driver")
                fastest_quali_laps = quali_laps.pick_fastest()
                # Check available columns and select appropriate ones
                available_cols = ["Driver", "LapTime"]
                if "Compound" in fastest_quali_laps.columns:
                    available_cols.append("Compound")

                # Sort by actual lap time first (before formatting)
                display_fastest_quali = fastest_quali_laps[available_cols].copy().sort_values(by="LapTime")
                # Then format the lap times
                display_fastest_quali["LapTime_Formatted"] = display_fastest_quali["LapTime"].apply(format_laptime)
                display_fastest_quali = display_fastest_quali.drop("LapTime", axis=1)
                display_fastest_quali = display_fastest_quali.rename(columns={"LapTime_Formatted": "LapTime"})
                # Reorder columns to put LapTime in the right position
                final_cols = ["Driver", "LapTime"]
                if "Compound" in display_fastest_quali.columns:
                    final_cols.append("Compound")
                display_fastest_quali = display_fastest_quali[final_cols]
                st.dataframe(display_fastest_quali)

                st.subheader("Qualifying Lap Time Chart")
                fig, ax = plt.subplots(figsize=(10, 5))
                for drv in quali_laps['Driver'].unique():
                    dr_laps = quali_laps.pick_driver(drv)
                    ax.plot(dr_laps['LapNumber'], dr_laps['LapTime'].dt.total_seconds(), label=drv)
                ax.set_xlabel("Lap Number")
                ax.set_ylabel("Lap Time (s)")
                ax.legend()
                st.pyplot(fig)
        else:
            if event_info is not None:
                event_date = event_info.get('EventDate', 'Unknown')
                event_name = event_info.get('EventName', 'Unknown Event')
                st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                st.error("Could not load qualifying session. Qualifying may not have started yet.")
            else:
                st.error("Could not load qualifying session. Try another round or year.")

    # Sprint Race Tab (only shown for Sprint weekends)
    if is_sprint_weekend:
        with tab3:
            st.subheader("Sprint Race Session")
            if sprint_session:
                # Cached session loading for better performance
                @st.cache_data(ttl=600, show_spinner=False)
                def load_sprint_laps(year, rnd):
                    try:
                        sprint_session = fastf1.get_session(year, rnd, 'S')
                        sprint_session.load(laps=True, telemetry=False, weather=False, messages=False)
                        return sprint_session.laps
                    except:
                        return pd.DataFrame()

                with st.spinner("Loading sprint race data..."):
                    sprint_laps = load_sprint_laps(year, round_number)

                if sprint_laps.empty:
                    if event_info is not None:
                        event_date = event_info.get('EventDate', 'Unknown')
                        event_name = event_info.get('EventName', 'Unknown Event')
                        st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                        st.warning("No sprint race lap data available yet.")
                    else:
                        st.warning("No sprint race lap data available yet.")
                else:
                    st.subheader("All Sprint Race Lap Times")
                    # Create a copy of the dataframe with formatted lap times
                    display_sprint_laps = sprint_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]].copy()
                    display_sprint_laps["LapTime_Formatted"] = display_sprint_laps["LapTime"].apply(format_laptime)

                    # Sort by lap number first, then by actual lap time within each lap (race order)
                    display_sprint_laps = display_sprint_laps.sort_values(by=["LapNumber", "LapTime"])

                    display_sprint_laps = display_sprint_laps.drop("LapTime", axis=1)
                    display_sprint_laps = display_sprint_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    display_sprint_laps = display_sprint_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife", "TrackStatus"]]
                    st.dataframe(display_sprint_laps)

                    st.subheader("Fastest Sprint Race Lap Per Driver")
                    fastest_sprint_laps = sprint_laps.pick_fastest()
                    # Check available columns and select appropriate ones
                    available_cols = ["Driver", "LapTime"]
                    if "Compound" in fastest_sprint_laps.columns:
                        available_cols.append("Compound")

                    # Sort by actual lap time first (before formatting)
                    display_fastest_sprint = fastest_sprint_laps[available_cols].copy().sort_values(by="LapTime")
                    # Then format the lap times
                    display_fastest_sprint["LapTime_Formatted"] = display_fastest_sprint["LapTime"].apply(format_laptime)
                    display_fastest_sprint = display_fastest_sprint.drop("LapTime", axis=1)
                    display_fastest_sprint = display_fastest_sprint.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    final_cols = ["Driver", "LapTime"]
                    if "Compound" in display_fastest_sprint.columns:
                        final_cols.append("Compound")
                    display_fastest_sprint = display_fastest_sprint[final_cols]
                    st.dataframe(display_fastest_sprint)

                    st.subheader("Sprint Race Lap Time Chart")
                    fig, ax = plt.subplots(figsize=(10, 5))
                    for drv in sprint_laps['Driver'].unique():
                        dr_laps = sprint_laps.pick_driver(drv)
                        ax.plot(dr_laps['LapNumber'], dr_laps['LapTime'].dt.total_seconds(), label=drv)
                    ax.set_xlabel("Lap Number")
                    ax.set_ylabel("Lap Time (s)")
                    ax.legend()
                    st.pyplot(fig)
            else:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.error("Could not load sprint race session. The sprint race may not have started yet.")
                else:
                    st.error("Could not load sprint race session. Try another round or year.")

        # Sprint Qualifying Tab
        with tab4:
            st.subheader("Sprint Qualifying Session")
            if sprint_qualifying_session:
                # Cached session loading for better performance
                @st.cache_data(ttl=600, show_spinner=False)
                def load_sprint_qualifying_laps(year, rnd):
                    try:
                        sprint_quali_session = fastf1.get_session(year, rnd, 'SQ')
                        sprint_quali_session.load(laps=True, telemetry=False, weather=False, messages=False)
                        return sprint_quali_session.laps
                    except:
                        return pd.DataFrame()

                with st.spinner("Loading sprint qualifying data..."):
                    sprint_quali_laps = load_sprint_qualifying_laps(year, round_number)

                if sprint_quali_laps.empty:
                    if event_info is not None:
                        event_date = event_info.get('EventDate', 'Unknown')
                        event_name = event_info.get('EventName', 'Unknown Event')
                        st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                        st.warning("No sprint qualifying lap data available yet.")
                    else:
                        st.warning("No sprint qualifying lap data available yet.")
                else:
                    st.subheader("All Sprint Qualifying Lap Times")
                    # Create a copy of the dataframe with formatted lap times
                    display_sprint_quali_laps = sprint_quali_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife"]].copy()
                    display_sprint_quali_laps["LapTime_Formatted"] = display_sprint_quali_laps["LapTime"].apply(format_laptime)

                    # Sort by lap number first, then by actual lap time within each lap
                    display_sprint_quali_laps = display_sprint_quali_laps.sort_values(by=["LapNumber", "LapTime"])

                    display_sprint_quali_laps = display_sprint_quali_laps.drop("LapTime", axis=1)
                    display_sprint_quali_laps = display_sprint_quali_laps.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    display_sprint_quali_laps = display_sprint_quali_laps[["Driver", "LapNumber", "LapTime", "Compound", "TyreLife"]]
                    st.dataframe(display_sprint_quali_laps)

                    st.subheader("Fastest Sprint Qualifying Lap Per Driver")
                    fastest_sprint_quali_laps = sprint_quali_laps.pick_fastest()
                    # Check available columns and select appropriate ones
                    available_cols = ["Driver", "LapTime"]
                    if "Compound" in fastest_sprint_quali_laps.columns:
                        available_cols.append("Compound")

                    # Sort by actual lap time first (before formatting)
                    display_fastest_sprint_quali = fastest_sprint_quali_laps[available_cols].copy().sort_values(by="LapTime")
                    # Then format the lap times
                    display_fastest_sprint_quali["LapTime_Formatted"] = display_fastest_sprint_quali["LapTime"].apply(format_laptime)
                    display_fastest_sprint_quali = display_fastest_sprint_quali.drop("LapTime", axis=1)
                    display_fastest_sprint_quali = display_fastest_sprint_quali.rename(columns={"LapTime_Formatted": "LapTime"})
                    # Reorder columns to put LapTime in the right position
                    final_cols = ["Driver", "LapTime"]
                    if "Compound" in display_fastest_sprint_quali.columns:
                        final_cols.append("Compound")
                    display_fastest_sprint_quali = display_fastest_sprint_quali[final_cols]
                    st.dataframe(display_fastest_sprint_quali)

                    st.subheader("Sprint Qualifying Lap Time Chart")
                    fig, ax = plt.subplots(figsize=(10, 5))
                    for drv in sprint_quali_laps['Driver'].unique():
                        dr_laps = sprint_quali_laps.pick_driver(drv)
                        ax.plot(dr_laps['LapNumber'], dr_laps['LapTime'].dt.total_seconds(), label=drv)
                    ax.set_xlabel("Lap Number")
                    ax.set_ylabel("Lap Time (s)")
                    ax.legend()
                    st.pyplot(fig)
            else:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.error("Could not load sprint qualifying session. Sprint qualifying may not have started yet.")
                else:
                    st.error("Could not load sprint qualifying session. Try another round or year.")


# -------- PAGE: RACE RESULTS --------
elif page == "Race Results":
    st.title("Race Results")

    if session:
        try:
            # Cached race results loading
            @st.cache_data(ttl=600, show_spinner=False)
            def load_race_results(year, rnd):
                try:
                    race_session = fastf1.get_session(year, rnd, 'R')
                    race_session.load(laps=False, telemetry=False, weather=False, messages=False)
                    return race_session.results
                except:
                    return pd.DataFrame()

            with st.spinner("Loading race results..."):
                results = load_race_results(year, round_number)
            if results.empty:
                if event_info is not None:
                    event_date = event_info.get('EventDate', 'Unknown')
                    event_name = event_info.get('EventName', 'Unknown Event')
                    st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
                    st.warning("Race results not available yet.")
                else:
                    st.warning("Race results not available yet.")
            else:
                st.subheader(f"Final Race Results - Round {round_number}")

                # Format the results for display
                display_results = results[["Position", "DriverNumber", "BroadcastName", "TeamName", "Time", "Status", "Points"]].copy()

                # Format the Time column to show proper race time
                def format_race_time(time_obj):
                    if pd.isna(time_obj):
                        return "N/A"
                    if hasattr(time_obj, 'total_seconds'):
                        total_seconds = time_obj.total_seconds()
                        hours = int(total_seconds // 3600)
                        minutes = int((total_seconds % 3600) // 60)
                        seconds = total_seconds % 60
                        if hours > 0:
                            return f"{hours}:{minutes:02d}:{seconds:06.3f}"
                        else:
                            return f"{minutes}:{seconds:06.3f}"
                    return str(time_obj)

                display_results["Time_Formatted"] = display_results["Time"].apply(format_race_time)
                display_results = display_results.drop("Time", axis=1)
                display_results = display_results.rename(columns={"Time_Formatted": "Time"})

                # Reorder columns
                display_results = display_results[["Position", "DriverNumber", "BroadcastName", "TeamName", "Time", "Status", "Points"]]

                st.dataframe(display_results, use_container_width=True, hide_index=True)

                # Show some race statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    finishers = len(results[results['Status'] == 'Finished'])
                    st.metric("Finishers", f"{finishers}/{len(results)}")
                with col2:
                    if not results.empty:
                        winner = results.iloc[0]['BroadcastName']
                        st.metric("Winner", winner)
                with col3:
                    dnfs = len(results[results['Status'] != 'Finished'])
                    st.metric("DNFs", dnfs)

        except Exception as e:
            st.error(f"Could not load race results: {e}")
    else:
        if event_info is not None:
            event_date = event_info.get('EventDate', 'Unknown')
            event_name = event_info.get('EventName', 'Unknown Event')
            st.info(f"🏁 **{event_name}** race weekend starts on **{event_date}**")
            st.error("Could not load race session. The race may not have started yet.")
        else:
            st.error("Could not load race session. Try another round or year.")


# -------- PAGE: DRIVER STANDINGS --------
elif page == "Driver Standings":
    st.title(f"Driver Championship Standings - {year}")

    try:
        # Get driver standings up to the current round
        @st.cache_data(ttl=300)  # Cache for 5 minutes
        def get_driver_standings(year, up_to_round):
            try:
                # Get all results up to the specified round
                all_results = []
                for rnd in range(1, up_to_round + 1):
                    try:
                        race_session = fastf1.get_session(year, rnd, 'R')
                        race_session.load()
                        if not race_session.results.empty:
                            race_results = race_session.results.copy()
                            race_results['Round'] = rnd
                            all_results.append(race_results)
                    except:
                        continue

                if not all_results:
                    return pd.DataFrame()

                # Combine all results
                combined_results = pd.concat(all_results, ignore_index=True)

                # Calculate championship standings
                standings = combined_results.groupby('BroadcastName')['Points'].sum().reset_index()
                standings = standings.sort_values('Points', ascending=False).reset_index(drop=True)
                standings['Position'] = range(1, len(standings) + 1)

                # Add team information from the latest round
                latest_results = all_results[-1] if all_results else pd.DataFrame()
                if not latest_results.empty:
                    team_info = latest_results[['BroadcastName', 'TeamName']].drop_duplicates()
                    standings = standings.merge(team_info, on='BroadcastName', how='left')

                return standings[['Position', 'BroadcastName', 'TeamName', 'Points']]

            except Exception as e:
                return pd.DataFrame()

        standings = get_driver_standings(year, round_number)

        if standings.empty:
            st.warning("No driver standings data available yet.")
        else:
            st.subheader(f"Championship Standings after Round {round_number}")
            st.dataframe(standings, use_container_width=True, hide_index=True)

            # Show championship leader info
            if len(standings) > 0:
                leader = standings.iloc[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Championship Leader", leader['BroadcastName'])
                with col2:
                    st.metric("Points", int(leader['Points']))
                with col3:
                    if len(standings) > 1:
                        gap = leader['Points'] - standings.iloc[1]['Points']
                        st.metric("Lead", f"{int(gap)} pts")
                    else:
                        st.metric("Lead", "N/A")

    except Exception as e:
        st.error(f"Could not load driver standings: {e}")


# -------- PAGE: CONSTRUCTOR STANDINGS --------
elif page == "Constructor Standings":
    st.title(f"Constructor Championship Standings - {year}")

    try:
        # Get constructor standings up to the current round
        @st.cache_data(ttl=300)  # Cache for 5 minutes
        def get_constructor_standings(year, up_to_round):
            try:
                # Get all results up to the specified round
                all_results = []
                for rnd in range(1, up_to_round + 1):
                    try:
                        race_session = fastf1.get_session(year, rnd, 'R')
                        race_session.load()
                        if not race_session.results.empty:
                            race_results = race_session.results.copy()
                            race_results['Round'] = rnd
                            all_results.append(race_results)
                    except:
                        continue

                if not all_results:
                    return pd.DataFrame()

                # Combine all results
                combined_results = pd.concat(all_results, ignore_index=True)

                # Calculate constructor standings
                constructor_standings = combined_results.groupby('TeamName')['Points'].sum().reset_index()
                constructor_standings = constructor_standings.sort_values('Points', ascending=False).reset_index(drop=True)
                constructor_standings['Position'] = range(1, len(constructor_standings) + 1)

                return constructor_standings[['Position', 'TeamName', 'Points']]

            except Exception as e:
                return pd.DataFrame()

        constructor_standings = get_constructor_standings(year, round_number)

        if constructor_standings.empty:
            st.warning("No constructor standings data available yet.")
        else:
            st.subheader(f"Constructor Championship after Round {round_number}")
            st.dataframe(constructor_standings, use_container_width=True, hide_index=True)

            # Show constructor championship leader info
            if len(constructor_standings) > 0:
                leader = constructor_standings.iloc[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Leading Constructor", leader['TeamName'])
                with col2:
                    st.metric("Points", int(leader['Points']))
                with col3:
                    if len(constructor_standings) > 1:
                        gap = leader['Points'] - constructor_standings.iloc[1]['Points']
                        st.metric("Lead", f"{int(gap)} pts")
                    else:
                        st.metric("Lead", "N/A")

    except Exception as e:
        st.error(f"Could not load constructor standings: {e}")


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
