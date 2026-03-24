import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "lms_diary.db"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-change-this-secret-key")
    app.config["ADMIN_REGISTRATION_KEY"] = os.getenv(
        "ADMIN_REGISTRATION_KEY", "change-me-admin-key"
    )

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(DATABASE)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    def close_db(_: object | None = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db() -> None:
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'admin')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS student_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                group_name TEXT NOT NULL,
                enrollment_year INTEGER NOT NULL,
                faculty TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                teacher TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                value INTEGER NOT NULL CHECK(value BETWEEN 0 AND 100),
                comment TEXT,
                date_assigned TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present', 'absent', 'late')),
                FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        db.commit()

    def seed_demo_data() -> None:
        db = get_db()

        admin = db.execute("SELECT id FROM users WHERE email = ?", ("admin@campus.local",)).fetchone()
        if admin is None:
            db.execute(
                "INSERT INTO users(full_name, email, password_hash, role) VALUES(?,?,?,?)",
                (
                    "Главный Администратор",
                    "admin@campus.local",
                    generate_password_hash("AdminPass123!"),
                    "admin",
                ),
            )

        student = db.execute(
            "SELECT id FROM users WHERE email = ?", ("student@campus.local",)
        ).fetchone()
        if student is None:
            cur = db.execute(
                "INSERT INTO users(full_name, email, password_hash, role) VALUES(?,?,?,?)",
                (
                    "Иван Петров",
                    "student@campus.local",
                    generate_password_hash("StudentPass123!"),
                    "student",
                ),
            )
            student_id = cur.lastrowid
            db.execute(
                """
                INSERT INTO student_profiles(user_id, group_name, enrollment_year, faculty)
                VALUES(?,?,?,?)
                """,
                (student_id, "CS-202", 2024, "Факультет Информационных Технологий"),
            )

        subject_defs = [
            ("Математика", "Смирнова Ольга"),
            ("Программирование", "Исаев Роман"),
            ("Базы данных", "Карпова Елена"),
        ]
        for name, teacher in subject_defs:
            db.execute(
                "INSERT OR IGNORE INTO subjects(name, teacher) VALUES(?,?)",
                (name, teacher),
            )

        student_row = db.execute(
            "SELECT id FROM users WHERE email = ?", ("student@campus.local",)
        ).fetchone()
        if student_row:
            student_id = student_row["id"]
            grade_exists = db.execute(
                "SELECT id FROM grades WHERE student_id = ? LIMIT 1", (student_id,)
            ).fetchone()
            if not grade_exists:
                subject_rows = db.execute("SELECT id, name FROM subjects").fetchall()
                values = {"Математика": 91, "Программирование": 96, "Базы данных": 88}
                for row in subject_rows:
                    db.execute(
                        """
                        INSERT INTO grades(student_id, subject_id, value, comment, date_assigned)
                        VALUES(?,?,?,?,?)
                        """,
                        (
                            student_id,
                            row["id"],
                            values.get(row["name"], 85),
                            "Демо-оценка",
                            datetime.now().date().isoformat(),
                        ),
                    )
                    db.execute(
                        """
                        INSERT INTO attendance(student_id, subject_id, lesson_date, status)
                        VALUES(?,?,?,?)
                        """,
                        (
                            student_id,
                            row["id"],
                            datetime.now().date().isoformat(),
                            "present",
                        ),
                    )

        admin_id = db.execute(
            "SELECT id FROM users WHERE email = ?", ("admin@campus.local",)
        ).fetchone()["id"]
        announcement_exists = db.execute("SELECT id FROM announcements LIMIT 1").fetchone()
        if announcement_exists is None:
            db.execute(
                "INSERT INTO announcements(title, body, created_by) VALUES(?,?,?)",
                (
                    "Добро пожаловать в LMS",
                    "Это демонстрационный онлайн-дневник. Админ может добавлять оценки и новости.",
                    admin_id,
                ),
            )

        db.commit()

    def login_required(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash("Сначала войдите в систему.", "warning")
                return redirect(url_for("login"))
            return view(**kwargs)

        return wrapped_view

    def role_required(expected_role: str):
        def decorator(view):
            @wraps(view)
            def wrapped_view(**kwargs):
                if g.user is None:
                    flash("Сначала войдите в систему.", "warning")
                    return redirect(url_for("login"))
                if g.user["role"] != expected_role:
                    abort(403)
                return view(**kwargs)

            return wrapped_view

        return decorator

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            return
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    @app.teardown_appcontext
    def teardown_db(exception: object | None = None) -> None:
        close_db(exception)

    @app.context_processor
    def inject_now() -> dict:
        return {"now": datetime.utcnow()}

    @app.route("/")
    def index():
        if g.user is None:
            return render_template("index.html")
        if g.user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))

    @app.route("/register/student", methods=["GET", "POST"])
    def register_student():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            group_name = request.form.get("group_name", "").strip()
            enrollment_year = request.form.get("enrollment_year", "").strip()
            faculty = request.form.get("faculty", "").strip()

            error = None
            if not full_name or not email or not password:
                error = "Имя, email и пароль обязательны."
            elif len(password) < 8:
                error = "Пароль должен быть минимум 8 символов."
            elif not enrollment_year.isdigit():
                error = "Год поступления должен быть числом."

            db = get_db()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                error = "Пользователь с таким email уже существует."

            if error is None:
                cur = db.execute(
                    "INSERT INTO users(full_name, email, password_hash, role) VALUES(?,?,?,?)",
                    (full_name, email, generate_password_hash(password), "student"),
                )
                db.execute(
                    """
                    INSERT INTO student_profiles(user_id, group_name, enrollment_year, faculty)
                    VALUES(?,?,?,?)
                    """,
                    (cur.lastrowid, group_name or "Не указано", int(enrollment_year), faculty or "Не указано"),
                )
                db.commit()
                flash("Регистрация прошла успешно. Теперь войдите.", "success")
                return redirect(url_for("login"))

            flash(error, "danger")

        return render_template("register_student.html")

    @app.route("/register/admin", methods=["GET", "POST"])
    def register_admin():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            admin_key = request.form.get("admin_key", "")

            error = None
            if not full_name or not email or not password or not admin_key:
                error = "Все поля обязательны."
            elif admin_key != app.config["ADMIN_REGISTRATION_KEY"]:
                error = "Неверный ключ регистрации администратора."
            elif len(password) < 10:
                error = "Пароль админа должен быть минимум 10 символов."

            db = get_db()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                error = "Пользователь с таким email уже существует."

            if error is None:
                db.execute(
                    "INSERT INTO users(full_name, email, password_hash, role) VALUES(?,?,?,?)",
                    (full_name, email, generate_password_hash(password), "admin"),
                )
                db.commit()
                flash("Админ зарегистрирован. Войдите в систему.", "success")
                return redirect(url_for("login"))

            flash(error, "danger")

        return render_template("register_admin.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Неверный email или пароль.", "danger")
            else:
                session.clear()
                session["user_id"] = user["id"]
                flash("Успешный вход.", "success")
                if user["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("student_dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Вы вышли из системы.", "info")
        return redirect(url_for("index"))

    @app.route("/student/dashboard")
    @role_required("student")
    def student_dashboard():
        db = get_db()
        profile = db.execute(
            "SELECT * FROM student_profiles WHERE user_id = ?", (g.user["id"],)
        ).fetchone()
        grades = db.execute(
            """
            SELECT g.value, g.comment, g.date_assigned, s.name AS subject_name, s.teacher
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            WHERE g.student_id = ?
            ORDER BY g.date_assigned DESC
            """,
            (g.user["id"],),
        ).fetchall()

        attendance = db.execute(
            """
            SELECT a.lesson_date, a.status, s.name AS subject_name
            FROM attendance a
            JOIN subjects s ON a.subject_id = s.id
            WHERE a.student_id = ?
            ORDER BY a.lesson_date DESC
            LIMIT 20
            """,
            (g.user["id"],),
        ).fetchall()

        announcements = db.execute(
            """
            SELECT an.title, an.body, an.created_at, u.full_name AS author
            FROM announcements an
            JOIN users u ON an.created_by = u.id
            ORDER BY an.created_at DESC
            LIMIT 10
            """
        ).fetchall()

        avg_grade = round(sum([row["value"] for row in grades]) / len(grades), 2) if grades else 0

        return render_template(
            "student_dashboard.html",
            profile=profile,
            grades=grades,
            attendance=attendance,
            announcements=announcements,
            avg_grade=avg_grade,
        )

    @app.route("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        db = get_db()
        students = db.execute(
            """
            SELECT u.id, u.full_name, u.email, sp.group_name, sp.faculty, sp.enrollment_year
            FROM users u
            LEFT JOIN student_profiles sp ON sp.user_id = u.id
            WHERE u.role = 'student'
            ORDER BY u.created_at DESC
            """
        ).fetchall()

        subjects = db.execute("SELECT * FROM subjects ORDER BY name").fetchall()
        announcements = db.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 10"
        ).fetchall()

        return render_template(
            "admin_dashboard.html",
            students=students,
            subjects=subjects,
            announcements=announcements,
        )

    @app.route("/admin/subject/create", methods=["POST"])
    @role_required("admin")
    def create_subject():
        name = request.form.get("name", "").strip()
        teacher = request.form.get("teacher", "").strip()
        if not name or not teacher:
            flash("Название предмета и преподаватель обязательны.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        try:
            db.execute("INSERT INTO subjects(name, teacher) VALUES(?,?)", (name, teacher))
            db.commit()
            flash("Предмет добавлен.", "success")
        except sqlite3.IntegrityError:
            flash("Такой предмет уже существует.", "warning")

        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/grade/create", methods=["POST"])
    @role_required("admin")
    def create_grade():
        student_id = request.form.get("student_id", "").strip()
        subject_id = request.form.get("subject_id", "").strip()
        value = request.form.get("value", "").strip()
        comment = request.form.get("comment", "").strip()
        date_assigned = request.form.get("date_assigned", datetime.now().date().isoformat())

        if not (student_id.isdigit() and subject_id.isdigit() and value.isdigit()):
            flash("ID студента, ID предмета и оценка должны быть числом.", "danger")
            return redirect(url_for("admin_dashboard"))

        grade_value = int(value)
        if grade_value < 0 or grade_value > 100:
            flash("Оценка должна быть в диапазоне 0-100.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            """
            INSERT INTO grades(student_id, subject_id, value, comment, date_assigned)
            VALUES(?,?,?,?,?)
            """,
            (int(student_id), int(subject_id), grade_value, comment, date_assigned),
        )
        db.commit()
        flash("Оценка успешно добавлена.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/announcement/create", methods=["POST"])
    @role_required("admin")
    def create_announcement():
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or not body:
            flash("Заголовок и текст новости обязательны.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "INSERT INTO announcements(title, body, created_by) VALUES(?,?,?)",
            (title, body, g.user["id"]),
        )
        db.commit()
        flash("Новость опубликована.", "success")
        return redirect(url_for("admin_dashboard"))

    app.cli.add_command(
        app.cli.command("init-db")(lambda: (init_db(), print("Database initialized")))
    )
    app.cli.add_command(app.cli.command("seed")(lambda: (init_db(), seed_demo_data(), print("Seed done"))))

    app.init_db = init_db  # type: ignore[attr-defined]
    app.seed_demo_data = seed_demo_data  # type: ignore[attr-defined]
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
