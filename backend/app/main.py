import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api import auth_routes, model_routes, governance_routes, dataset_routes, admin_routes, report_routes
from app.services.scheduler_service import scheduler_loop

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="CreditSentinel API",
    description="MLOps-based Responsible Machine Learning platform for credit risk model governance.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(model_routes.router)
app.include_router(governance_routes.router)
app.include_router(dataset_routes.router)
app.include_router(admin_routes.router)
app.include_router(report_routes.router)

_scheduler_task = None


@app.on_event("startup")
def on_startup():
    global _scheduler_task
    init_db()
    # Lightweight in-process background loop for Automated Drift Monitoring
    # (Feature 8). No external cron/task-queue dependency required.
    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(scheduler_loop())


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()


@app.get("/")
def root():
    return {
        "service": "CreditSentinel API",
        "tagline": "A monitoring shield for smarter and fairer lending models.",
        "status": "online",
    }


@app.get("/api/health")
def health():
    return {"status": "healthy"}
