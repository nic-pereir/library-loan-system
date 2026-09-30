from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Library business rules
    LOAN_DAYS: int = 14                  # initial term (and term of each renewal)
    MAX_ACTIVE_LOANS: int = 2            # outstanding loans per user
    MAX_RENEWALS: int = 3                # loan renewals
    MAX_CONSECUTIVE_LOANS: int = 3       # the same book "3 times in a row"
    COOLDOWN_DAYS: int = 14              # waiting period to borrow the same book

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
