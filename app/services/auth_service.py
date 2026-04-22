from datetime import datetime, timezone
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.models.user import User
from app.models.audit import AuditLog, LOGIN, LOGOUT
import uuid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(db: Session, username_or_email: str, password: str) -> User | None:
    user = db.query(User).filter(
        (User.username == username_or_email) | (User.email == username_or_email),
        User.is_active == True,
    ).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def record_login(db: Session, user: User, ip: str = "") -> None:
    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(event=LOGIN, user_id=user.id, meta={"ip": ip}))
    db.commit()


def record_logout(db: Session, user_id: str) -> None:
    db.add(AuditLog(event=LOGOUT, meta={"user_id": str(user_id)}))
    db.commit()


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    is_admin: bool = False,
) -> User:
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def user_exists(db: Session, username: str, email: str) -> bool:
    return db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first() is not None
