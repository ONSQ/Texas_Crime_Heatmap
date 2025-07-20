import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import os

# --- DATA LOADING ---
@st.cache_resource
def load_data():
    # Load Excel data (assume sheet name and multi-level headers as in your script)
    df = pd.read_excel(
        "Texas_Offense_Type_by_Agency_2023.xlsx",
        sheet_name="2023 TX",
        header=[0, 1]
    )

    # Flatten multi-index columns for ease
    df.columns = ['_'.join([str(i) for i in col]).strip('_') for col in df.columns.values]
    return df

@st.cache_resource
def load_places():
    gdf = gpd.read_file("tl_2023_48_place.shp")
    gdf["centroid"] = gdf.geometry.centroid
    return gdf

# --- APP LOGIC ---
st.set_page_config(layout="wide")
st.title("Texas Crime Rate Interactive Heatmap")
st.caption("Search Texas cities and visualize crime by offense type. Data: TX DPS 2023")

df = load_data()
gdf_places = load_places()

# Identify available crime types from your columns
crime_types = [col for col in df.columns if col.startswith("Crimes Against")]
st.sidebar.header("Filters")
crime_col = st.sidebar.selectbox("Choose crime category:", crime_types)

# Search bar
search_city = st.sidebar.text_input("Search for a Texas city:")

# --- PROCESS DATA ---
# Merge data and geometry
def get_city_latlon(name):
    row = gdf_places[gdf_places["NAME"].str.lower() == name.lower()]
    if not row.empty:
        return row.iloc[0]["centroid"].y, row.iloc[0]["centroid"].x
    else:
        return None, None

df["latitude"] = df["Agency Name_"].apply(lambda x: get_city_latlon(x)[0])
df["longitude"] = df["Agency Name_"].apply(lambda x: get_city_latlon(x)[1])
df_heat = df.dropna(subset=["latitude", "longitude"])

# --- MAP ---
st.subheader("Crime Heatmap")
m = folium.Map(location=[31.9686, -99.9018], zoom_start=6)
heat_data = [
    [row["latitude"], row["longitude"], row[crime_col]]
    for _, row in df_heat.iterrows()
    if pd.notnull(row[crime_col])
]

if heat_data:
    HeatMap(heat_data, radius=15, blur=10, max_zoom=9).add_to(m)
st_data = st_folium(m, width=900, height=600)

# --- CITY SEARCH + TABLES ---
if search_city:
    results = df[df["Agency Name"].str.lower().str.contains(search_city.lower())]
    if not results.empty:
        city = results.iloc[0]
        st.markdown(f"### {city['Agency Name']}")
        st.write(f"**{crime_col}**: {city[crime_col]:,.0f}")
        st.write(f"Coordinates: ({city['latitude']:.4f}, {city['longitude']:.4f})")
    else:
        st.warning("City not found. Try a different spelling?")

# Top/Bottom tables
st.subheader(f"Safest & Most Dangerous Cities by {crime_col}")
sorted_df = df_heat[["Agency Name", crime_col]].sort_values(by=crime_col)
col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Safest (Lowest Crime)")
    st.dataframe(sorted_df.head(10).reset_index(drop=True))
with col2:
    st.markdown("#### Most Dangerous (Highest Crime)")
    st.dataframe(sorted_df.tail(10).sort_values(by=crime_col, ascending=False).reset_index(drop=True))
