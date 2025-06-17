from neo4j import GraphDatabase
import networkx as nx
from collections import defaultdict

# 1. Koneksi ke Neo4j
uri = "bolt://localhost:7687"
username = "neo4j"
password = "password"
driver = GraphDatabase.driver(uri, auth=(username, password))

# 2. Fetch relasi konflik
def fetch_conflicts():
    with driver.session() as session:
        session.run("""
            MATCH (m:User {role:'Mahasiswa'})-[:MENGAMBIL]->(c1:MataKuliah),
                  (m)-[:MENGAMBIL]->(c2:MataKuliah)
            WHERE c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_DENGAN]->(c2)
        """)
        session.run("""
            MATCH (d:User {role:'Dosen'})-[:MENGAJAR]->(c1:MataKuliah),
                  (d)-[:MENGAJAR]->(c2:MataKuliah)
            WHERE c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_DENGAN]->(c2)
        """)
        session.run("""
            MATCH (c1:MataKuliah), (c2:MataKuliah)
            WHERE c1.ruangan IS NOT NULL AND c1.ruangan = c2.ruangan AND c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_DENGAN]->(c2)
        """)
        result = session.run("""
            MATCH (c1:MataKuliah)-[:BERTABRAKAN_DENGAN]-(c2:MataKuliah)
            RETURN DISTINCT c1.kode AS mk1, c2.kode AS mk2
        """)
        return [(r["mk1"], r["mk2"]) for r in result]

# 3. Mapping dosen & ruangan
def fetch_mapping_dosen():
    with driver.session() as session:
        result = session.run("""
            MATCH (d:User {role:'Dosen'})-[:MENGAJAR]->(c:MataKuliah)
            RETURN c.kode AS kode, d.nama AS nama
        """)
        return {r["kode"]: r["nama"] for r in result}

def fetch_mapping_ruangan():
    with driver.session() as session:
        result = session.run("""
            MATCH (c:MataKuliah)
            RETURN c.kode AS kode, c.ruangan AS ruangan
        """)
        return {r["kode"]: r["ruangan"] for r in result}

# 3b. Fetch data jadwal
def fetch_jadwal_info():
    with driver.session() as session:
        result = session.run("""
            MATCH (c:MataKuliah)-[:DIJADWALKAN]->(j:Jadwal)
            RETURN c.kode AS kode, c.ruangan AS ruangan, 
                   j.jam_mulai AS jam_mulai, j.jam_selesai AS jam_selesai,
                   j.hari AS hari
        """)
        return {
            r["kode"]: {
                "ruangan": r["ruangan"],
                "jam_mulai": r["jam_mulai"],
                "jam_selesai": r["jam_selesai"],
                "hari": r["hari"]
            }
            for r in result
        }

# 4. DSATUR manual
def dsatur_manual_coloring(G, mk_to_dosen, mk_to_ruang):
    coloring = {}
    saturation = {node: 0 for node in G.nodes}
    degrees = dict(G.degree())

    def is_valid(coloring):
        used = set()
        for mk, slot in coloring.items():
            d = mk_to_dosen.get(mk)
            r = mk_to_ruang.get(mk)
            if (slot, d) in used or (slot, r) in used:
                return False, mk
            used.add((slot, d))
            used.add((slot, r))
        return True, None

    while len(coloring) < len(G.nodes):
        uncolored = [n for n in G.nodes if n not in coloring]
        node = max(uncolored, key=lambda n: (saturation[n], degrees[n]))

        neighbor_colors = {coloring[n] for n in G.neighbors(node) if n in coloring}
        color = 0
        while color in neighbor_colors:
            color += 1
        coloring[node] = color

        for neighbor in G.neighbors(node):
            if neighbor not in coloring:
                neighbor_colors = {coloring[n] for n in G.neighbors(neighbor) if n in coloring}
                saturation[neighbor] = len(neighbor_colors)

    while True:
        valid, conflict_mk = is_valid(coloring)
        if valid:
            return coloring
        max_slot = max(coloring.values())
        coloring[conflict_mk] = max_slot + 1

# 5. Bangun graf konflik
conflicts = fetch_conflicts()
G = nx.Graph()
G.add_edges_from(conflicts)

# 6. Fetch mapping tambahan
mk_to_dosen = fetch_mapping_dosen()
mk_to_ruang = fetch_mapping_ruangan()
mk_jadwal_info = fetch_jadwal_info()

# 7. Jalankan penjadwalan
final_coloring = dsatur_manual_coloring(G, mk_to_dosen, mk_to_ruang)

# 8. Cetak hasil akhir
print("=== Jadwal Akhir Mata Kuliah ===")
slot_map = defaultdict(list)
for mk, slot in final_coloring.items():
    info = mk_jadwal_info.get(mk, {})
    ruangan = info.get("ruangan", "-")
    jam_mulai = info.get("jam_mulai", "-")
    jam_selesai = info.get("jam_selesai", "-")
    hari = info.get("hari", "-")
    slot_map[slot].append((mk, hari, jam_mulai, jam_selesai, ruangan))

for slot in sorted(slot_map.keys()):
    print(f"\n• Slot {slot + 1}:")
    for mk, hari, jam_mulai, jam_selesai, ruangan in slot_map[slot]:
        print(f"  {mk} ({hari} {jam_mulai} - {jam_selesai}, Ruang {ruangan})")
