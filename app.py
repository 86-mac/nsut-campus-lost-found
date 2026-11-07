import os
import secrets
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from uuid import uuid4
import json
import urllib.request
import urllib.error
import os

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "local-development-only-change-before-deploying")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

DB_CONFIG = {
    "host": os.getenv("DB_HOST") or os.getenv("MYSQLHOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT") or os.getenv("MYSQLPORT", "3306")),
    "user": os.getenv("DB_USER") or os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("DB_PASSWORD") or os.getenv("MYSQLPASSWORD", ""),
    "database": os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE", "campus_lost_found"),
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)



def send_email(to_email, subject, body):
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        app.logger.warning("Email not sent: RESEND_API_KEY is missing.")
        return False

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "text": body
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NSUT-Campus-Lost-Found/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            app.logger.info("Email sent successfully through Resend.")
            return True

    except urllib.error.HTTPError as e:
        error = e.read().decode("utf-8", errors="replace")
        app.logger.error("Resend email error: %s", error)
        return False

    except Exception:
        app.logger.exception("Resend email delivery failed.")
        return False



def notify_user(user_id, message, subject="NSUT Campus Lost & Found update"):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("INSERT INTO notifications(user_id,message) VALUES(%s,%s)", (user_id, message))
        cur.execute("SELECT email, full_name FROM users WHERE user_id=%s", (user_id,))
        user = cur.fetchone()
        conn.commit()
        if user:
            send_email(user["email"], subject, f"Hello {user['full_name']},\n\n{message}\n\nNSUT Campus Lost & Found")
    finally:
        cur.close()
        conn.close()


def record_tracking_event(cur, item_id, event, details, actor_id=None):
    """Record a visible milestone in an item's tracking timeline."""
    cur.execute(
        "INSERT INTO item_tracking(item_id,actor_id,event,details) VALUES(%s,%s,%s,%s)",
        (item_id, actor_id, event, details),
    )


def save_image(file, prefix):
    if not file or not file.filename:
        return None
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Please upload a JPG, PNG, WEBP or GIF image.")
    filename = f"{prefix}_{uuid4().hex}.{ext}"
    file.save(UPLOAD_DIR / filename)
    return f"uploads/{filename}"


def remove_upload(relative_path):
    if relative_path:
        path = (BASE_DIR / "static" / relative_path).resolve()
        if path.parent == UPLOAD_DIR.resolve() and path.exists():
            path.unlink(missing_ok=True)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


@app.errorhandler(413)
def file_too_large(_error):
    flash("Image is too large. Maximum upload size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile_number", "").strip()
        roll = request.form.get("roll_no", "").strip() or None
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8 or not mobile.isdigit() or len(mobile) != 10:
            flash("Enter your name, email, a valid 10-digit mobile number and a password of at least 8 characters.", "danger")
            return redirect(url_for("register"))
        try:
            profile_image = save_image(request.files.get("profile_image"), "profile")
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                "INSERT INTO users(full_name,email,mobile_number,roll_no,password_hash,profile_image_path) VALUES(%s,%s,%s,%s,%s,%s)",
                (name, email, mobile, roll, generate_password_hash(password), profile_image)
            )
            conn.commit()
            cur.close(); conn.close()
            send_email(email, "Welcome to NSUT Campus Lost & Found",
                    f"Hello {name},\n\nYour account has been created successfully. You can now sign in to report and search for lost/found items.")
            flash("Registration successful. Check your email if mail delivery is configured, then log in.", "success")
            return redirect(url_for("login"))
        except (Error, ValueError) as e:
            flash("Could not register: " + str(e), "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone(); cur.close(); conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["name"] = user["full_name"]
            session["role"] = user["role"]
            send_email(user["email"], "New login to NSUT Campus Lost & Found",
                    f"Hello {user['full_name']},\n\nA successful login to your account occurred at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. If this was not you, reset your password immediately.")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id, full_name FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(minutes=30)
            cur.execute("INSERT INTO password_resets(user_id,token_hash,expires_at) VALUES(%s,%s,%s)",
                        (user["user_id"], generate_password_hash(token), expires))
            conn.commit()
            reset_url = url_for("reset_password", token=token, _external=True)
            sent = send_email(email, "Reset your NSUT Campus Lost & Found password",
                            f"Hello {user['full_name']},\n\nUse this one-time link within 30 minutes to reset your password:\n{reset_url}\n\nIf you did not request this, ignore this email.")
            if not sent:
                app.logger.warning("Password reset link could not be emailed for account %s", user["user_id"])
        cur.close(); conn.close()
        flash("If that email is registered, a password reset link will be sent when email delivery is configured.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM password_resets WHERE used_at IS NULL AND expires_at > UTC_TIMESTAMP() ORDER BY reset_id DESC")
    reset_row = next((r for r in cur.fetchall() if check_password_hash(r["token_hash"], token)), None)
    if not reset_row:
        cur.close(); conn.close()
        flash("This password reset link is invalid or expired. Request a new one.", "danger")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        else:
            cur.execute("UPDATE users SET password_hash=%s WHERE user_id=%s",
                        (generate_password_hash(password), reset_row["user_id"]))
            cur.execute("UPDATE password_resets SET used_at=UTC_TIMESTAMP() WHERE reset_id=%s", (reset_row["reset_id"],))
            conn.commit(); cur.close(); conn.close()
            flash("Password changed. Please log in.", "success")
            return redirect(url_for("login"))
    cur.close(); conn.close()
    return render_template("reset_password.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))



@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        mobile = request.form.get("mobile_number", "").strip()

        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number.", "danger")
        else:
            cur.execute(
                "SELECT profile_image_path FROM users WHERE user_id=%s",
                (session["user_id"],)
            )
            old = cur.fetchone()["profile_image_path"]

            try:
                new_image = save_image(
                    request.files.get("profile_image"), "profile"
                )

                cur.execute(
                    "UPDATE users SET mobile_number=%s WHERE user_id=%s",
                    (mobile, session["user_id"])
                )

                if new_image:
                    cur.execute(
                        "UPDATE users SET profile_image_path=%s WHERE user_id=%s",
                        (new_image, session["user_id"])
                    )

                conn.commit()

                if new_image:
                    remove_upload(old)

                flash("Profile updated successfully.", "success")

            except (Error, ValueError) as e:
                conn.rollback()
                flash(str(e), "danger")

    cur.execute(
        "SELECT * FROM users WHERE user_id=%s",
        (session["user_id"],)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("profile.html", user=user)



@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) total, SUM(report_type='Lost') lost_count, SUM(report_type='Found') found_count, SUM(status='Open') open_count FROM items")
    stats = cur.fetchone()
    cur.execute("SELECT i.*, c.category_name, l.location_name, u.full_name reporter, u.email reporter_email, u.mobile_number reporter_mobile FROM items i JOIN categories c ON c.category_id=i.category_id JOIN locations l ON l.location_id=i.location_id JOIN users u ON u.user_id=i.reporter_id ORDER BY i.item_date DESC, i.item_id DESC LIMIT 8")
    items = cur.fetchall(); cur.close(); conn.close()
    return render_template("dashboard.html", stats=stats, items=items)


@app.route("/items")
@login_required
def items():
    term = request.args.get("q", "").strip(); kind = request.args.get("type", "")
    conn = get_db(); cur = conn.cursor(dictionary=True)
    sql = "SELECT i.*, c.category_name, l.location_name, u.full_name reporter, u.email reporter_email, u.mobile_number reporter_mobile FROM items i JOIN categories c ON c.category_id=i.category_id JOIN locations l ON l.location_id=i.location_id JOIN users u ON u.user_id=i.reporter_id WHERE (i.item_name LIKE %s OR i.description LIKE %s)"
    args = [f"%{term}%", f"%{term}%"]
    if kind in ("Lost", "Found"):
        sql += " AND i.report_type=%s"; args.append(kind)
    sql += " ORDER BY i.item_date DESC, i.item_id DESC"
    cur.execute(sql, tuple(args)); rows = cur.fetchall(); cur.close(); conn.close()
    return render_template("items.html", items=rows, q=term, kind=kind)


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("item_name", "").strip()
        try:
            if not name:
                raise ValueError("Item name is required.")
            image_path = save_image(request.files.get("item_image"), "item")
            cur.execute("INSERT INTO items(report_type,item_name,category_id,location_id,description,item_date,reporter_id,image_path) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (request.form["report_type"], name, request.form["category_id"], request.form["location_id"],
                        request.form.get("description", ""), request.form.get("item_date") or date.today(), session["user_id"], image_path))
            item_id = cur.lastrowid
            record_tracking_event(
                cur, item_id, "Reported",
                f'{request.form["report_type"]} item report created.', session["user_id"]
            )
            conn.commit(); cur.close(); conn.close()
            flash("Item report saved successfully.", "success")
            return redirect(url_for("item_tracking", item_id=item_id))
        except (Error, ValueError) as e:
            conn.rollback(); flash(str(e), "danger")
    cur.execute("SELECT * FROM categories ORDER BY category_name")
    categories = cur.fetchall(); cur.execute("SELECT * FROM locations WHERE location_name IN ('APJ Complex','Block:-5','Block:-6','Nesci Lawn','Ramanujan Hostel','Raman Hostel','Bhaskar Hostel','Aryabhata Hostel','JC Bose','Saraswati Hostel','Kaveri Hostel','North Gate') ORDER BY location_name")
    locations = cur.fetchall(); cur.close(); conn.close()
    return render_template("report.html", categories=categories, locations=locations)


@app.route("/claim/<int:item_id>", methods=["POST"])
@login_required
def claim(item_id):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM items WHERE item_id=%s AND report_type='Found' AND status='Open'", (item_id,))
    item = cur.fetchone()
    if not item:
        flash("This found item is no longer available for claiming.", "warning")
    elif item["reporter_id"] == session["user_id"]:
        flash("You cannot claim an item you reported.", "warning")
    else:
        cur.execute("INSERT INTO claims(item_id,claimant_id,claim_date) VALUES(%s,%s,%s)", (item_id, session["user_id"], date.today()))
        claim_id = cur.lastrowid
        cur.execute("UPDATE items SET status='Claimed' WHERE item_id=%s", (item_id,))
        record_tracking_event(
            cur, item_id, "Claim submitted",
            f"Claim #{claim_id} was submitted and is awaiting administrator review.",
            session["user_id"],
        )
        conn.commit()
        notify_user(item["reporter_id"], f'New claim #{claim_id} for "{item["item_name"]}".', "New claim submitted")
        flash("Claim submitted for administrator review.", "success")
    cur.close(); conn.close()
    return redirect(url_for("items"))


@app.route("/claims")
@login_required
def claims():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    sql = "SELECT c.*, i.item_name, u.full_name claimant FROM claims c JOIN items i ON i.item_id=c.item_id JOIN users u ON u.user_id=c.claimant_id"
    args = ()
    if session.get("role") != "admin":
        sql += " WHERE c.claimant_id=%s"; args = (session["user_id"],)
    cur.execute(sql + " ORDER BY c.claim_date DESC", args)
    rows = cur.fetchall(); cur.close(); conn.close()
    return render_template("claims.html", claims=rows)


@app.route("/claim/<int:claim_id>/<decision>", methods=["POST"])
@admin_required
def decide_claim(claim_id, decision):
    if decision not in ("approve", "reject"):
        abort(400)
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT c.*, i.item_name FROM claims c JOIN items i ON i.item_id=c.item_id WHERE c.claim_id=%s", (claim_id,))
    c = cur.fetchone()
    if c and c["claim_status"] == "Pending":
        status = "Approved" if decision == "approve" else "Rejected"
        item_status = "Returned" if decision == "approve" else "Open"
        cur.execute("UPDATE claims SET claim_status=%s WHERE claim_id=%s", (status, claim_id))
        cur.execute("UPDATE items SET status=%s WHERE item_id=%s", (item_status, c["item_id"]))
        record_tracking_event(
            cur, c["item_id"], f"Claim {status.lower()}",
            f"Claim #{claim_id} was {status.lower()} by an administrator. Item status: {item_status}.",
            session["user_id"],
        )
        conn.commit()
        notify_user(c["claimant_id"], f'Your claim #{claim_id} for "{c["item_name"]}" was {status.lower()}.', "Claim decision")
        flash(f"Claim {status.lower()}.", "success")
    cur.close(); conn.close()
    return redirect(url_for("claims"))


@app.route("/item/<int:item_id>/tracking")
@login_required
def item_tracking(item_id):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT i.*, u.full_name reporter, u.email reporter_email FROM items i "
        "JOIN users u ON u.user_id=i.reporter_id WHERE i.item_id=%s",
        (item_id,),
    )
    item = cur.fetchone()
    if not item:
        cur.close(); conn.close(); abort(404)

    allowed = session.get("role") == "admin" or item["reporter_id"] == session["user_id"]
    if not allowed:
        cur.execute(
            "SELECT claim_id FROM claims WHERE item_id=%s AND claimant_id=%s LIMIT 1",
            (item_id, session["user_id"]),
        )
        allowed = cur.fetchone() is not None
    if not allowed:
        cur.close(); conn.close(); abort(403)

    cur.execute(
        "SELECT t.*, u.full_name actor_name FROM item_tracking t "
        "LEFT JOIN users u ON u.user_id=t.actor_id "
        "WHERE t.item_id=%s ORDER BY t.created_at DESC, t.tracking_id DESC",
        (item_id,),
    )
    events = cur.fetchall(); cur.close(); conn.close()
    return render_template("tracking.html", item=item, events=events)


@app.route("/notifications")
@login_required
def notifications():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
    rows = cur.fetchall(); cur.execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (session["user_id"],))
    conn.commit(); cur.close(); conn.close()
    return render_template("notifications.html", notifications=rows)


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) users_count FROM users"); users_count = cur.fetchone()["users_count"]
    cur.execute("SELECT COUNT(*) items_count FROM items"); items_count = cur.fetchone()["items_count"]
    cur.execute("SELECT COUNT(*) pending_count FROM claims WHERE claim_status='Pending'"); pending_count = cur.fetchone()["pending_count"]
    cur.execute("SELECT i.*, c.category_name, l.location_name, u.full_name reporter, u.email reporter_email, u.mobile_number reporter_mobile FROM items i JOIN categories c ON c.category_id=i.category_id JOIN locations l ON l.location_id=i.location_id JOIN users u ON u.user_id=i.reporter_id ORDER BY i.created_at DESC")
    all_items = cur.fetchall()
    cur.execute("SELECT user_id,full_name,email,mobile_number,roll_no,role,created_at,profile_image_path FROM users ORDER BY created_at DESC")
    all_users = cur.fetchall(); cur.close(); conn.close()
    return render_template("admin.html", users_count=users_count, items_count=items_count, pending_count=pending_count, items=all_items, users=all_users)


@app.route("/admin/item/<int:item_id>/status", methods=["POST"])
@admin_required
def admin_item_status(item_id):
    status = request.form.get("status")
    if status not in ("Open", "Claimed", "Returned", "Resolved"):
        abort(400)
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT item_name,reporter_id FROM items WHERE item_id=%s", (item_id,)); item = cur.fetchone()
    if item:
        cur.execute("SELECT status FROM items WHERE item_id=%s", (item_id,))
        old_status = cur.fetchone()["status"]
        cur.execute("UPDATE items SET status=%s WHERE item_id=%s", (status, item_id))
        if old_status != status:
            record_tracking_event(
                cur, item_id, "Status updated",
                f"Administrator changed item status from {old_status} to {status}.",
                session["user_id"],
            )
        conn.commit()
    cur.close(); conn.close()
    if item:
        notify_user(item["reporter_id"], f'Status for "{item["item_name"]}" changed to {status}.', "Item status changed")
    flash("Item status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_user_role(user_id):
    role = request.form.get("role")
    if role not in ("student", "admin") or user_id == session["user_id"]:
        flash("Invalid role change. You cannot change your own role.", "danger")
        return redirect(url_for("admin_dashboard"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE users SET role=%s WHERE user_id=%s", (role, user_id)); conn.commit()
    cur.close(); conn.close()
    flash("User role updated.", "success")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
