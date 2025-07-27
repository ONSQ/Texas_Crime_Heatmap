import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from folium import CircleMarker, Tooltip
from streamlit_folium import st_folium
import os

# --- DATA LOADING ---
@st.cache_resource
def load_data():
    df = pd.read_csv("TexasCrimeDataCities.csv", header=0)
    df.columns = df.columns.str.strip().str.replace("\n", " ")
    return df

@st.cache_resource
def load_land_area():
    land_df = pd.read_csv("LandAreaTX2.csv")
    land_df.columns = land_df.columns.str.strip().str.replace("\n", " ")
    return land_df

@st.cache_resource
def load_places():
    gdf = gpd.read_file("tl_2023_48_place.shp")
    gdf["centroid"] = gdf.geometry.centroid
    return gdf

# --- APP LOGIC ---
st.set_page_config(layout="wide")
st.title("Texas Crime Rate Interactive Heatmap")
st.caption("Search Texas cities and visualize crime by offense type. Data: FBI NIBRS & TX DPS 2023")    
st.caption("Webapp by ONSQ (WGN273), Data crafting by Jushua Cherry")

df = load_data()
land_df = load_land_area()

# Merge land area data with crime data on 'Agency'
df = df.merge(land_df, how="left", left_on="Agency", right_on="city")

# Calculate population density
if "Population" in df.columns and "Land Area" in df.columns:
    df["Population Density"] = df["Population"] / df["Land Area"]
else:
    df["Population Density"] = None

# Calculate crime percentage columns (crime per population * 100)
exclude_cols = {"Agency", "Agency Type", "Population", "Land Area", "latitude", "longitude"}
for col in df.columns:
    if col not in exclude_cols and pd.api.types.is_numeric_dtype(df[col]):
        if "Population" in df.columns:
            df[f"{col} %"] = (df[col] / df["Population"]) * 100

gdf_places = load_places()

# Identify all numeric crime-related columns (absolute numbers only)
crime_types = [col for col in df.columns if col not in exclude_cols 
               and pd.api.types.is_numeric_dtype(df[col]) and "%" not in col]

if crime_types:
    crime_col = st.sidebar.selectbox("Choose crime category (absolute numbers):", sorted(crime_types))
else:
    st.error("No numeric crime category columns found in the dataset.")
    st.stop()

# Toggle for using % vs absolute
use_percentage = st.sidebar.checkbox("Use % (crime per population) for heatmap", value=False)
show_predictions = st.sidebar.checkbox("Show Predictions (next year)", value=False)


# Search bar
search_city = st.sidebar.text_input("Search for a Texas city:")

# --- PROCESS DATA ---
def get_city_latlon(name):
    row = gdf_places[gdf_places["NAME"].str.lower() == name.lower()]
    if not row.empty:
        return row.iloc[0]["centroid"].y, row.iloc[0]["centroid"].x
    else:
        return None, None

df["latitude"] = df["Agency"].apply(lambda x: get_city_latlon(str(x).strip())[0] if pd.notnull(x) else None)
df["longitude"] = df["Agency"].apply(lambda x: get_city_latlon(str(x).strip())[1] if pd.notnull(x) else None)

# Ensure numeric and drop rows without lat/lon or crime data
df[crime_col] = pd.to_numeric(df[crime_col], errors="coerce")
# Simple prediction: assume a fixed 5% growth for demo
df[f"{crime_col} Predicted"] = df[crime_col] * 1.05
df[f"{crime_col} % Predicted"] = df[f"{crime_col} Predicted"] / df["Population"] * 100
df_heat = df.dropna(subset=["latitude", "longitude", crime_col])

# --- MAP ---
st.subheader(f"    {crime_col} Heatmap")

avg_lat, avg_lon = 31.9686, -99.9018
zoom_level = 6

if search_city:
    results = df[df["Agency"].str.lower().str.contains(search_city.lower(), na=False)]
    if not results.empty:
        city = results.iloc[0]
        if pd.notnull(city["latitude"]) and pd.notnull(city["longitude"]):
            avg_lat, avg_lon = city["latitude"], city["longitude"]
            zoom_level = 10

m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom_level)

# Decide heatmap data: % or absolute
if use_percentage:
    percent_col = f"{crime_col} %"
    if percent_col not in df_heat.columns:
        st.error(f"No percentage data found for {crime_col}.")
        st.stop()

    heat_data = [
        [row["latitude"], row["longitude"], row[percent_col]]
        for _, row in df_heat.iterrows()
        if pd.notnull(row[percent_col]) and row[percent_col] > 0
    ]
else:
    heat_data = [
        [row["latitude"], row["longitude"], row[crime_col]]
        for _, row in df_heat.iterrows()
        if pd.notnull(row[crime_col]) and row[crime_col] > 0
    ]


# Add heatmap
if heat_data:
    HeatMap(
        heat_data,
        radius=15,
        blur=10,
        max_zoom=9,
        gradient={
            0.0: 'blue',
            0.2: 'green',
            0.4: 'yellow',
            0.6: 'orange',
            0.8: 'red',
            1.0: 'darkred'
        }
    ).add_to(m)

# Add invisible markers with tooltips for all cities
for _, row in df_heat.iterrows():
    abs_value = row[crime_col]
    percent_value = row.get(f"{crime_col} %", None)

    tooltip_text = f"<b>{row['Agency']}</b><br>"
    tooltip_text += f"Crime Total: {abs_value:,.0f}<br>"
    tooltip_text += f"Population: {int(row['Population']):,}<br>"
    if percent_value is not None and pd.notnull(percent_value):
        tooltip_text += f"% of population: {percent_value:.2f}%<br>"

    if show_predictions:
        predicted_value = row.get(f"{crime_col} Predicted", None)
        predicted_percent = row.get(f"{crime_col} % Predicted", None)
        if predicted_value is not None and pd.notnull(predicted_value):
            tooltip_text += f"<b>Predicted:</b> {predicted_value:,.0f}"
            if predicted_percent is not None:
                tooltip_text += f" ({predicted_percent:.2f}%)"

    CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=4,                  # Small, hoverable
        color="#00000000",         # Fully transparent border
        fill=True,
        fill_color="#000000",      # Very faint black dot
        fill_opacity=0.05,         # Almost invisible but hoverable
        tooltip=Tooltip(tooltip_text, sticky=True, direction="top")
    ).add_to(m)




st_data = st_folium(m, width=900, height=600)


# --- CITY SEARCH + TABLES ---
if search_city:
    results = df[df["Agency"].str.lower().str.contains(search_city.lower(), na=False)]
    if not results.empty:
        city = results.iloc[0]
        st.markdown(f"### {city['Agency']}")

        abs_value = city[crime_col]
        percent_col = f"{crime_col} %"
        percent_value = city[percent_col] if percent_col in city else None

        if pd.notnull(abs_value):
            st.write(f"**{crime_col} (Total):** {abs_value:,.0f}")

        if percent_value is not None and pd.notnull(percent_value):
            st.write(f"**{crime_col} (% of population):** {percent_value:.2f}%")

        if show_predictions:
            predicted_value = city.get(f"{crime_col} Predicted", None)
            predicted_percent = city.get(f"{crime_col} % Predicted", None)
            if pd.notnull(predicted_value):
                st.write(f"**Predicted Next Year:** {predicted_value:,.0f} ({predicted_percent:.2f}%)")
        if "Population" in city:
            st.write(f"**Population:** {int(city['Population']):,}")
        if "Population Density" in city and pd.notnull(city["Population Density"]):
            st.write(f"**Population Density:** {city['Population Density']:.1f} people per sq. mile")

        st.write(f"Coordinates: ({city['latitude']:.4f}, {city['longitude']:.4f})")
    else:
        st.warning("City not found. Try a different spelling?")

# Top/Bottom tables
st.subheader(f"Safest & Most Dangerous Cities by {crime_col}")
percent_col = f"{crime_col} %"
cols_to_show = ["Agency", crime_col]
if percent_col in df_heat.columns:
    cols_to_show.append(percent_col)
if show_predictions:
    cols_to_show.append(f"{crime_col} Predicted")
sorted_df = df_heat[cols_to_show].sort_values(by=crime_col)
col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Safest (Lowest Crime)")
    st.dataframe(sorted_df.head(10).reset_index(drop=True))
with col2:
    st.markdown("#### Most Dangerous (Highest Crime)")
    st.dataframe(sorted_df.tail(10).sort_values(by=crime_col, ascending=False).reset_index(drop=True))
