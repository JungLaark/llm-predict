import os
from fastapi import FastAPI
import httpx
from contextlib import asynccontextmanager
from database import init_pool, close_pool
from predict import predict_cash as do_predict_cash, predict_fault as do_predict_fault
from predict import data_cash as do_data_cash, data_fault as do_data_fault
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
DB_HOST = os.getenv("DB_HOST", "192.168.28.22")
DB_PORT = int(os.getenv("DB_PORT", "1432"))
DB_NAME = os.getenv("DB_NAME", "datm")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

app = FastAPI(
    title="ATMS 예측 모듈",
    description="ATM 시재 예측 및 장애 예측 API",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/demo")
async def demo():
    return FileResponse("demo.html", media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "atms-prediction"}


@app.get("/api/v1/status")
async def status():
    """Ollama 및 DB 연결 상태 확인"""
    result = {"ollama": "unknown", "database": "unknown"}

    # Ollama 연결 확인
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                result["ollama"] = "connected"
                result["models"] = [m["name"] for m in models]
            else:
                result["ollama"] = "error"
    except Exception as e:
        result["ollama"] = f"disconnected: {e}"

    # MySQL 연결 확인
    try:
        import aiomysql

        conn = await aiomysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
        conn.close()
        result["database"] = "connected"
    except Exception as e:
        result["database"] = f"disconnected: {e}"

    return result


@app.post("/api/v1/data/cash")
async def data_cash(term_group_id: str = "00706", term_id: str = "415", base_date: str = None):
    """시재 조회 (LLM 없이 즉시 응답)"""
    return await do_data_cash(term_group_id, term_id, base_date=base_date)

@app.post("/api/v1/data/fault")
async def data_fault(term_group_id: str = "00706", term_id: str = "415", base_date: str = None):
    """장애 조회 (LLM 없이 즉시 응답)"""
    return await do_data_fault(term_group_id, term_id, base_date=base_date)


@app.post("/api/v1/predict/cash")
async def predict_cash(term_group_id: str = "00706", term_id: str = "415", base_date: str = None):
    """시재 예측"""
    result = await do_predict_cash(term_group_id, term_id, base_date=base_date)
    return result


@app.post("/api/v1/predict/fault")
async def predict_fault(term_group_id: str = "00706", term_id: str = "415", base_date: str = None):
    """장애 예측"""
    result = await do_predict_fault(term_group_id, term_id, base_date=base_date)
    return result
