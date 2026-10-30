import pytest

from mosaichour.graph import fallback, review


@pytest.mark.asyncio
async def test_reviewer_replaces_unsupported_qloo_anchor_and_adds_access_check():
    candidates = {kind: [{"name": name}] for kind, name in
                  (("artist", "Billie Holiday"), ("movie", "Cinema Paradiso"), ("book", "The Great Gatsby"))}
    drafts = fallback(candidates)
    drafts[0]["selected_name"] = "Invented Musician"
    state = {"request": {"artist": "Frank Sinatra", "movie": "Casablanca", "group_size": 12,
                         "minutes": 45, "budget": 20, "access_need": "hearing"},
             "candidates": candidates, "drafts": drafts, "trace": []}
    result = await review(state)
    assert result["programs"][0]["anchor"] == "Billie Holiday"
    assert all("captions" in p["access_note"] for p in result["programs"])
    assert all(p["review_needed"] for p in result["programs"])
    assert "1 unsupported" in result["trace"][0]["result"]


def test_fallback_uses_only_qloo_candidates():
    candidates = {kind: [{"name": name}] for kind, name in
                  (("artist", "Billie Holiday"), ("movie", "Cinema Paradiso"), ("book", "The Great Gatsby"))}
    assert [p["selected_name"] for p in fallback(candidates)] == [
        "Billie Holiday", "Cinema Paradiso", "The Great Gatsby"]
