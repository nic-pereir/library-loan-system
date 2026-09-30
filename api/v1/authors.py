from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from app import crud
from app.schemas import AuthorCreate, AuthorResponse, Page, make_page

router = APIRouter(prefix="/authors", tags=["authors"])


@router.post(
    "", response_model=AuthorResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
def create_author(data: AuthorCreate, db: Session = Depends(get_db)):
    return crud.create_author(db, data)


@router.get("", response_model=Page[AuthorResponse])
def list_authors(
    name: Optional[str] = Query(None, description="Partial name search"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = crud.list_authors(db, name, page, page_size)
    return make_page(items, total, page, page_size)


@router.get("/{author_id}", response_model=AuthorResponse)
def get_author(author_id: int, db: Session = Depends(get_db)):
    author = crud.get_author(db, author_id)
    if author is None:
        raise HTTPException(status_code=404, detail="Author not found.")
    return author
