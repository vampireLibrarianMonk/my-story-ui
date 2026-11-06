"""One provider contract, three adapters. No secrets are sent to browsers."""

from __future__ import annotations

import asyncio
import os

import httpx


class ProviderError(Exception):
    pass


def availability():
    return {
        "demo": {"ready": True, "label": "Demo · no model"},
        "arc": {
            "ready": bool(
                os.environ.get("ARC_CHAT_URL") and os.environ.get("ARC_MODEL_ID")
            ),
            "label": "Local · Intel Arc",
        },
        "bedrock": {
            "ready": bool(os.environ.get("BEDROCK_MODEL_ID")),
            "label": "AWS · Bedrock",
        },
    }


async def completion(
    provider: str, messages: list[dict], *, model_max_tokens: int = 1000
) -> str:
    if provider == "demo":
        last = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        return (
            "[DEMO RESPONSE — no model was called]\n\n"
            "This is the place where an AI response will appear. The action you submitted was:\n"
            f"“{last[:600]}”\n\n"
            "Connect an Arc-compatible endpoint or an AWS Bedrock model to generate actual text. "
            "You can still test conversations, controls, project documents, and saved passages."
        )
    if provider == "arc":
        url = os.environ.get("ARC_CHAT_URL", "").strip()
        model = os.environ.get("ARC_MODEL_ID", "").strip()
        if not url or not model:
            raise ProviderError(
                "Arc is not configured. Set ARC_CHAT_URL and ARC_MODEL_ID on the server."
            )
        if not url.startswith(("http://", "https://")):
            raise ProviderError("ARC_CHAT_URL must be an http(s) URL.")
        headers = {"Content-Type": "application/json"}
        if os.environ.get("ARC_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["ARC_API_KEY"]
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
                res = await client.post(
                    url,
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": model_max_tokens,
                        "temperature": 0.7,
                        "stream": False,
                    },
                    headers=headers,
                )
                res.raise_for_status()
                data = res.json()
                answer = data["choices"][0]["message"]["content"]
                if isinstance(answer, list):
                    answer = "\n".join(
                        str(c.get("text", "")) for c in answer if isinstance(c, dict)
                    )
                return str(answer).strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Arc service failed: " + str(exc)[:250]) from exc
    if provider == "bedrock":
        model = os.environ.get("BEDROCK_MODEL_ID", "").strip()
        if not model:
            raise ProviderError(
                "Bedrock is not configured. Set BEDROCK_MODEL_ID on the server."
            )
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError(
                "Bedrock requires pip install -r requirements-bedrock.txt"
            ) from exc

        def call():
            kwargs = {}
            if os.environ.get("AWS_REGION"):
                kwargs["region_name"] = os.environ["AWS_REGION"]
            client = boto3.client("bedrock-runtime", **kwargs)
            system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
            turns = [
                {"role": m["role"], "content": [{"text": m["content"]}]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ]
            if not turns:
                raise ProviderError("No user prompt was supplied.")
            response = client.converse(
                modelId=model,
                system=system,
                messages=turns,
                inferenceConfig={"maxTokens": model_max_tokens, "temperature": 0.7},
            )
            return "\n".join(
                block["text"]
                for block in response["output"]["message"]["content"]
                if "text" in block
            )

        try:
            return await asyncio.to_thread(call)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Bedrock failed: " + str(exc)[:250]) from exc
    raise ProviderError("Unknown AI provider.")
