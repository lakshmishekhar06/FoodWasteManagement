from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "foodshare_secret_key"

DATABASE = "foodshare.db"


# DATABASE CONNECTION
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# CREATE DATABASE TABLES
def create_database():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            food_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            location TEXT NOT NULL,
            pickup_time TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'Available',
            FOREIGN KEY (donor_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS donation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donation_id INTEGER NOT NULL,
            ngo_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Pending',
            UNIQUE(donation_id, ngo_id),
            FOREIGN KEY (donation_id) REFERENCES donations(id),
            FOREIGN KEY (ngo_id) REFERENCES users(id)
        )
    """)

    # CREATE DEFAULT ADMIN ACCOUNT
    admin = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        ("admin@foodshare.com",)
    ).fetchone()

    if admin is None:
        conn.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (
            "FoodShare Admin",
            "admin@foodshare.com",
            generate_password_hash("Admin@123"),
            "Admin"
        ))

    conn.commit()
    conn.close()


# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# USER REGISTRATION
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]

        if not name or not email or not password:
            flash("Please fill all fields.")
            return redirect(url_for("register"))

        if role not in ["Donor", "NGO"]:
            flash("Invalid role selected.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()

        try:
            conn.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (name, email, hashed_password, role))

            conn.commit()
            flash("Registration successful!")

        except sqlite3.IntegrityError:
            flash("Email already registered.")

        finally:
            conn.close()

        return redirect(url_for("register"))

    return render_template("register.html")


# USER LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# MAIN DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "Donor":
        return redirect(url_for("donor_dashboard"))

    if session["role"] == "NGO":
        return redirect(url_for("ngo_dashboard"))

    if session["role"] == "Admin":
        return redirect(url_for("admin_dashboard"))

    return "Invalid user role", 403


# DONOR DASHBOARD
@app.route("/donor_dashboard")
def donor_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Donor":
        return "Access denied", 403

    conn = get_db_connection()

    donations = conn.execute("""
        SELECT * FROM donations
        WHERE donor_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    requests = conn.execute("""
        SELECT
            donation_requests.id AS request_id,
            donation_requests.status AS request_status,
            donations.food_name,
            donations.quantity,
            users.name AS ngo_name
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        JOIN users
            ON donation_requests.ngo_id = users.id
        WHERE donations.donor_id = ?
        ORDER BY donation_requests.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "donor_dashboard.html",
        name=session["name"],
        donations=donations,
        requests=requests
    )


# ADD FOOD DONATION
@app.route("/add_donation", methods=["POST"])
def add_donation():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Donor":
        return "Access denied", 403

    food_name = request.form["food_name"].strip()
    quantity = request.form["quantity"]
    location = request.form["location"].strip()
    pickup_time = request.form["pickup_time"]
    description = request.form.get("description", "").strip()

    if not food_name or not location or not pickup_time:
        flash("Please fill all required fields.")
        return redirect(url_for("donor_dashboard"))

    try:
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError
    except ValueError:
        flash("Please enter a valid quantity.")
        return redirect(url_for("donor_dashboard"))

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO donations
        (donor_id, food_name, quantity, location, pickup_time, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        food_name,
        quantity,
        location,
        pickup_time,
        description
    ))

    conn.commit()
    conn.close()

    flash("Food donation added successfully!")
    return redirect(url_for("donor_dashboard"))


# NGO DASHBOARD
@app.route("/ngo_dashboard")
def ngo_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "NGO":
        return "Access denied", 403

    conn = get_db_connection()

    donations = conn.execute("""
        SELECT donations.*, users.name AS donor_name
        FROM donations
        JOIN users ON donations.donor_id = users.id
        WHERE donations.status = 'Available'
        ORDER BY donations.id DESC
    """).fetchall()

    request_history = conn.execute("""
        SELECT
            donation_requests.id AS request_id,
            donation_requests.status AS request_status,
            donations.food_name,
            donations.quantity,
            donations.location,
            donations.pickup_time,
            users.name AS donor_name
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        JOIN users
            ON donations.donor_id = users.id
        WHERE donation_requests.ngo_id = ?
        ORDER BY donation_requests.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "ngo_dashboard.html",
        name=session["name"],
        donations=donations,
        request_history=request_history
    )


# NGO REQUEST FOOD
@app.route("/request_donation/<int:donation_id>", methods=["POST"])
def request_donation(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "NGO":
        return "Access denied", 403

    conn = get_db_connection()

    donation = conn.execute("""
        SELECT * FROM donations
        WHERE id = ? AND status = 'Available'
    """, (donation_id,)).fetchone()

    if donation is None:
        flash("This donation is no longer available.")

    else:
        try:
            conn.execute("""
                INSERT INTO donation_requests (donation_id, ngo_id)
                VALUES (?, ?)
            """, (donation_id, session["user_id"]))

            conn.commit()
            flash("Food request submitted successfully!")

        except sqlite3.IntegrityError:
            flash("You have already requested this donation.")

    conn.close()
    return redirect(url_for("ngo_dashboard"))


# DONOR APPROVE OR REJECT REQUEST
@app.route("/update_request/<int:request_id>/<action>", methods=["POST"])
def update_request(request_id, action):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Donor":
        return "Access denied", 403

    if action not in ["approve", "reject"]:
        return "Invalid action", 400

    conn = get_db_connection()

    donation_request = conn.execute("""
        SELECT donation_requests.id,
               donation_requests.status,
               donation_requests.donation_id,
               donations.status AS donation_status
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        WHERE donation_requests.id = ?
        AND donations.donor_id = ?
    """, (request_id, session["user_id"])).fetchone()

    if donation_request is None:
        flash("Request not found.")

    elif donation_request["status"] != "Pending":
        flash("This request has already been processed.")

    elif donation_request["donation_status"] != "Available":
        flash("This donation is no longer available.")

    else:
        if action == "approve":

            conn.execute("""
                UPDATE donation_requests
                SET status = 'Approved'
                WHERE id = ?
            """, (request_id,))

            conn.execute("""
                UPDATE donations
                SET status = 'Claimed'
                WHERE id = ?
            """, (donation_request["donation_id"],))

            # Reject other pending requests for the same donation.
            conn.execute("""
                UPDATE donation_requests
                SET status = 'Rejected'
                WHERE donation_id = ?
                AND id != ?
                AND status = 'Pending'
            """, (donation_request["donation_id"], request_id))

            flash("NGO request approved successfully!")

        else:
            conn.execute("""
                UPDATE donation_requests
                SET status = 'Rejected'
                WHERE id = ?
            """, (request_id,))

            flash("NGO request rejected.")

        conn.commit()

    conn.close()
    return redirect(url_for("donor_dashboard"))


# ADMIN DASHBOARD
@app.route("/admin_dashboard")
def admin_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Admin":
        return "Access denied", 403

    conn = get_db_connection()

    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_donors = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'Donor'"
    ).fetchone()[0]

    total_ngos = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'NGO'"
    ).fetchone()[0]

    total_donations = conn.execute(
        "SELECT COUNT(*) FROM donations"
    ).fetchone()[0]

    available_donations = conn.execute(
        "SELECT COUNT(*) FROM donations WHERE status = 'Available'"
    ).fetchone()[0]

    total_requests = conn.execute(
        "SELECT COUNT(*) FROM donation_requests"
    ).fetchone()[0]

    users = conn.execute("""
        SELECT id, name, email, role
        FROM users
        ORDER BY id DESC
    """).fetchall()

    donations = conn.execute("""
        SELECT donations.*, users.name AS donor_name
        FROM donations
        JOIN users ON donations.donor_id = users.id
        ORDER BY donations.id DESC
    """).fetchall()

    requests = conn.execute("""
        SELECT donation_requests.id AS request_id,
               donation_requests.status AS request_status,
               donations.food_name,
               users.name AS ngo_name
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        JOIN users
            ON donation_requests.ngo_id = users.id
        ORDER BY donation_requests.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        name=session["name"],
        total_users=total_users,
        total_donors=total_donors,
        total_ngos=total_ngos,
        total_donations=total_donations,
        available_donations=available_donations,
        total_requests=total_requests,
        users=users,
        donations=donations,
        requests=requests
    )


# ADMIN DELETE USER
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Admin":
        return "Access denied", 403

    if user_id == session["user_id"]:
        flash("You cannot delete your own admin account.")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if user is None:
        flash("User not found.")

    elif user["role"] == "Admin":
        flash("Admin account cannot be deleted.")

    else:
        if user["role"] == "Donor":

            donation_ids = conn.execute(
                "SELECT id FROM donations WHERE donor_id = ?",
                (user_id,)
            ).fetchall()

            for donation in donation_ids:
                conn.execute(
                    "DELETE FROM donation_requests WHERE donation_id = ?",
                    (donation["id"],)
                )

            conn.execute(
                "DELETE FROM donations WHERE donor_id = ?",
                (user_id,)
            )

        if user["role"] == "NGO":
            conn.execute(
                "DELETE FROM donation_requests WHERE ngo_id = ?",
                (user_id,)
            )

        conn.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,)
        )

        conn.commit()
        flash("User deleted successfully!")

    conn.close()
    return redirect(url_for("admin_dashboard"))


# ADMIN DELETE DONATION
@app.route("/admin/delete_donation/<int:donation_id>", methods=["POST"])
def admin_delete_donation(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Admin":
        return "Access denied", 403

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM donation_requests WHERE donation_id = ?",
        (donation_id,)
    )

    result = conn.execute(
        "DELETE FROM donations WHERE id = ?",
        (donation_id,)
    )

    conn.commit()
    conn.close()

    if result.rowcount > 0:
        flash("Donation deleted successfully!")
    else:
        flash("Donation not found.")

    return redirect(url_for("admin_dashboard"))


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("login"))


# RUN APPLICATION
if __name__ == "__main__":
    create_database()
    app.run(debug=True)