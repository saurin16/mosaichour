"""Four cooperating steps: Resolve → Taste Bridge → Program Designer → Access Reviewer."""
import asyncio
import os
import time
from typing import TypedDict

from google import genai
from google.genai import types
from langgraph.graph import END, START, StateGraph

from .models import DraftBatch, PlanRequest, ProgramDraft
from .qloo import Qloo


class State(TypedDict, total=False):
    request: dict
    seeds: list[dict]
    candidates: dict
    drafts: list[dict]
    programs: list[dict]
    trace: list[dict]
    designer: str


def step(name: str, description: str, ms: int, calls: list[dict] | None = None) -> dict:
    return {"agent": name, "result": description, "ms": ms, "qloo_calls": calls or []}


async def resolve(state: State) -> dict:
    start = time.perf_counter()
    request = PlanRequest(**state["request"])
    q = Qloo()
    try:
        artist, movie = await asyncio.gather(q.search(request.artist, "artist"),
                                             q.search(request.movie, "movie"))
    finally:
        await q.close()
    seeds = [{"name": artist["name"], "entity_id": artist["entity_id"], "kind": "artist"},
             {"name": movie["name"], "entity_id": movie["entity_id"], "kind": "movie"}]
    return {"seeds": seeds, "trace": [step("Qloo Scout", "Matched both favorites to Qloo entities",
                                         round((time.perf_counter() - start) * 1000), q.calls)]}


async def discover(state: State) -> dict:
    start = time.perf_counter()
    ids = ",".join(s["entity_id"] for s in state["seeds"])
    q = Qloo()
    try:
        artist, movie, book = await asyncio.gather(q.insights("artist", ids),
                                                    q.insights("movie", ids),
                                                    q.insights("book", ids))
    finally:
        await q.close()
    candidates = {"artist": artist, "movie": movie, "book": book}
    if any(not items for items in candidates.values()):
        raise ValueError("Qloo did not return enough cross-category matches for these favorites. Try another pair.")
    total = sum(map(len, candidates.values()))
    return {"candidates": candidates,
            "trace": state["trace"] + [step("Taste Bridge", f"Found {total} Qloo matches across music, film and books",
                                            round((time.perf_counter() - start) * 1000), q.calls)]}


def fallback(candidates: dict) -> list[dict]:
    labels = [("artist", "A listening salon", "Play a licensed recording or invite humming; ask which memory the music brings up."),
              ("movie", "A film conversation", "Watch a licensed excerpt or discuss a familiar scene; invite different readings."),
              ("book", "A story circle", "Read from a legally available copy; invite stories around its theme.")]
    return [ProgramDraft(selected_name=candidates[kind][0]["name"], title=f"{title}: {candidates[kind][0]['name']}",
                         why_it_fits="Qloo connected this title to the group's two favorites.",
                         opening="Invite residents to share what they remember or enjoy about this theme.",
                         steps=[instruction, "Offer a choice to listen, speak, or simply observe.",
                                "Close with one favorite moment from the group."],
                         closing="Thank everyone for what they chose to share.",
                         host_prompt="What did this bring to mind for you?").model_dump()
            for kind, title, instruction in labels]


async def design(state: State) -> dict:
    start = time.perf_counter()
    req = PlanRequest(**state["request"])
    names = {k: [e["name"] for e in v] for k, v in state["candidates"].items()}
    prompt = (f"Group favorites: {state['seeds'][0]['name']} and {state['seeds'][1]['name']}. "
              f"Group size {req.group_size}; duration {req.minutes} minutes; supply budget at most ${req.budget}; "
              f"access priority {req.access_need}.\n"
              f"Qloo artist choices: {names['artist']}\nQloo movie choices: {names['movie']}\n"
              f"Qloo book choices: {names['book']}\n"
              "Create exactly three program drafts in order: music, film, book. For each, selected_name must "
              "exactly match one name in the corresponding Qloo choices. Make titles concrete, use 3-4 short "
              "facilitation steps and a warm host question. Respect the access priority and budget. Do not "
              "assert health benefits, diagnose, give medical advice, or promise content is licensed. "
              "Do not assume rights to copy lyrics, film images, or book excerpts. All suggestions are for "
              "staff review. Avoid childish or patronizing activities and flag potentially distressing themes.")
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                              http_options=types.HttpOptions(timeout=45000))
        response = await client.aio.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a senior living life-enrichment program designer. Respect resident choice and staff judgment.",
                response_mime_type="application/json", response_schema=DraftBatch, temperature=0.25,
                thinking_config=types.ThinkingConfig(thinking_budget=0)))
        drafts = DraftBatch.model_validate_json(response.text).programs
        if len(drafts) != 3:
            raise ValueError("Designer returned the wrong number of drafts")
        result = [d.model_dump() for d in drafts]
        mode = "Gemini"
    except Exception:
        result = fallback(state["candidates"])
        mode = "template fallback"
    return {"drafts": result, "designer": mode,
            "trace": state["trace"] + [step("Program Designer", f"Drafted three activities ({mode})",
                                            round((time.perf_counter() - start) * 1000))]}


ACCESS = {
    "seated": "Offer every part of the activity seated, with an easy option to observe.",
    "hearing": "Use captions or written prompts; ask residents what volume works for them.",
    "vision": "Read prompts aloud and describe any visuals; avoid relying on small print.",
    "quiet": "Keep volume low, offer a smaller group, and make stepping out easy.",
}
MATERIALS = {
    "artist": "A playback device and legally available music; check permission before reproducing lyrics.",
    "movie": "Licensed film access or a discussion without screening; preview themes and use captions if available.",
    "book": "A legally available copy; check rights before reproducing excerpts and preview themes.",
}


async def review(state: State) -> dict:
    start = time.perf_counter()
    req = PlanRequest(**state["request"])
    programs = []
    corrections = 0
    for kind, draft in zip(("artist", "movie", "book"), state["drafts"]):
        allowed = {e["name"] for e in state["candidates"][kind]}
        if draft["selected_name"] not in allowed:
            draft = dict(draft)
            draft["selected_name"] = state["candidates"][kind][0]["name"]
            draft["why_it_fits"] = "Qloo connected this title to the group's two favorites."
            corrections += 1
        programs.append({"kind": kind, "anchor": draft["selected_name"], "title": draft["title"][:100],
                         "why_it_fits": draft["why_it_fits"][:300], "opening": draft["opening"][:300],
                         "steps": [str(s)[:250] for s in draft["steps"][:4]], "closing": draft["closing"][:300],
                         "host_prompt": draft["host_prompt"][:250], "access_note": ACCESS[req.access_need],
                         "materials": MATERIALS[kind], "duration": req.minutes,
                         "budget_limit": req.budget, "review_needed": True})
    result = f"Checked Qloo anchors and added staff review notes; {corrections} unsupported anchor(s) corrected"
    return {"programs": programs,
            "trace": state["trace"] + [step("Access Reviewer", result,
                                            round((time.perf_counter() - start) * 1000))]}


builder = StateGraph(State)
for name, fn in (("resolve", resolve), ("discover", discover), ("design", design), ("review", review)):
    builder.add_node(name, fn)
builder.add_edge(START, "resolve")
builder.add_edge("resolve", "discover")
builder.add_edge("discover", "design")
builder.add_edge("design", "review")
builder.add_edge("review", END)
graph = builder.compile()
