import os
from dotenv import load_dotenv

load_dotenv()
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, make_response
)
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_connection, initialize_database
from calculations import calculate_generation

import csv
import io
from datetime import datetime, date


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Illustrative grid emission factor
GRID_EMISSION_FACTOR = 0.70

WASTE_TYPES = [
    "Food Waste",
    "Cattle Dung",
    "Agricultural Waste",
    "Kitchen Waste"
]


class User(UserMixin):
    def __init__(self, user_id, full_name, email):
        self.id = user_id
        self.full_name = full_name
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    connection = get_connection()

    if connection is None:
        return None

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT user_id, full_name, email
            FROM users
            WHERE user_id = %s
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        if user:
            return User(
                user["user_id"],
                user["full_name"],
                user["email"]
            )

        return None

    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------
# COMMON HISTORY FILTER
# --------------------------------------------------

def get_filtered_records(user_id, filters):
    """
    Get records belonging to the logged-in user.
    Optional filters: waste_type, start_date, end_date.
    """

    connection = get_connection()

    if connection is None:
        raise Exception("Database connection failed.")

    cursor = connection.cursor(dictionary=True)

    try:
        query = """
            SELECT *
            FROM generation_records
            WHERE user_id = %s
        """

        values = [user_id]

        waste_type = filters.get("waste_type", "").strip()
        start_date = filters.get("start_date", "").strip()
        end_date = filters.get("end_date", "").strip()

        if waste_type and waste_type in WASTE_TYPES:
            query += " AND waste_type = %s"
            values.append(waste_type)

        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
            query += " AND DATE(created_at) >= %s"
            values.append(start_date)

        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
            query += " AND DATE(created_at) <= %s"
            values.append(end_date)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, tuple(values))

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not full_name or not email or not password:
            flash("Please fill all the fields.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )
            return redirect(url_for("register"))

        connection = get_connection()

        if connection is None:
            flash("Database connection failed.", "error")
            return redirect(url_for("register"))

        cursor = connection.cursor()

        try:
            hashed_password = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO users (full_name, email, password)
                VALUES (%s, %s, %s)
                """,
                (full_name, email, hashed_password)
            )

            connection.commit()

            flash(
                "Registration successful! Please login.",
                "success"
            )

            return redirect(url_for("login"))

        except Exception:
            connection.rollback()
            flash(
                "Email already registered or registration failed.",
                "error"
            )

        finally:
            cursor.close()
            connection.close()

    return render_template("register.html")


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        connection = get_connection()

        if connection is None:
            flash("Database connection failed.", "error")
            return redirect(url_for("login"))

        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user_data = cursor.fetchone()

        finally:
            cursor.close()
            connection.close()

        if user_data and check_password_hash(
            user_data["password"], password
        ):
            user = User(
                user_data["user_id"],
                user_data["full_name"],
                user_data["email"]
            )

            login_user(user)

            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("index"))

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(waste_quantity), 0) AS total_waste,
                COALESCE(SUM(biogas_volume), 0) AS total_biogas,
                COALESCE(SUM(electricity_generated), 0)
                    AS total_electricity
            FROM generation_records
            WHERE user_id = %s
        """, (current_user.id,))

        stats = cursor.fetchone()

        cursor.execute("""
            SELECT
                waste_type,
                SUM(waste_quantity) AS total_waste,
                SUM(biogas_volume) AS total_biogas,
                SUM(electricity_generated) AS total_electricity
            FROM generation_records
            WHERE user_id = %s
            GROUP BY waste_type
        """, (current_user.id,))

        waste_data = cursor.fetchall()

        cursor.execute("""
            SELECT
                DATE_FORMAT(created_at, '%Y-%m') AS month,
                SUM(electricity_generated) AS electricity
            FROM generation_records
            WHERE user_id = %s
            GROUP BY DATE_FORMAT(created_at, '%Y-%m')
            ORDER BY month
        """, (current_user.id,))

        monthly_data = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM generation_records
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 5
        """, (current_user.id,))

        records = cursor.fetchall()

        total_electricity = float(
            stats["total_electricity"] or 0
        )

        environmental_impact = (
            total_electricity * GRID_EMISSION_FACTOR
        )

        return render_template(
            "dashboard.html",
            total_records=stats["total_records"],
            total_waste=round(float(stats["total_waste"]), 2),
            total_biogas=round(float(stats["total_biogas"]), 2),
            total_electricity=round(total_electricity, 2),
            environmental_impact=round(environmental_impact, 2),
            waste_data=waste_data,
            monthly_data=monthly_data,
            records=records
        )

    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------
# CALCULATOR
# --------------------------------------------------

@app.route("/calculator", methods=["GET", "POST"])
@login_required
def calculator():

    result = None

    if request.method == "POST":
        try:
            waste_type = request.form["waste_type"]
            waste_quantity = float(request.form["waste_quantity"])

            if waste_quantity <= 0:
                raise ValueError(
                    "Waste quantity must be greater than zero."
                )

            result = calculate_generation(
                waste_type,
                waste_quantity
            )

            connection = get_connection()

            if connection is None:
                flash("Database connection failed.", "error")
                return render_template(
                    "calculator.html",
                    result=result
                )

            cursor = connection.cursor()

            try:
                cursor.execute("""
                    INSERT INTO generation_records (
                        user_id,
                        waste_type,
                        waste_quantity,
                        biogas_volume,
                        methane_percentage,
                        methane_volume,
                        generator_efficiency,
                        electricity_generated
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    current_user.id,
                    result["waste_type"],
                    result["waste_quantity"],
                    result["biogas_volume"],
                    result["methane_percentage"],
                    result["methane_volume"],
                    result["generator_efficiency"],
                    result["electricity_generated"]
                ))

                connection.commit()

                flash(
                    "Calculation saved successfully!",
                    "success"
                )

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()
                connection.close()

        except ValueError as e:
            flash(str(e), "error")

        except Exception as e:
            flash(
                "Calculation could not be saved: " + str(e),
                "error"
            )

    return render_template("calculator.html", result=result)


# --------------------------------------------------
# HISTORY WITH FILTERS
# --------------------------------------------------

@app.route("/history")
@login_required
def history():

    filters = {
        "waste_type": request.args.get("waste_type", ""),
        "start_date": request.args.get("start_date", ""),
        "end_date": request.args.get("end_date", "")
    }

    records = []

    try:
        records = get_filtered_records(
            current_user.id,
            filters
        )

    except ValueError:
        flash("Please enter valid filter dates.", "error")

    except Exception as e:
        flash("Could not load history: " + str(e), "error")

    return render_template(
        "history.html",
        records=records,
        filters=filters,
        waste_types=WASTE_TYPES
    )


# --------------------------------------------------
# DELETE A HISTORY RECORD
# --------------------------------------------------

@app.route("/delete-record/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("history"))

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM generation_records
            WHERE record_id = %s AND user_id = %s
        """, (record_id, current_user.id))

        connection.commit()

        if cursor.rowcount > 0:
            flash("Record deleted successfully.", "success")
        else:
            flash("Record not found or you cannot delete it.", "error")

    except Exception as e:
        connection.rollback()
        flash("Could not delete record: " + str(e), "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("history"))


# --------------------------------------------------
# CSV EXPORT
# --------------------------------------------------

@app.route("/export/csv")
@login_required
def export_csv():

    try:
        records = get_filtered_records(
            current_user.id,
            request.args
        )

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Record ID",
            "Date",
            "Waste Type",
            "Waste Quantity (kg)",
            "Biogas Volume (m3)",
            "Methane Percentage",
            "Methane Volume (m3)",
            "Generator Efficiency",
            "Electricity Generated (kWh)"
        ])

        for record in records:
            writer.writerow([
                record["record_id"],
                record["created_at"],
                record["waste_type"],
                record["waste_quantity"],
                record["biogas_volume"],
                record["methane_percentage"],
                record["methane_volume"],
                record["generator_efficiency"],
                record["electricity_generated"]
            ])

        response = make_response("\ufeff" + output.getvalue())

        response.headers["Content-Disposition"] = (
            "attachment; filename=biopower_history.csv"
        )
        response.headers["Content-Type"] = (
            "text/csv; charset=utf-8"
        )

        return response

    except ValueError:
        flash("Please enter valid filter dates.", "error")
        return redirect(url_for("history"))

    except Exception as e:
        flash("CSV export failed: " + str(e), "error")
        return redirect(url_for("history"))


# --------------------------------------------------
# PDF REPORT
# --------------------------------------------------

@app.route("/export/pdf")
@login_required
def export_pdf():

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )

        records = get_filtered_records(
            current_user.id,
            request.args
        )

        buffer = io.BytesIO()

        document = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm
        )

        styles = getSampleStyleSheet()
        content = []

        content.append(
            Paragraph("BioPower - Generation Report", styles["Title"])
        )

        content.append(Spacer(1, 8))

        content.append(
            Paragraph(
                "User: " + current_user.full_name,
                styles["Normal"]
            )
        )

        content.append(
            Paragraph(
                "Report generated: " + datetime.now().strftime(
                    "%d-%m-%Y %I:%M %p"
                ),
                styles["Normal"]
            )
        )

        content.append(Spacer(1, 12))

        total_waste = sum(
            float(r["waste_quantity"] or 0) for r in records
        )
        total_biogas = sum(
            float(r["biogas_volume"] or 0) for r in records
        )
        total_electricity = sum(
            float(r["electricity_generated"] or 0)
            for r in records
        )

        content.append(
            Paragraph(
                "Total records: " + str(len(records)),
                styles["Heading2"]
            )
        )

        content.append(
            Paragraph(
                "Total waste: {:.2f} kg".format(total_waste),
                styles["Normal"]
            )
        )

        content.append(
            Paragraph(
                "Total biogas: {:.2f} m3".format(total_biogas),
                styles["Normal"]
            )
        )

        content.append(
            Paragraph(
                "Total electricity: {:.2f} kWh".format(
                    total_electricity
                ),
                styles["Normal"]
            )
        )

        content.append(Spacer(1, 15))

        table_data = [[
            "ID",
            "Date",
            "Waste Type",
            "Waste (kg)",
            "Biogas (m3)",
            "Methane (m3)",
            "Electricity (kWh)"
        ]]

        for record in records:
            table_data.append([
                str(record["record_id"]),
                str(record["created_at"]),
                str(record["waste_type"]),
                "{:.2f}".format(float(record["waste_quantity"])),
                "{:.2f}".format(float(record["biogas_volume"])),
                "{:.2f}".format(float(record["methane_volume"])),
                "{:.2f}".format(
                    float(record["electricity_generated"])
                )
            ])

        if not records:
            content.append(
                Paragraph(
                    "No records were found for the selected filters.",
                    styles["Normal"]
                )
            )
        else:
            table = Table(
                table_data,
                repeatRows=1,
                colWidths=[
                    15 * mm,
                    37 * mm,
                    40 * mm,
                    25 * mm,
                    28 * mm,
                    28 * mm,
                    35 * mm
                ]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176B3A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    colors.white,
                    colors.HexColor("#EAF5ED")
                ]),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
            ]))

            content.append(table)

        document.build(content)

        buffer.seek(0)

        response = make_response(buffer.getvalue())

        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            "attachment; filename=biopower_report.pdf"
        )

        return response

    except ValueError:
        flash("Please enter valid filter dates.", "error")
        return redirect(url_for("history"))

    except Exception as e:
        flash("PDF report could not be generated: " + str(e), "error")
        return redirect(url_for("history"))


# --------------------------------------------------
# ANALYTICS
# --------------------------------------------------

@app.route("/analytics")
@login_required
def analytics():

    connection = get_connection()

    if connection is None:
        flash("Database connection failed.", "error")
        return redirect(url_for("dashboard"))

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                waste_type,
                SUM(waste_quantity) AS total_waste,
                SUM(biogas_volume) AS total_biogas,
                SUM(electricity_generated) AS total_electricity
            FROM generation_records
            WHERE user_id = %s
            GROUP BY waste_type
        """, (current_user.id,))

        records = cursor.fetchall()

        cursor.execute("""
            SELECT
                DATE_FORMAT(created_at, '%Y-%m') AS month,
                SUM(waste_quantity) AS total_waste,
                SUM(biogas_volume) AS total_biogas,
                SUM(electricity_generated) AS total_electricity
            FROM generation_records
            WHERE user_id = %s
            GROUP BY DATE_FORMAT(created_at, '%Y-%m')
            ORDER BY month
        """, (current_user.id,))

        monthly_data = cursor.fetchall()

        cursor.execute("""
            SELECT
                COALESCE(SUM(waste_quantity), 0) AS total_waste,
                COALESCE(SUM(biogas_volume), 0) AS total_biogas,
                COALESCE(SUM(electricity_generated), 0)
                    AS total_electricity,
                COUNT(*) AS total_records
            FROM generation_records
            WHERE user_id = %s
        """, (current_user.id,))

        stats = cursor.fetchone()

        total_electricity = float(
            stats["total_electricity"] or 0
        )

        environmental_impact = (
            total_electricity * GRID_EMISSION_FACTOR
        )

        return render_template(
            "analytics.html",
            records=records,
            monthly_data=monthly_data,
            total_waste=round(float(stats["total_waste"]), 2),
            total_biogas=round(float(stats["total_biogas"]), 2),
            total_electricity=round(total_electricity, 2),
            total_records=stats["total_records"],
            environmental_impact=round(environmental_impact, 2),
            emission_factor=GRID_EMISSION_FACTOR
        )

    finally:
        cursor.close()
        connection.close()


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
