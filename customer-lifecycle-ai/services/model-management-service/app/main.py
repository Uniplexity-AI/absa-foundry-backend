from fastapi import FastAPI
from app.api import routes

app = FastAPI(title="Absa Foundry Model Management Service")

# routes.py already declares prefix="/api/v1/models" on its APIRouter,
# so do NOT add a prefix here (that produced a doubled path).
app.include_router(routes.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "model-management-service"}
