import asyncio
import base64
import io
from typing import AsyncGenerator

import numpy as np
from fastapi import Request
from fastapi.responses import StreamingResponse

from modules.core.handler.datacls.audio_model import AudioFormat, EncoderConfig
from modules.core.handler.datacls.tts_model import InferConfig
from modules.core.handler.encoder.encoders import (
    AacEncoder,
    FlacEncoder,
    Mp3Encoder,
    OggEncoder,
    RawEncoder,
    WavEncoder,
)
from modules.core.handler.encoder.StreamEncoder import StreamEncoder
from modules.core.handler.encoder.WavFile import WAVFileBytes
from modules.core.pipeline.processor import NP_AUDIO
import logging

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)

def remove_wav_bytes_header(wav_bytes: bytes):
    wav_file = WAVFileBytes(wav_bytes=wav_bytes)
    wav_file.read()
    return wav_file.get_body_data()


def read_np_to_wav(audio_data: np.ndarray) -> bytes:
    audio_data: np.ndarray = audio_data / np.max(np.abs(audio_data))
    audio_data = (audio_data * 32767).astype(np.int16)
    return audio_data.tobytes()


class AudioHandler:

    def __init__(
        self, encoder_config: EncoderConfig, infer_config: InferConfig
    ) -> None:
        assert isinstance(
            infer_config, InferConfig
        ), "infer_config should be InferConfig"
        assert isinstance(
            encoder_config, EncoderConfig
        ), "encoder_config should be EncoderConfig"

        self.encoder_config = encoder_config
        self.infer_config = infer_config
        self.current_request: Request = None

    async def enqueue(self) -> NP_AUDIO:
        raise NotImplementedError("Method 'enqueue' must be implemented by subclass")

    async def enqueue_stream(self) -> AsyncGenerator[NP_AUDIO, None]:
        raise NotImplementedError(
            "Method 'enqueue_stream' must be implemented by subclass"
        )

    def set_current_request(self, request: Request):
        if self.current_request is not None:
            raise ValueError("current_request has been set")
        self.current_request = request

        asyncio.create_task(self.monitor_disconnect(request))

    async def monitor_disconnect(self, request: Request):
        """后台协程，监听 request 是否断开"""
        while not await request.is_disconnected():
            await asyncio.sleep(0.1)
        logger.debug("request is disconnected")
        self.interrupt()

    def get_encoder(self) -> StreamEncoder:
        encoder_config = self.encoder_config
        format = encoder_config.format
        bitrate = encoder_config.bitrate or None
        acodec = encoder_config.acodec or None

        if format == AudioFormat.wav:
            encoder = WavEncoder()
        elif format == AudioFormat.mp3:
            encoder = Mp3Encoder()
        elif format == AudioFormat.flac:
            encoder = FlacEncoder()
        # OGG 和 ACC 编码有问题，不知道为啥
        # FIXME: BrokenPipeError: [Errno 32] Broken pipe
        elif format == AudioFormat.acc:
            encoder = AacEncoder()
        # FIXME: BrokenPipeError: [Errno 32] Broken pipe
        elif format == AudioFormat.ogg:
            encoder = OggEncoder()
        elif format == AudioFormat.raw:
            encoder = RawEncoder()
        else:
            raise ValueError(f"Unsupported audio format: {format}")

        encoder.open(bitrate=bitrate, acodec=acodec)

        return encoder

    async def enqueue_to_stream(self) -> AsyncGenerator[bytes, None]:
        encoder = self.get_encoder()
        try:
            logger.debug("enqueue_to_stream start")

            chunk_data = bytes()
            async for sample_rate, audio_data in await self.enqueue_stream():
                encoder.set_header(sample_rate=sample_rate)
                audio_bytes = read_np_to_wav(audio_data=audio_data)

                logger.debug(f"write audio_bytes len: {len(audio_bytes)}")
                encoder.write(audio_bytes)

                chunk_data = encoder.read()
                while len(chunk_data) > 0:
                    logger.debug(f"encoder read data_1 len: {len(chunk_data)}")

                    yield chunk_data
                    chunk_data = encoder.read()

            encoder.close()

            chunk_data = encoder.read()
            while len(chunk_data) > 0:
                logger.debug(f"encoder read data_2 len: {len(chunk_data)}")

                yield chunk_data
                chunk_data = encoder.read()
        finally:
            logger.debug("enqueue_to_stream end")
            encoder.terminate()

    def interrupt(self):
        # called to interrupt inference
        pass

    async def enqueue_to_stream_with_request(self) -> AsyncGenerator[bytes, None]:
        gen1 = self.enqueue_to_stream()
        async for chunk in gen1:
            if await self.current_request.is_disconnected():
                self.interrupt()
                break
            yield chunk
            await asyncio.sleep(0.01)
        try:
            await gen1.aclose()
        except GeneratorExit:
            pass

    # just for test
    async def enqueue_to_stream_join(self) -> AsyncGenerator[bytes, None]:
        encoder = self.get_encoder()
        chunk_data = bytes()
        async for sample_rate, audio_data in await self.enqueue_stream():
            encoder.set_header(sample_rate=sample_rate)
            audio_bytes = read_np_to_wav(audio_data=audio_data)
            encoder.write(audio_bytes)

        encoder.close()
        chunk_data = encoder.read_all()
        if len(chunk_data) > 0:
            yield chunk_data

        encoder.terminate()

    async def enqueue_to_bytes(self) -> bytes:
        encoder = self.get_encoder()

        try:
            sample_rate, audio_data = await self.enqueue()
            audio_bytes = read_np_to_wav(audio_data=audio_data)
            encoder.set_header(sample_rate=sample_rate)
            encoder.write(audio_bytes)
            encoder.close()
            buffer = encoder.read_all()
        finally:
            encoder.terminate()

        return buffer

    async def enqueue_to_buffer(self) -> io.BytesIO:
        audio_bytes = await self.enqueue_to_bytes()
        return io.BytesIO(audio_bytes)

    async def enqueue_to_base64(self) -> str:
        binary = await self.enqueue_to_bytes()

        base64_encoded = base64.b64encode(binary)
        base64_string = base64_encoded.decode("utf-8")

        return base64_string

    def get_media_type(self) -> str:
        encoder_config = self.encoder_config

        media_type = f"audio/{encoder_config.format}"
        if encoder_config.format == AudioFormat.mp3:
            media_type = "audio/mpeg"
        if encoder_config.format == AudioFormat.raw:
            media_type = "audio/wav"

        return media_type

    async def enqueue_to_response(self) -> StreamingResponse:
        infer_config = self.infer_config
        media_type = self.get_media_type()

        if infer_config.stream:
            gen = self.enqueue_to_stream_with_request()
            return StreamingResponse(gen, media_type=media_type)
        else:
            buffer = await self.enqueue_to_buffer()
            return StreamingResponse(buffer, media_type=media_type)
