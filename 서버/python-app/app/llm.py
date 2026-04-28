import os
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3:8b")

async def ask_llm(prompt: str, think: bool = False, max_tokens: int = 300) -> dict:
    """
    Ollama API로 LLM 호출
    
    Args: 
        prompt: LLM에 보낼 프롬프트 문자열
        think: True=Thinking ON(배치용), False=Thinking OFF(실시간용)
        max_tokens: 최대 생성 토큰 수
    Returns:
        {"response": "LLM 응답 텍스트", "eval_count": 토큰수, "total_duration": 소요시간(ns)}
    """

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "think": think,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
        },
    }

    # CPU 서버로 응답이 느림 -> 타임아웃 넉넉히
    timeout = httpx.Timeout(600.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    
    return {
        "response": data.get("response", ""),
        "eval_count": data.get("eval_count", 0),
        "total_duration": data.get("total_duration", 0)
    }

async def ask_llm_with_fallback(prompt: str, 
                                fallback_message: str, 
                                think: bool = False,
                                max_tokens: int = 300) -> str:
    """
    LLM 호출 + 실패 시 fallback 메시지 반환 
    Args: 
        prompt: LLM에 보낼 프롬프트
        fallback_message: LLM 실패 시 대신 반환할 메시지
        think: Thinking 모드 ON/OFF
        max_tokens: 최대 생성 토큰 수
    Returns:
        LLM 응답 텍스트 또는 fallback 메시지
    """

    try:
        result = await ask_llm(prompt, think=think, max_tokens=max_tokens)
        response = result["response"].strip()
        if response:
            return response
        return fallback_message
    except Exception:
        return fallback_message