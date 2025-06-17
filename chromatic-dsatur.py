from neo4j import GraphDatabase
import networkx as nx

# Koneksi ke Neo4j
uri = "bolt://localhost:7687"
username = "neo4j"
password = "password"

driver = GraphDatabase.driver(uri, auth=(username, password))

# Query ambil konflik antar MataKuliah
CYTHER_QUERY = """
MATCH (c1:MataKuliah)-[:BERTABRAKAN_DENGAN]-(c2:MataKuliah)
RETURN DISTINCT c1.kode AS dari, c2.kode AS ke
"""

# Bangun graf dari hasil query
def build_graph():
    G = nx.Graph()
    with driver.session() as session:
        result = session.run(CYTHER_QUERY)
        for record in result:
            G.add_edge(record["dari"], record["ke"])
    return G

# DSatur Coloring Algorithm
def dsatur_coloring(G):
    coloring = {}
    uncolored = set(G.nodes)
    degrees = dict(G.degree)

    while uncolored:
        # Hitung saturasi untuk simpul tak berwarna
        saturations = {}
        for node in uncolored:
            neighbor_colors = {coloring[n] for n in G.neighbors(node) if n in coloring}
            saturations[node] = len(neighbor_colors)

        # Pilih node dengan saturasi tertinggi, kalau seri ambil derajat tertinggi
        max_sat = max(saturations.values())
        candidates = [n for n in uncolored if saturations[n] == max_sat]
        next_node = max(candidates, key=lambda n: degrees[n])

        # Tentukan warna minimum yang belum dipakai tetangga
        neighbor_colors = {coloring[n] for n in G.neighbors(next_node) if n in coloring}
        color = 0
        while color in neighbor_colors:
            color += 1

        coloring[next_node] = color
        uncolored.remove(next_node)

    num_colors = max(coloring.values()) + 1
    return num_colors, coloring

# Eksekusi
G = build_graph()

print(f"Jumlah simpul (mata kuliah): {G.number_of_nodes()}")
print(f"Jumlah konflik (edge): {G.number_of_edges()}")

if G.number_of_nodes() == 0:
    print("⚠️ Graf kosong! Pastikan data dan relasi 'BERTABRAKAN_DENGAN' sudah dimasukkan.")
else:
    chromatic, coloring = dsatur_coloring(G)
    print(f"Chromatic Number (jumlah slot minimal): {chromatic}")
    print("Pewarnaan (slot tiap mata kuliah):")
    for node, color in coloring.items():
        print(f"  {node} => Slot {color + 1}")
