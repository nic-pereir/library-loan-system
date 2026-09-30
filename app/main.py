from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.v1.router import api_router
from app.crud import BusinessError

app = FastAPI(title="Library API", version="1.0.0")


@app.exception_handler(BusinessError)
def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
