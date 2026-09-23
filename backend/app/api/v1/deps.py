from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.user import User
from app.models.project import Project
from app.models.presentation import Presentation
from app.models.document import Document

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user


def get_owned_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """The path's project if it belongs to the current user; 404 otherwise (never reveal other users' data)."""
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_owned_presentation(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Presentation:
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return pres


def get_owned_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    doc = db.get(Document, document_id)
    project = db.get(Project, doc.project_id) if doc else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
