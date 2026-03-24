from app import create_app

app = create_app()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LMS Diary Management")
    parser.add_argument("command", choices=["run", "init-db", "seed"], help="Action to perform")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if args.command == "init-db":
        with app.app_context():
            app.init_db()
        print("Database initialized")
    elif args.command == "seed":
        with app.app_context():
            app.init_db()
            app.seed_demo_data()
        print("Seed completed")
    else:
        app.run(host=args.host, port=args.port, debug=True)
