# Configuration settings for the Texas Crime Heatmap App

# Data Files
DATA_FILES = {
    2023: "TexasCrimeDataCities.csv",
    # Add future years here, e.g.:
    # 2022: "TexasCrime2022.csv",
}
# Default to the latest year
DEFAULT_YEAR = max(DATA_FILES.keys())
LAND_AREA_FILE = "LandAreaTX2.csv"
SHAPEFILE = "tl_2023_48_place.shp"

# Map Settings
DEFAULT_LAT = 31.4
DEFAULT_LON = -99.9013
DEFAULT_ZOOM = 6
CITY_ZOOM = 10

# Prediction Settings
DEFAULT_GROWTH_RATE = 0.05

# Columns to Exclude from Crime Analysis
EXCLUDE_COLS = {
    "Agency", "Agency Type", "Population", "land", "land area", 
    "latitude", "longitude", "INTPTLAT", "INTPTLONG", 
    "centroid", "city", "Population Density"
}
