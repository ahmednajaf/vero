from typing import cast

from fastapi import APIRouter, Request, Response

from app.core.config import Settings
from app.knowledge.provider import OpenAIResearchProvider

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/ai")
async def ai_health(request: Request, response: Response) -> dict[str, object]:
    result = await OpenAIResearchProvider(
        cast(Settings, request.app.state.settings)
    ).health()
    response.headers["Cache-Control"] = "no-store"
    if not result["ready"]:
        response.status_code = 503
    return result
