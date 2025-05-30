import osmnx as ox

# Set up logging and cache
ox.settings.log_console = True
ox.settings.use_cache = True

# Define your area of interest
place_name = "Las Condes, Santiago Metropolitan Region, Chile"

# Download the street network as a directed graph
G = ox.graph_from_place(place_name, network_type='drive')

# Plot the street network
ox.plot_graph(G)