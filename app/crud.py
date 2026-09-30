from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, contains_eager

from app.config import settings
from app.models import Author, Book, Loan, LoanStatus, User
from app.schemas import AuthorCreate, BookCreate, BookUpdate, UserCreate
from core.security import hash_password, verify_password

OPEN_STATUSES = (LoanStatus.PENDING.value, LoanStatus.ACTIVE.value, LoanStatus.OVERDUE.value)


class BusinessError(Exception):
    """Business rule error; main.py converts it into an HTTP response."""

    def __init__(self, detail: str, status_code: int = 409):
        self.detail = detail
        self.status_code = status_code


def today() -> date:
    # separate function to facilitate "time travel" in tests
    return date.today()


# ============================ USERS ============================
def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email.lower()))


def create_user(db: Session, data: UserCreate) -> User:
    if get_user_by_email(db, data.email):
        raise BusinessError("Email already registered.", 409)
    user = User(name=data.name, email=data.email.lower(), hashed_pwd=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_pwd):
        return None
    return user


# ============================ AUTHORS ============================
def create_author(db: Session, data: AuthorCreate) -> Author:
    author = Author(**data.model_dump())
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


def get_author(db: Session, author_id: int) -> Optional[Author]:
    return db.get(Author, author_id)


def list_authors(db: Session, name: Optional[str], page: int, page_size: int) -> tuple[list[Author], int]:
    stmt = select(Author)
    if name:
        stmt = stmt.where(Author.name.icontains(name, autoescape=True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Author.name, Author.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


# ============================ BOOKS ============================
BOOK_SORT_COLUMNS = {
    "title": Book.title,
    "published_at": Book.published_at,
    "author": Author.name,
}


def list_books(
    db: Session,
    *,
    title: Optional[str],
    author: Optional[str],
    sort_by: str,
    order: str,
    page: int,
    page_size: int,
) -> tuple[list[Book], int]:
    stmt = select(Book).join(Book.author)
    if title:
        stmt = stmt.where(Book.title.icontains(title, autoescape=True))
    if author:
        stmt = stmt.where(Author.name.icontains(author, autoescape=True))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column = BOOK_SORT_COLUMNS[sort_by]
    column = column.desc() if order == "desc" else column.asc()
    items = db.scalars(
        stmt.options(contains_eager(Book.author))
        .order_by(column, Book.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def get_book(db: Session, book_id: int) -> Optional[Book]:
    return db.get(Book, book_id)


def create_book(db: Session, data: BookCreate) -> Book:
    if get_author(db, data.author_id) is None:
        raise BusinessError("Author not found.", 404)
    book = Book(**data.model_dump(), available_copies=data.total_copies)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def update_book(db: Session, book: Book, data: BookUpdate) -> Book:
    changes = data.model_dump(exclude_unset=True)
    if "author_id" in changes and get_author(db, changes["author_id"]) is None:
        raise BusinessError("Author not found.", 404)
    if "total_copies" in changes:
        # maintains the count of lent copies: available = new_total - lent
        borrowed = book.total_copies - book.available_copies
        if changes["total_copies"] < borrowed:
            raise BusinessError(
                f"There are {borrowed} borrowed copies; total_copies cannot be less than that.", 409
            )
        book.available_copies = changes["total_copies"] - borrowed
    for field, value in changes.items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book: Book) -> None:
    has_loans = db.scalar(select(func.count()).select_from(Loan).where(Loan.book_id == book.id))
    if has_loans:
        raise BusinessError("The book has a loan history and cannot be removed.", 409)
    db.delete(book)
    db.commit()


# ============================ LOANS ============================
def mark_overdue(db: Session, user_id: Optional[int] = None) -> None:
    """An expired ACTIVE item becomes OVERDUE (calculated on demand, without a scheduled job)."""
    stmt = (
        update(Loan)
        .where(Loan.status == LoanStatus.ACTIVE.value, Loan.due_date < today())
        .values(status=LoanStatus.OVERDUE.value)
    )
    if user_id is not None:
        stmt = stmt.where(Loan.user_id == user_id)
    db.execute(stmt)
    db.commit()


def _get_own_loan(db: Session, user: User, loan_id: int) -> Loan:
    mark_overdue(db, user.id)
    loan = db.get(Loan, loan_id)
    # 404 (and not 403) so as not to reveal that the loan exists
    if loan is None or loan.user_id != user.id:
        raise BusinessError("Loan not found.", 404)
    return loan


def get_loan(db: Session, user: User, loan_id: int) -> Loan:
    return _get_own_loan(db, user, loan_id)


def list_loans(
    db: Session, user: User, status: Optional[LoanStatus], page: int, page_size: int
) -> tuple[list[Loan], int]:
    mark_overdue(db, user.id)
    stmt = select(Loan).where(Loan.user_id == user.id)
    if status:
        stmt = stmt.where(Loan.status == status.value)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Loan.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def _cooldown_until(db: Session, user_id: int, book_id: int) -> Optional[date]:
    """Date until which the user is blocked from borrowing this book (or None).

    Blocks for COOLDOWN_DAYS after return if, during the last loan of this book:
      - the renewal limit was reached, or
      - the user's last MAX_CONSECUTIVE_LOANS loans were all for this book.
    """
    last_of_book = db.scalar(
        select(Loan)
        .where(Loan.user_id == user_id, Loan.book_id == book_id, Loan.status == LoanStatus.RETURNED.value)
        .order_by(Loan.returned_at.desc(), Loan.id.desc())
        .limit(1)
    )
    if last_of_book is None:
        return None

    hit_renewal_limit = last_of_book.renews_count >= settings.MAX_RENEWALS

    recent = db.scalars(
        select(Loan.book_id)
        .where(Loan.user_id == user_id)
        .order_by(Loan.id.desc())
        .limit(settings.MAX_CONSECUTIVE_LOANS)
    ).all()
    consecutive = len(recent) == settings.MAX_CONSECUTIVE_LOANS and all(b == book_id for b in recent)

    if hit_renewal_limit or consecutive:
        until = last_of_book.returned_at + timedelta(days=settings.COOLDOWN_DAYS)
        if today() < until:
            return until
    return None


def create_loan(db: Session, user: User, book_id: int) -> Loan:
    mark_overdue(db, user.id)

    # `with_for_update` locks the book row (Postgres/MySQL) and prevents two people from taking the last copy.
    book = db.get(Book, book_id, with_for_update=True)
    if book is None:
        raise BusinessError("Book not found.", 404)

    open_loans = db.scalars(
        select(Loan).where(Loan.user_id == user.id, Loan.status.in_(OPEN_STATUSES))
    ).all()

    if any(l.status == LoanStatus.OVERDUE.value for l in open_loans):
        raise BusinessError("You have an overdue loan. Please return it before borrowing new books.", 403)
    if len(open_loans) >= settings.MAX_ACTIVE_LOANS:
        raise BusinessError(f"Limit of {settings.MAX_ACTIVE_LOANS} simultaneous loans reached.", 409)
    if any(l.book_id == book_id for l in open_loans):
        raise BusinessError("You already have an active loan for this book.", 409)

    until = _cooldown_until(db, user.id, book_id)
    if until:
        raise BusinessError(f"Grace period for this book until {until.isoformat()}.", 409)

    if book.available_copies < 1:
        raise BusinessError("There are no copies of this book available.", 409)

    start = today()
    loan = Loan(
        user_id=user.id,
        book_id=book_id,
        borrowed_at=start,
        due_date=start + timedelta(days=settings.LOAN_DAYS),
        renews_count=0,
        status=LoanStatus.PENDING.value,
    )
    book.available_copies -= 1  # The copy is held pending pickup.
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


def pickup_loan(db: Session, user: User, loan_id: int) -> Loan:
    loan = _get_own_loan(db, user, loan_id)
    if loan.status != LoanStatus.PENDING.value:
        raise BusinessError("Only PENDING loans can be withdrawn.", 409)
    start = today()
    loan.status = LoanStatus.ACTIVE.value
    loan.borrowed_at = start  # The 14-day period starts from the time of pickup.
    loan.due_date = start + timedelta(days=settings.LOAN_DAYS)
    db.commit()
    db.refresh(loan)
    return loan


def cancel_loan(db: Session, user: User, loan_id: int) -> None:
    loan = _get_own_loan(db, user, loan_id)
    if loan.status != LoanStatus.PENDING.value:
        raise BusinessError("Only PENDING loans can be cancelled.", 409)
    book = db.get(Book, loan.book_id, with_for_update=True)
    book.available_copies += 1
    db.delete(loan)
    db.commit()


def renew_loan(db: Session, user: User, loan_id: int) -> Loan:
    loan = _get_own_loan(db, user, loan_id)
    if loan.status == LoanStatus.OVERDUE.value:
        raise BusinessError("An overdue loan cannot be renewed. Return the book.", 409)
    if loan.status != LoanStatus.ACTIVE.value:
        raise BusinessError("Only ACTIVE loans can be renewed.", 409)
    if loan.renews_count >= settings.MAX_RENEWALS:
        raise BusinessError(f"Limit of {settings.MAX_RENEWALS} renewals reached.", 409)
    loan.due_date = loan.due_date + timedelta(days=settings.LOAN_DAYS)
    loan.renews_count += 1
    db.commit()
    db.refresh(loan)
    return loan


def return_loan(db: Session, user: User, loan_id: int) -> Loan:
    loan = _get_own_loan(db, user, loan_id)
    if loan.status not in (LoanStatus.ACTIVE.value, LoanStatus.OVERDUE.value):
        raise BusinessError("Only ACTIVE or OVERDUE loans can be returned.", 409)
    book = db.get(Book, loan.book_id, with_for_update=True)
    book.available_copies += 1
    loan.status = LoanStatus.RETURNED.value
    loan.returned_at = today()
    db.commit()
    db.refresh(loan)
    return loan
