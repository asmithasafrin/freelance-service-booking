from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os

app = Flask(__name__)
app.secret_key = "freelance-mini-project-secret"
DB = os.path.join(os.path.dirname(__file__), "freelance.db")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, role TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS freelancers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, skill TEXT, bio TEXT, rate REAL DEFAULT 0,
        available INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER, freelancer_id INTEGER,
        service TEXT, booking_date TEXT, status TEXT DEFAULT 'Pending'
    );
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER, rating INTEGER, comment TEXT
    );
    """)
    if not con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        con.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    ("Admin","admin@demo.com","admin123","admin"))
    if con.execute("SELECT COUNT(*) FROM users WHERE role='freelancer'").fetchone()[0] == 0:
        con.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    ("Anu Designer","anu@demo.com","1234","freelancer"))
        uid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO freelancers(user_id,skill,bio,rate,available) VALUES(?,?,?,?,?)",
                    (uid,"Graphic Designer","Logo, poster and social media design",500,1))
        con.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    ("Ravi Developer","ravi@demo.com","1234","freelancer"))
        uid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.execute("INSERT INTO freelancers(user_id,skill,bio,rate,available) VALUES(?,?,?,?,?)",
                    (uid,"Web Developer","Flask and website development",1000,1))
    con.commit(); con.close()

@app.route("/")
def home():
    con=db()
    freelancers=con.execute("""SELECT f.*,u.name,u.email FROM freelancers f
        JOIN users u ON u.id=f.user_id ORDER BY f.available DESC""").fetchall()
    con.close()
    return render_template("index.html", freelancers=freelancers)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name,email,password,role=request.form["name"],request.form["email"],request.form["password"],request.form["role"]
        con=db()
        try:
            cur=con.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",(name,email,password,role))
            if role=="freelancer":
                con.execute("INSERT INTO freelancers(user_id,skill,bio,rate,available) VALUES(?,?,?,?,?)",
                            (cur.lastrowid,request.form.get("skill","General Service"),request.form.get("bio",""),request.form.get("rate",0),1))
            con.commit()
            flash("Registration successful. Please login.","success")
        except sqlite3.IntegrityError:
            flash("Email already registered.","danger")
        con.close()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        con=db()
        u=con.execute("SELECT * FROM users WHERE email=? AND password=?",
                      (request.form["email"],request.form["password"])).fetchone()
        con.close()
        if u:
            session["user_id"],session["name"],session["role"]=u["id"],u["name"],u["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.","danger")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("login"))
    con=db()
    role=session["role"]
    if role=="admin":
        data={"users":con.execute("SELECT COUNT(*) c FROM users WHERE role!='admin'").fetchone()["c"],
              "freelancers":con.execute("SELECT COUNT(*) c FROM freelancers").fetchone()["c"],
              "bookings":con.execute("SELECT COUNT(*) c FROM bookings").fetchone()["c"],
              "pending":con.execute("SELECT COUNT(*) c FROM bookings WHERE status='Pending'").fetchone()["c"]}
        bookings=con.execute("""SELECT b.*,u.name customer,f.id fid,fu.name freelancer
            FROM bookings b JOIN users u ON u.id=b.customer_id
            JOIN freelancers f ON f.id=b.freelancer_id JOIN users fu ON fu.id=f.user_id
            ORDER BY b.id DESC""").fetchall()
    elif role=="freelancer":
        f=con.execute("SELECT * FROM freelancers WHERE user_id=?",(session["user_id"],)).fetchone()
        bookings=con.execute("""SELECT b.*,u.name customer FROM bookings b
            JOIN users u ON u.id=b.customer_id WHERE b.freelancer_id=? ORDER BY b.id DESC""",(f["id"],)).fetchall()
        data={"profile":f}
    else:
        bookings=con.execute("""SELECT b.*,u.name freelancer FROM bookings b
            JOIN freelancers f ON f.id=b.freelancer_id JOIN users u ON u.id=f.user_id
            WHERE b.customer_id=? ORDER BY b.id DESC""",(session["user_id"],)).fetchall()
        data={}
    con.close()
    return render_template("dashboard.html",role=role,bookings=bookings,data=data)

@app.route("/book/<int:fid>", methods=["POST"])
def book(fid):
    if session.get("role")!="customer": return redirect(url_for("login"))
    con=db()
    f=con.execute("SELECT * FROM freelancers WHERE id=?",(fid,)).fetchone()
    if f and f["available"]:
        con.execute("INSERT INTO bookings(customer_id,freelancer_id,service,booking_date) VALUES(?,?,?,?,?)",
                    (session["user_id"],fid,request.form["service"],request.form["booking_date"]))
        con.commit(); flash("Booking request sent.","success")
    else: flash("Freelancer is not available.","danger")
    con.close(); return redirect(url_for("home"))

@app.route("/booking/<int:bid>/<action>")
def booking_action(bid,action):
    if "user_id" not in session: return redirect(url_for("login"))
    status={"accept":"Accepted","reject":"Rejected","progress":"In Progress","complete":"Completed"}.get(action)
    if status:
        con=db()
        con.execute("UPDATE bookings SET status=? WHERE id=?",(status,bid))
        con.commit(); con.close()
        flash("Booking status updated.","success")
    return redirect(url_for("dashboard"))

@app.route("/availability", methods=["POST"])
def availability():
    if session.get("role")!="freelancer": return redirect(url_for("login"))
    con=db()
    con.execute("UPDATE freelancers SET available=? WHERE user_id=?",(int(request.form["available"]),session["user_id"]))
    con.commit(); con.close()
    return redirect(url_for("dashboard"))

@app.route("/feedback/<int:bid>", methods=["POST"])
def feedback(bid):
    con=db()
    con.execute("INSERT INTO feedback(booking_id,rating,comment) VALUES(?,?,?)",
                (bid,request.form["rating"],request.form["comment"]))
    con.commit(); con.close()
    flash("Thank you for your feedback.","success")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

if __name__=="__main__":
    init_db()
    app.run(debug=True)
