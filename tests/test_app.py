from app import create_app


def make_client(tmp_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
    )

    # Patch DB path at runtime
    import app as app_module

    app_module.DATABASE = tmp_path / "test.db"

    with app.app_context():
        app.init_db()

    return app.test_client(), app


def test_student_registration_and_login(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/register/student",
        data={
            "full_name": "Test Student",
            "email": "test@student.local",
            "password": "Password123",
            "group_name": "A-1",
            "enrollment_year": "2025",
            "faculty": "IT",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Регистрация прошла успешно" in response.get_data(as_text=True)

    response = client.post(
        "/login",
        data={"email": "test@student.local", "password": "Password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Кабинет студента" in response.get_data(as_text=True)


def test_admin_registration_requires_key(tmp_path):
    client, app = make_client(tmp_path)

    app.config["ADMIN_REGISTRATION_KEY"] = "super-secret"
    bad = client.post(
        "/register/admin",
        data={
            "full_name": "Bad Admin",
            "email": "bad@admin.local",
            "password": "VeryStrong123",
            "admin_key": "wrong",
        },
        follow_redirects=True,
    )
    assert "Неверный ключ" in bad.get_data(as_text=True)

    good = client.post(
        "/register/admin",
        data={
            "full_name": "Good Admin",
            "email": "good@admin.local",
            "password": "VeryStrong123",
            "admin_key": "super-secret",
        },
        follow_redirects=True,
    )
    assert "Админ зарегистрирован" in good.get_data(as_text=True)
