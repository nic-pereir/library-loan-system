from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from app import crud
from app.schemas import BookCreate, BookResponse, BookUpdate, Page, make_page

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=Page[BookResponse])
def list_books(
    title: Optional[str] = Query(None, description="Partial title search"),
    author: Optional[str] = Query(None, description="Partial search by author name"),
    sort_by: Literal["title", "published_at", "author"] = "title",
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = crud.list_books(
        db, title=title, author=author, sort_by=sort_by, order=order, page=page, page_size=page_size
    )
    return make_page(items, total, page, page_size)


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = crud.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    return book


@router.post(
    "", response_model=BookResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
def create_book(data: BookCreate, db: Session = Depends(get_db)):
    return crud.create_book(db, data)


@router.put("/{book_id}", response_model=BookResponse, dependencies=[Depends(get_current_user)])
def update_book(book_id: int, data: BookUpdate, db: Session = Depends(get_db)):
    book = crud.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    return crud.update_book(db, book, data)


@router.delete(
    "/{book_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_user)]
)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = crud.get_book(db, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    crud.delete_book(db, book)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
