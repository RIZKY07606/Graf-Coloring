from neo4j import GraphDatabase
import networkx as nx

# Koneksi ke Neo4j
uri = "bolt://localhost:7687"  # atau sesuaikan dengan server-mu
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

# Hitung chromatic number (greedy coloring)
def greedy_chromatic_number(G):
    coloring = nx.coloring.greedy_color(G, strategy="largest_first")
    num_colors = max(coloring.values()) + 1  # warna dimulai dari 0
    return num_colors, coloring

# Eksekusi
G = build_graph()

print(f"Jumlah simpul (mata kuliah): {G.number_of_nodes()}")
print(f"Jumlah konflik (edge): {G.number_of_edges()}")

if G.number_of_nodes() == 0:
    print("⚠️ Graf kosong! Pastikan data dan relasi 'BERTABRAKAN_DENGAN' sudah dimasukkan.")
else:
    chromatic, coloring = greedy_chromatic_number(G)
    print(f"Chromatic Number (jumlah slot minimal): {chromatic}")
    print("Pewarnaan (slot tiap mata kuliah):")
    for node, color in coloring.items():
        print(f"  {node} => Slot {color + 1}")
