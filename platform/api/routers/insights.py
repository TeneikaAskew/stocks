"""AI Insights router — Vertex AI Gemini 2.0 Flash chat endpoint with streaming."""
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

GCP_PROJECT = "adept-mountain-474619-d4"
GCP_LOCATION = "us-east1"
GCP_KEY_FILE = str(PROJECT_ROOT / ".gcp-key.json")

SYSTEM_PROMPTS = {
    "chat": (
        "You are a senior quantitative trader and portfolio manager with 20 years of "
        "institutional experience across equities, options, and systematic strategies. "
        "You are mentoring a developing trader who uses IWM/SPY/QQQ as their primary instruments.\n\n"
        "Available context you can reference:\n"
        "- Historical signals (330K+ entries with RSI, EMA, StochRSI, ATR, VWAP indicators)\n"
        "- Backtest results for systematic strategies on IWM/SPY/QQQ\n"
        "- Options GEX/VEX flow data (dealer positioning, king nodes, gatekeepers)\n"
        "- Playbook decision cards for each ticker\n\n"
        "Respond conversationally but tie advice back to actual data when possible. "
        "Be direct, specific, and constructive. Challenge assumptions. Don't give generic advice."
    ),
    "market": (
        "You are a derivatives market maker explaining current market structure to a trader on "
        "your desk. Be precise about levels, flows, and what matters today. Reference GEX/VEX "
        "data and explain dealer positioning. Focus on actionable insights for intraday trading."
    ),
    "strategy": (
        "You are a quantitative portfolio manager evaluating a retail trader's systematic strategy. "
        "Analyze it as if considering an allocation decision. Be rigorous and critical. Highlight "
        "risks, edge cases, and improvement opportunities. Reference specific metrics from their "
        "backtest data (win rate, profit factor, max drawdown, Sharpe)."
    ),
    "trade": (
        "You are a senior prop desk trader reviewing a junior trader's work. Be direct, specific, "
        "and constructive. Reference the actual numbers. Grade trades A-F with specific reasoning. "
        "Focus on: entry timing quality, exit optimization, setup alignment with playbook, "
        "and risk management."
    ),
}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "chat"
    ticker: str = "IWM"
    history: list[ChatMessage] = []


def _get_client():
    """Create a google-genai client using service account credentials."""
    from google.oauth2 import service_account
    from google import genai

    project = os.environ.get("GCP_PROJECT_ID", GCP_PROJECT)
    location = os.environ.get("GCP_REGION", GCP_LOCATION)
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", GCP_KEY_FILE)

    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=credentials,
    )
    return client


async def _stream_gemini(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Stream response from Vertex AI Gemini 2.0 Flash."""
    try:
        from google import genai
        from google.genai import types

        client = _get_client()

        # Build contents from history + current message
        contents: list[types.Content] = []
        for msg in request.history[-6:]:
            role = "user" if msg.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

        ticker_context = f"[Ticker: {request.ticker} | Mode: {request.mode}]\n\n"
        contents.append(
            types.Content(role="user", parts=[types.Part(text=ticker_context + request.message)])
        )

        system_prompt = SYSTEM_PROMPTS.get(request.mode, SYSTEM_PROMPTS["chat"])

        for chunk in client.models.generate_content_stream(
            model="gemini-2.0-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,
            ),
        ):
            if chunk.text:
                yield chunk.text

    except ImportError:
        yield (
            "google-genai SDK not installed.\n"
            "Run: pip install google-genai google-cloud-aiplatform"
        )
    except Exception as e:
        err = str(e)
        if "PERMISSION_DENIED" in err or "aiplatform.user" in err:
            yield (
                "Permission denied — the trading-runner service account needs roles/aiplatform.user.\n"
                "Run: gcloud projects add-iam-policy-binding adept-mountain-474619-d4 \\\n"
                "  --member='serviceAccount:trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com' \\\n"
                "  --role='roles/aiplatform.user'"
            )
        else:
            yield f"Gemini error: {err}"


@router.post("/api/insights/chat")
async def insights_chat(request: ChatRequest):
    """Stream a Gemini 2.0 Flash response for the given mode and message."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if request.mode not in SYSTEM_PROMPTS:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")

    return StreamingResponse(
        _stream_gemini(request),
        media_type="text/plain",
        headers={"X-Content-Type-Options": "nosniff"},
    )
