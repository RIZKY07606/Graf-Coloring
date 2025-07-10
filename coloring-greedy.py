from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from neo4j import GraphDatabase
import networkx as nx
from collections import defaultdict
import time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = "secretkey"

# === Neo4j setup ===
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "admin123"))

def get_session():
    return driver.session(database="grafcoloring")

# === Login setup ===
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, uid, nama, role):
        self.id = uid
        self.nama = nama
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    with get_session() as s:
        r = s.run(
            "MATCH (u:User {id:$id}) RETURN u.id AS id, u.nama AS nama, u.role AS role",
            id=user_id
        ).single()
    if r:
        return User(r["id"], r["nama"], r["role"])
    return None

# === Graph Coloring Functions ===

def fetch_conflicts():
    with get_session() as session:
        session.run("MATCH (:MataKuliah)-[r:BERTABRAKAN_DOSEN]->(:MataKuliah) DELETE r")
        session.run("MATCH (:MataKuliah)-[r:BERTABRAKAN_MAHASISWA]->(:MataKuliah) DELETE r")
        session.run("MATCH (:MataKuliah)-[r:BERTABRAKAN_RUANGAN]->(:MataKuliah) DELETE r")

        # Mahasiswa
        session.run("""
            MATCH (m:User {role:'Mahasiswa'})-[:MENGAMBIL]->(c1:MataKuliah),
                  (m)-[:MENGAMBIL]->(c2:MataKuliah)
            WHERE c1 <> c2 AND c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_MAHASISWA]->(c2)
        """)
        # Dosen
        session.run("""
            MATCH (d:User {role:'Dosen'})-[:MENGAJAR]->(c1:MataKuliah),
                  (d)-[:MENGAJAR]->(c2:MataKuliah)
            WHERE c1 <> c2 AND c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_DOSEN]->(c2)
        """)
        # Ruangan
        session.run("""
            MATCH (c1:MataKuliah), (c2:MataKuliah)
            WHERE c1.ruangan IS NOT NULL AND c2.ruangan IS NOT NULL
              AND c1.ruangan = c2.ruangan AND c1.kode < c2.kode
            MERGE (c1)-[:BERTABRAKAN_RUANGAN]->(c2)
        """)
        result = session.run("""
            MATCH (c1:MataKuliah)-[r]->(c2:MataKuliah)
            WHERE type(r) IN ['BERTABRAKAN_MAHASISWA','BERTABRAKAN_DOSEN','BERTABRAKAN_RUANGAN']
            RETURN DISTINCT c1.kode AS mk1, c2.kode AS mk2
        """)
        return [(r["mk1"], r["mk2"]) for r in result]

def build_graph():
    start = time.time()
    G = nx.Graph()
    conflicts = fetch_conflicts()
    G.add_edges_from(conflicts)
    duration = time.time() - start
    return G, duration

# === GREEDY COLORING ===
def greedy_coloring(G):
    start = time.time()
    coloring = {}
    for node in G.nodes():
        neighbor_colors = {coloring[neighbor] for neighbor in G.neighbors(node) if neighbor in coloring}
        color = 0
        while color in neighbor_colors:
            color += 1
        coloring[node] = color
    chromatic_number = max(coloring.values()) + 1
    duration = time.time() - start
    return chromatic_number, coloring, duration

def slot_to_hari_jam(slot):
    if slot == 0:
        return "Senin", "08:00", "09:40"
    elif slot == 1:
        return "Selasa", "08:00", "09:40"
    elif slot == 2:
        return "Rabu", "08:00", "09:40"
    elif slot == 3:
        return "Kamis", "08:00", "09:40"
    else:
        return "Jumat", "08:00", "09:40"

def fetch_jadwal_info():
    data = defaultdict(list)
    with get_session() as session:
        result = session.run("""
            MATCH (c:MataKuliah)-[:DIJADWALKAN]->(j:Jadwal)
            RETURN c.kode AS kode, j.hari AS hari, 
                   j.jam_mulai AS jam_mulai, j.jam_selesai AS jam_selesai, 
                   j.slot AS slot, c.ruangan AS ruangan
        """)
        for r in result:
            data[int(r["slot"])].append({
                "kode": r["kode"],
                "hari": r["hari"],
                "jam_mulai": r["jam_mulai"],
                "jam_selesai": r["jam_selesai"],
                "ruangan": r["ruangan"]
            })
    return data

def render_colored_graph(G, coloring):
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(G, seed=42)
    colors = [coloring.get(node, 0) for node in G.nodes()]
    nx.draw(G, pos, with_labels=True, node_color=colors, cmap=plt.cm.Set3, node_size=800, font_size=10)
    plt.title("Visualisasi Pewarnaan Graf (Greedy)")
    img = io.BytesIO()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.read()).decode('utf-8')

# === Routes ===

@app.route("/")
@login_required
def jadwal():
    total_start = time.time()
    G, time_graph = build_graph()
    chromatic_num, pewarnaan, time_coloring = greedy_coloring(G)
    total_exec_time = time.time() - total_start
    graph_img = render_colored_graph(G, pewarnaan)
    latency = total_exec_time
    jumlah_konflik = G.number_of_edges()
    throughput = jumlah_konflik / latency if latency > 0 else 0

    return render_template("index.html",
        slot_map=fetch_jadwal_info(),
        jumlah_simpul=G.number_of_nodes(),
        jumlah_konflik=jumlah_konflik,
        chromatic_number=chromatic_num,
        pewarnaan=pewarnaan,
        nama=current_user.nama,
        role=current_user.role,
        exec_time=f"{total_exec_time:.4f} detik",
        exec_graph=f"{time_graph:.4f} detik",
        exec_coloring=f"{time_coloring:.4f} detik",
        graph_img=graph_img,
        latency=f"{latency:.4f} detik",
        throughput=f"{throughput:.2f} edge/detik"
    )

@app.route("/sinkron-pewarnaan", methods=["POST"])
@login_required
def sinkron_pewarnaan():
    if current_user.role != "Admin":
        flash("Hanya admin yang diizinkan.")
        return redirect(url_for("jadwal"))

    G, _ = build_graph()
    _, pewarnaan, _ = greedy_coloring(G)

    with get_session() as session:
        for kode, slot in pewarnaan.items():
            hari, jam_mulai, jam_selesai = slot_to_hari_jam(slot)
            session.run("MATCH (c:MataKuliah {kode:$kode})-[r:DIJADWALKAN]->() DELETE r", kode=kode)
            session.run("""
                MERGE (j:Jadwal {slot:$slot})
                SET j.hari=$hari, j.jam_mulai=$jam_mulai, j.jam_selesai=$jam_selesai
                WITH j
                MATCH (c:MataKuliah {kode:$kode})
                MERGE (c)-[:DIJADWALKAN]->(j)
            """, kode=kode, slot=slot, hari=hari, jam_mulai=jam_mulai, jam_selesai=jam_selesai)

    flash("Jadwal berhasil disinkronkan dengan hasil pewarnaan Greedy.")
    return redirect(url_for("jadwal"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        uid = request.form["id"]
        with get_session() as s:
            r = s.run("MATCH (u:User {id:$id}) RETURN u.id AS id, u.nama AS nama, u.role AS role", id=uid).single()
        if not r:
            error = "User ID tidak ditemukan."
        else:
            user = User(r["id"], r["nama"], r["role"])
            login_user(user)
            return redirect(url_for("jadwal"))
    return render_template("login.html", error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/admin/mk")
@login_required
def list_mk():
    if current_user.role != "Admin":
        flash("Hanya admin yang diizinkan.")
        return redirect(url_for("jadwal"))
    with get_session() as s:
        rows = s.run("MATCH (c:MataKuliah) RETURN c.kode AS kode, c.nama AS nama, c.ruangan AS ruangan")
        mk_list = [dict(kode=r["kode"], nama=r["nama"], ruangan=r["ruangan"]) for r in rows]
    return render_template("list_mk.html", mk_list=mk_list)

@app.route("/admin/mk/add", methods=["GET", "POST"])
@login_required
def add_mk():
    if current_user.role != "Admin":
        flash("Hanya admin yang diizinkan.")
        return redirect(url_for("jadwal"))
    if request.method == "POST":
        k, n, r = request.form["kode"], request.form["nama"], request.form["ruangan"]
        with get_session() as s:
            s.run("CREATE (:MataKuliah {kode:$k, nama:$n, ruangan:$r})", k=k, n=n, r=r)
        return redirect(url_for("list_mk"))
    return render_template("form_mk.html", mode="Add", mk=None)

@app.route("/admin/mk/edit/<kode>", methods=["GET", "POST"])
@login_required
def edit_mk(kode):
    if current_user.role != "Admin":
        flash("Hanya admin yang diizinkan.")
        return redirect(url_for("jadwal"))
    with get_session() as s:
        ex = s.run("MATCH (c:MataKuliah {kode:$k}) RETURN c.kode AS kode, c.nama AS nama, c.ruangan AS ruangan", k=kode).single()
    if not ex:
        flash("Mata kuliah tidak ditemukan.")
        return redirect(url_for("list_mk"))
    if request.method == "POST":
        n, r = request.form["nama"], request.form["ruangan"]
        with get_session() as s:
            s.run("MATCH (c:MataKuliah {kode:$k}) SET c.nama=$n, c.ruangan=$r", k=kode, n=n, r=r)
        return redirect(url_for("list_mk"))
    return render_template("form_mk.html", mode="Edit", mk=dict(kode=ex["kode"], nama=ex["nama"], ruangan=ex["ruangan"]))

@app.route("/admin/mk/delete/<kode>", methods=["POST"])
@login_required
def delete_mk(kode):
    if current_user.role != "Admin":
        flash("Hanya admin yang diizinkan.")
        return redirect(url_for("jadwal"))
    with get_session() as s:
        s.run("MATCH (c:MataKuliah {kode:$k}) DETACH DELETE c", k=kode)
    return redirect(url_for("list_mk"))

if __name__ == "__main__":
    app.run(debug=True)
