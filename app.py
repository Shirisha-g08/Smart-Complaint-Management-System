"""
Smart Complaint Management System
Flask + AWS DynamoDB + SNS
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── AWS config ───────────────────────────────────────────────────────────────
AWS_REGION        = os.environ.get("AWS_REGION", "us-east-1")
USERS_TABLE       = os.environ.get("DYNAMODB_USERS_TABLE", "scms_users")
COMPLAINTS_TABLE  = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "scms_complaints")
SNS_TOPIC_ARN     = os.environ.get("SNS_TOPIC_ARN", "")
ADMIN_EMAIL       = os.environ.get("ADMIN_EMAIL", "admin@college.edu")
ADMIN_PASSWORD    = os.environ.get("ADMIN_PASSWORD", "Admin@123")

dynamodb        = boto3.resource("dynamodb", region_name=AWS_REGION)
sns_client      = boto3.client("sns",        region_name=AWS_REGION)
users_table     = dynamodb.Table(USERS_TABLE)
complaints_table = dynamodb.Table(COMPLAINTS_TABLE)

# ── Constants ─────────────────────────────────────────────────────────────────
CATEGORIES = [
    "Infrastructure",
    "Hostel",
    "Academic",
    "Administration",
    "Transport",
    "Other",
]
STATUS_OPTIONS = ["Pending", "In Progress", "Resolved"]


# ── Helpers ───────────────────────────────────────────────────────────────────
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def send_sns_notification(subject: str, message: str) -> None:
    """Publish a message to the SNS topic (all subscribers receive it)."""
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not configured — skipping notification.")
        return
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
        logger.info("SNS notification sent: %s", subject)
    except ClientError as exc:
        logger.error("SNS publish failed: %s", exc)


# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ── User Registration ──────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_email" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        phone    = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not all([name, email, phone, password, confirm]):
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html")

        try:
            existing = users_table.get_item(Key={"email": email}).get("Item")
            if existing:
                flash("Email already registered. Please login.", "warning")
                return render_template("register.html")

            users_table.put_item(Item={
                "email":         email,
                "user_id":       str(uuid.uuid4()),
                "name":          name,
                "phone":         phone,
                "password_hash": generate_password_hash(password),
                "created_at":    utc_now(),
            })
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))

        except ClientError as exc:
            logger.error("DynamoDB error (register): %s", exc)
            flash("Registration failed. Please try again.", "danger")

    return render_template("register.html")


# ── User Login ────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_email" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("login.html")

        try:
            user = users_table.get_item(Key={"email": email}).get("Item")
            if user and check_password_hash(user["password_hash"], password):
                session["user_email"] = email
                session["user_name"]  = user["name"]
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid email or password.", "danger")

        except ClientError as exc:
            logger.error("DynamoDB error (login): %s", exc)
            flash("Login failed. Please try again.", "danger")

    return render_template("login.html")


# ── User Logout ───────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ════════════════════════════════════════════════════════════════════════════════
# USER ROUTES  (login required)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    complaints = []
    try:
        response   = complaints_table.query(
            IndexName="user_email-index",
            KeyConditionExpression=Key("user_email").eq(session["user_email"]),
        )
        complaints = sorted(
            response.get("Items", []),
            key=lambda c: c.get("timestamp", ""),
            reverse=True,
        )
    except ClientError as exc:
        logger.error("DynamoDB error (dashboard): %s", exc)
        flash("Could not load complaints.", "warning")

    stats = {
        "total":       len(complaints),
        "pending":     sum(1 for c in complaints if c.get("status") == "Pending"),
        "in_progress": sum(1 for c in complaints if c.get("status") == "In Progress"),
        "resolved":    sum(1 for c in complaints if c.get("status") == "Resolved"),
    }
    return render_template("dashboard.html", complaints=complaints, stats=stats)


@app.route("/submit", methods=["GET", "POST"])
@login_required
def submit_complaint():
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category    = request.form.get("category", "").strip()

        if not all([title, description, category]):
            flash("All fields are required.", "danger")
            return render_template("submit_complaint.html", categories=CATEGORIES)

        if category not in CATEGORIES:
            flash("Invalid category selected.", "danger")
            return render_template("submit_complaint.html", categories=CATEGORIES)

        complaint_id = str(uuid.uuid4())
        now          = utc_now()

        try:
            complaints_table.put_item(Item={
                "complaint_id": complaint_id,
                "user_email":   session["user_email"],
                "user_name":    session.get("user_name", "User"),
                "title":        title,
                "description":  description,
                "category":     category,
                "status":       "Pending",
                "timestamp":    now,
                "updated_at":   now,
                "remarks":      "",
            })

            send_sns_notification(
                subject=f"[SmartCMS] Complaint Received — {complaint_id[:8].upper()}",
                message=(
                    f"Hello {session.get('user_name', 'User')},\n\n"
                    f"Your complaint has been submitted successfully.\n\n"
                    f"ID     : {complaint_id[:8].upper()}\n"
                    f"Title  : {title}\n"
                    f"Category: {category}\n"
                    f"Status : Pending\n"
                    f"Time   : {now}\n\n"
                    f"We will review and respond as soon as possible.\n\n"
                    f"— Smart Complaint Management System"
                ),
            )

            flash(
                f"Complaint submitted! Reference ID: {complaint_id[:8].upper()}",
                "success",
            )
            return redirect(url_for("dashboard"))

        except ClientError as exc:
            logger.error("DynamoDB error (submit): %s", exc)
            flash("Failed to submit complaint. Please try again.", "danger")

    return render_template("submit_complaint.html", categories=CATEGORIES)


@app.route("/complaint/<complaint_id>")
@login_required
def complaint_detail(complaint_id):
    try:
        complaint = complaints_table.get_item(
            Key={"complaint_id": complaint_id}
        ).get("Item")

        if not complaint or complaint["user_email"] != session["user_email"]:
            flash("Complaint not found.", "danger")
            return redirect(url_for("dashboard"))

        return render_template("complaint_detail.html", complaint=complaint)

    except ClientError as exc:
        logger.error("DynamoDB error (detail): %s", exc)
        flash("Error loading complaint.", "danger")
        return redirect(url_for("dashboard"))


# ════════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES  (admin_required)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
def admin_index():
    return redirect(url_for("admin_dashboard") if session.get("is_admin") else url_for("admin_login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["is_admin"]    = True
            session["admin_email"] = email
            flash("Admin login successful.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin",    None)
    session.pop("admin_email", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    complaints = []
    try:
        # For large datasets, implement pagination with LastEvaluatedKey
        response   = complaints_table.scan()
        complaints = sorted(
            response.get("Items", []),
            key=lambda c: c.get("timestamp", ""),
            reverse=True,
        )
    except ClientError as exc:
        logger.error("DynamoDB error (admin dashboard): %s", exc)
        flash("Could not load complaints.", "warning")

    stats = {
        "total":       len(complaints),
        "pending":     sum(1 for c in complaints if c.get("status") == "Pending"),
        "in_progress": sum(1 for c in complaints if c.get("status") == "In Progress"),
        "resolved":    sum(1 for c in complaints if c.get("status") == "Resolved"),
    }
    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        stats=stats,
    )


@app.route("/admin/complaint/<complaint_id>", methods=["GET", "POST"])
@admin_required
def admin_complaint(complaint_id):
    try:
        complaint = complaints_table.get_item(
            Key={"complaint_id": complaint_id}
        ).get("Item")

        if not complaint:
            flash("Complaint not found.", "danger")
            return redirect(url_for("admin_dashboard"))

        if request.method == "POST":
            new_status = request.form.get("status", "").strip()
            remarks    = request.form.get("remarks", "").strip()

            if new_status not in STATUS_OPTIONS:
                flash("Invalid status value.", "danger")
                return render_template(
                    "admin_complaint.html",
                    complaint=complaint,
                    status_options=STATUS_OPTIONS,
                )

            complaints_table.update_item(
                Key={"complaint_id": complaint_id},
                UpdateExpression="SET #st = :s, remarks = :r, updated_at = :u",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":s": new_status,
                    ":r": remarks,
                    ":u": utc_now(),
                },
            )

            send_sns_notification(
                subject=f"[SmartCMS] Complaint Update — {complaint_id[:8].upper()}",
                message=(
                    f"Hello {complaint.get('user_name', 'User')},\n\n"
                    f"Your complaint has been updated by the admin.\n\n"
                    f"ID       : {complaint_id[:8].upper()}\n"
                    f"Title    : {complaint['title']}\n"
                    f"New Status: {new_status}\n"
                    f"Remarks  : {remarks or 'No remarks provided'}\n\n"
                    f"Thank you for your patience.\n\n"
                    f"— Smart Complaint Management System"
                ),
            )

            flash(f'Status updated to "{new_status}".', "success")
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_complaint.html",
            complaint=complaint,
            status_options=STATUS_OPTIONS,
        )

    except ClientError as exc:
        logger.error("DynamoDB error (admin_complaint): %s", exc)
        flash("Error processing complaint.", "danger")
        return redirect(url_for("admin_dashboard"))


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # On EC2: set debug=False and use a production WSGI server (gunicorn)
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_ENV") == "development")
