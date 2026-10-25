import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    CheckConstraint, Integer, Numeric, String, create_engine, select, update
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, sessionmaker
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("price >= 0"),
        CheckConstraint("quantity >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    make: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value


class VehicleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    quantity: int = Field(ge=0, strict=True)


class VehicleUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    make: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    quantity: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("make", "model", "category", "price", "quantity")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("A supplied field cannot be null")
        return value


class RestockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(gt=0, strict=True)


class VehicleOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    make: str
    model: str
    category: str
    price: float
    quantity: int


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: Literal["user", "admin"]


password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def create_app(database_url=None):
    database_url = database_url or os.getenv(
        "DATABASE_URL", "sqlite:///./dealership.db"
    )
    connect_args = (
        {"check_same_thread": False, "timeout": 30}
        if database_url.startswith("sqlite") else {}
    )
    engine = create_engine(database_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Set JWT_SECRET in production. Without it, restarting logs users out.
    jwt_secret = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
    application = FastAPI(title="Car Dealership Inventory API")
    application.state.session_factory = session_factory
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def get_session():
        with session_factory() as session:
            yield session

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        session=Depends(get_session),
    ):
        unauthorized = HTTPException(
            status_code=401,
            detail="Please log in with a valid account",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if credentials is None:
            raise unauthorized
        try:
            payload = jwt.decode(
                credentials.credentials,
                jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "exp"]},
            )
            user_id = int(payload["sub"])
        except (InvalidTokenError, ValueError, TypeError, KeyError):
            raise unauthorized
        user = session.get(User, user_id)
        if user is None:
            raise unauthorized
        return user

    def admin_user(user=Depends(current_user)):
        if user.role != "admin":
            raise HTTPException(403, "Administrator access required")
        return user

    def find_vehicle(session, vehicle_id):
        vehicle = session.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise HTTPException(404, "Vehicle not found")
        return vehicle

    @application.post(
        "/api/auth/register", status_code=201, response_model=UserOutput
    )
    def register(data: Credentials, session=Depends(get_session)):
        user = User(
            email=data.email,
            password_hash=password_hasher.hash(data.password),
            role="user",
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "This email is already registered")
        session.refresh(user)
        return user

    @application.post("/api/auth/login")
    def login(data: Credentials, session=Depends(get_session)):
        user = session.scalar(select(User).where(User.email == data.email))
        if user is None or not password_hasher.verify(
            data.password, user.password_hash
        ):
            raise HTTPException(401, "Incorrect email or password")
        token = jwt.encode(
            {
                "sub": str(user.id),
                "exp": datetime.now(timezone.utc) + timedelta(hours=8),
            },
            jwt_secret,
            algorithm="HS256",
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {"id": user.id, "email": user.email, "role": user.role},
        }

    @application.get("/api/auth/me", response_model=UserOutput)
    def me(user=Depends(current_user)):
        return user

    @application.get("/api/vehicles", response_model=list[VehicleOutput])
    def list_vehicles(
        user=Depends(current_user), session=Depends(get_session)
    ):
        return session.scalars(select(Vehicle).order_by(Vehicle.id)).all()

    @application.get(
        "/api/vehicles/search", response_model=list[VehicleOutput]
    )
    def search_vehicles(
        make: str | None = None,
        model: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        user=Depends(current_user),
        session=Depends(get_session),
    ):
        if (
            (min_price is not None and (not min_price.is_finite() or min_price < 0))
            or (max_price is not None and (not max_price.is_finite() or max_price < 0))
        ):
            raise HTTPException(422, "Prices must be finite and nonnegative")
        if (
            min_price is not None and max_price is not None
            and min_price > max_price
        ):
            raise HTTPException(422, "Minimum price exceeds maximum price")
        query = select(Vehicle)
        for column, value in (
            (Vehicle.make, make),
            (Vehicle.model, model),
            (Vehicle.category, category),
        ):
            if value:
                query = query.where(column.icontains(value, autoescape=True))
        if min_price is not None:
            query = query.where(Vehicle.price >= min_price)
        if max_price is not None:
            query = query.where(Vehicle.price <= max_price)
        return session.scalars(query.order_by(Vehicle.id)).all()

    @application.post(
        "/api/vehicles", status_code=201, response_model=VehicleOutput
    )
    def add_vehicle(
        data: VehicleInput,
        user=Depends(admin_user),
        session=Depends(get_session),
    ):
        vehicle = Vehicle(**data.model_dump())
        session.add(vehicle)
        session.commit()
        session.refresh(vehicle)
        return vehicle

    @application.put(
        "/api/vehicles/{vehicle_id}", response_model=VehicleOutput
    )
    def update_vehicle(
        vehicle_id: int,
        data: VehicleUpdate,
        user=Depends(admin_user),
        session=Depends(get_session),
    ):
        vehicle = find_vehicle(session, vehicle_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(vehicle, key, value)
        session.commit()
        session.refresh(vehicle)
        return vehicle

    @application.delete("/api/vehicles/{vehicle_id}", status_code=204)
    def delete_vehicle(
        vehicle_id: int,
        user=Depends(admin_user),
        session=Depends(get_session),
    ):
        vehicle = find_vehicle(session, vehicle_id)
        session.delete(vehicle)
        session.commit()
        return Response(status_code=204)

    @application.post(
        "/api/vehicles/{vehicle_id}/purchase", response_model=VehicleOutput
    )
    def purchase(
        vehicle_id: int,
        user=Depends(current_user),
        session=Depends(get_session),
    ):
        # A conditional database update prevents overselling the last unit.
        result = session.execute(
            update(Vehicle)
            .where(Vehicle.id == vehicle_id, Vehicle.quantity > 0)
            .values(quantity=Vehicle.quantity - 1)
        )
        if result.rowcount == 0:
            session.rollback()
            find_vehicle(session, vehicle_id)
            raise HTTPException(409, "Vehicle is out of stock")
        session.commit()
        return find_vehicle(session, vehicle_id)

    @application.post(
        "/api/vehicles/{vehicle_id}/restock", response_model=VehicleOutput
    )
    def restock(
        vehicle_id: int,
        data: RestockInput,
        user=Depends(admin_user),
        session=Depends(get_session),
    ):
        result = session.execute(
            update(Vehicle)
            .where(Vehicle.id == vehicle_id)
            .values(quantity=Vehicle.quantity + data.quantity)
        )
        if result.rowcount == 0:
            session.rollback()
            raise HTTPException(404, "Vehicle not found")
        session.commit()
        return find_vehicle(session, vehicle_id)

    return application
