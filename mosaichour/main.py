import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .graph import graph
from .models import PlanRequest
from .qloo import QlooError

app = FastAPI(title="MosaicHour", version="0.1.0")
ROOT = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
_plans: dict[str, dict] = {}
_limit = asyncio.Semaphore(3)


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
async def health():
    return {"ok": True, "service": "mosaichour"}


@app.post("/api/plan")
async def plan(request: PlanRequest):
    try:
        async with _limit:
            result = await graph.ainvoke({"request": request.model_dump(), "trace": []})
    except (ValueError, QlooError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The plan could not be built right now. Please try again.") from exc
    plan_id = uuid.uuid4().hex[:16]
    public = {"id": plan_id, "request": request.model_dump(), "seeds": result["seeds"],
              "candidates": {k: [e["name"] for e in v[:6]] for k, v in result["candidates"].items()},
              "programs": result["programs"], "trace": result["trace"],
              "designer": result["designer"], "approved": None}
    _plans[plan_id] = public
    if len(_plans) > 200:
        _plans.pop(next(iter(_plans)))
    return public


class Approval(BaseModel):
    program_index: int


@app.post("/api/plans/{plan_id}/approve")
async def approve(plan_id: str, choice: Approval):
    plan = _plans.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan expired. Create a new one.")
    if choice.program_index not in (0, 1, 2):
        raise HTTPException(status_code=422, detail="Choose one of the three activities.")
    plan["approved"] = choice.program_index
    return {"id": plan_id, "approved": choice.program_index,
            "program": plan["programs"][choice.program_index]}
