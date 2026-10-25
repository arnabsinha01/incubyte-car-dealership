from getpass import getpass
from sqlalchemy import select
from backend.app import (
    Credentials, User, Vehicle, create_app, password_hasher
)


def main():
    print("Create a local administrator account")
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password (at least 8 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match. Run the command again.")

    credentials = Credentials(email=email, password=password)
    app = create_app()

    with app.state.session_factory() as session:
        existing = session.scalar(
            select(User).where(User.email == credentials.email)
        )
        if existing:
            raise SystemExit(
                "That email already exists. Use a new email for admin setup."
            )

        session.add(User(
            email=credentials.email,
            password_hash=password_hasher.hash(credentials.password),
            role="admin",
        ))

        if session.scalar(select(Vehicle.id).limit(1)) is None:
            vehicles = [
                ("Toyota", "Camry", "Sedan", 32000, 5),
                ("BMW", "X5", "SUV", 68000, 3),
                ("Tesla", "Model 3", "Electric", 42000, 4),
                ("Ford", "Mustang", "Coupe", 46000, 2),
                ("Honda", "Civic", "Sedan", 26000, 0),
                ("Hyundai", "Ioniq 5", "Electric", 44000, 6),
            ]
            for make, model, category, price, quantity in vehicles:
                session.add(Vehicle(
                    make=make, model=model, category=category,
                    price=price, quantity=quantity,
                ))

        session.commit()

    print("Admin account created. Sample inventory is ready.")
    print("Use your admin email and password to log into the application.")


if __name__ == "__main__":
    main()
