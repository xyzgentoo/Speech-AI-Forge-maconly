from pydantic import BaseModel


class ChatTTSConfig(BaseModel):
    # model id
    mid: str = "chat-tts"

    style: str = ""
    temperature: float = 0.3
    top_p: float = 0.7
    top_k: int = 20
    prompt: str = ""
    prompt1: str = ""
    prompt2: str = ""
    prefix: str = ""


class InferConfig(BaseModel):
    batch_size: int = 4
    spliter_threshold: int = 100
    # end_of_sentence
    eos: str = "[uv_break]"
    seed: int = 42

    stream: bool = False
    stream_chunk_size: int = 96

    no_cache: bool = False
