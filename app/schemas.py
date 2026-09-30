import math
from datetime import date, datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import LoanStatus

T = TypeVar("T")


# ----- PAGINAÇÃO -----
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


def make_page(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
    }


# ----- USER / AUTH -----
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    # bcrypt só aceita até 72 bytes
    password: str = Field(min_length=8, max_length=72)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ----- AUTHOR -----
class AuthorBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    birth_date: date
    biography: Optional[str] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorSummary(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


# ----- BOOK -----
class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    synopsis: Optional[str] = None
    published_at: date
    total_copies: int = Field(ge=1)
    author_id: int


class BookCreate(BookBase):
    """available_copies starts out equal to total_copies (calculated on the server)."""


class BookUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    synopsis: Optional[str] = None
    published_at: Optional[date] = None
    total_copies: Optional[int] = Field(default=None, ge=1)
    author_id: Optional[int] = None


class BookResponse(BookBase):
    id: int
    available_copies: int
    author: AuthorSummary
    model_config = ConfigDict(from_attributes=True)


class AuthorResponse(AuthorBase):
    id: int
    books: list[BookResponse] = []
    model_config = ConfigDict(from_attributes=True)


# ----- LOANS -----
class LoanCreate(BaseModel):
    book_id: int


class LoanResponse(BaseModel):
    id: int
    user_id: int
    book_id: int
    borrowed_at: date
    due_date: date
    returned_at: Optional[date] = None
    renews_count: int
    status: LoanStatus
    model_config = ConfigDict(from_attributes=True)
