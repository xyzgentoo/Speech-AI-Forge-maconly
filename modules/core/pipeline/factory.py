import logging


from modules.core.models.zoo.ModelZoo import model_zoo
from modules.core.pipeline.dcls import TTSSegment
from modules.core.pipeline.pipeline import AudioPipeline, TTSPipeline
from modules.core.pipeline.processor import (
    NP_AUDIO,
    PreProcessor,
    TTSPipelineContext,
)
from modules.core.pipeline.processors.Adjuster import AdjusterProcessor
from modules.core.pipeline.processors.Enhancer import EnhancerProcessor
from modules.core.pipeline.processors.Normalizer import AudioNormalizer
from modules.core.pipeline.processors.VoiceClone import VoiceCloneProcessor
from modules.core.spk.SpkMgr import spk_mgr
from modules.core.spk.TTSSpeaker import TTSSpeaker
from modules.core.tn.ChatTtsTN import ChatTtsTN
from modules.core.tn.CosyVoiceTN import CosyVoiceTN
from modules.core.tn.FishSpeechTN import FishSpeechTN
from modules.core.tn.TNPipeline import TNPipeline
from modules.data import styles_mgr

logger = logging.getLogger(__name__)


class TNProcess(PreProcessor):

    def __init__(self, tn_pipeline: TNPipeline) -> None:
        super().__init__()
        self.tn = tn_pipeline

    def process(self, segment: TTSSegment, context: TTSPipelineContext) -> TTSSegment:
        segment.text = self.tn.normalize(text=segment.text, config=context.tn_config)
        return segment


class TTSStyleProcessor(PreProcessor):
    """
    计算合并 style/spk
    """

    def get_style_params(self, context: TTSPipelineContext):
        style = context.tts_config.style
        if not style:
            return {}
        params = styles_mgr.find_params_by_name(style)
        return params

    def process(self, segment: TTSSegment, context: TTSPipelineContext) -> TTSSegment:
        params = self.get_style_params(context)
        segment.prompt = (
            segment.prompt or context.tts_config.prompt or params.get("prompt", "")
        )
        segment.prompt1 = (
            segment.prompt1 or context.tts_config.prompt1 or params.get("prompt1", "")
        )
        segment.prompt2 = (
            segment.prompt2 or context.tts_config.prompt2 or params.get("prompt2", "")
        )
        segment.prefix = (
            segment.prefix or context.tts_config.prefix or params.get("prefix", "")
        )
        segment.emotion = (
            segment.emotion or context.tts_config.emotion or params.get("emotion", "")
        )

        spk = segment.spk or context.spk

        if isinstance(spk, str):
            if spk == "":
                spk = None
            else:
                spk = spk_mgr.get_speaker(spk)
        if spk and not isinstance(spk, TTSSpeaker):
            spk = None
            logger.warn(f"Invalid spk: {spk}")

        segment.spk = spk

        return segment


class FromAudioPipeline(AudioPipeline):

    def __init__(self, audio: NP_AUDIO, ctx: TTSPipelineContext) -> None:
        super().__init__(context=ctx)
        self.audio = audio

    def generate_audio(self):
        return self.audio


class PipelineFactory:
    @classmethod
    def create(cls, ctx: TTSPipelineContext) -> TTSPipeline:
        model_id = ctx.tts_config.mid

        if model_id == "chattts" or model_id == "chat-tts":
            return cls.create_chattts_pipeline(ctx)
        elif model_id == "fishspeech" or model_id == "fish-speech":
            return cls.create_fishspeech_pipeline(ctx)
        elif model_id == "cosyvoice" or model_id == "cosy-voice":
            return cls.create_cosyvoice_pipeline(ctx)
        else:
            raise Exception(f"Unknown model id: {model_id}")

    @classmethod
    def setup_base_modules(cls, pipeline: AudioPipeline):
        pipeline.add_module(VoiceCloneProcessor())
        pipeline.add_module(EnhancerProcessor())

        # NOTE: 先 normalizer 后 adjuster，不然 volume_gain_db 和 normalize 冲突
        pipeline.add_module(AudioNormalizer())
        pipeline.add_module(AdjusterProcessor())

        pipeline.add_module(TTSStyleProcessor())
        return pipeline

    @classmethod
    def create_chattts_pipeline(cls, ctx: TTSPipelineContext):
        pipeline = TTSPipeline(ctx)
        cls.setup_base_modules(pipeline=pipeline)
        pipeline.add_module(TNProcess(tn_pipeline=ChatTtsTN))
        model = model_zoo.get_chat_tts()
        pipeline.set_model(model)
        return pipeline

    @classmethod
    def create_fishspeech_pipeline(cls, ctx: TTSPipelineContext):
        pipeline = TTSPipeline(ctx)
        cls.setup_base_modules(pipeline=pipeline)
        pipeline.add_module(TNProcess(tn_pipeline=FishSpeechTN))
        model = model_zoo.get_fish_speech()
        pipeline.set_model(model)
        return pipeline

    @classmethod
    def create_cosyvoice_pipeline(cls, ctx: TTSPipelineContext):
        pipeline = TTSPipeline(ctx)
        cls.setup_base_modules(pipeline=pipeline)
        pipeline.add_module(TNProcess(tn_pipeline=CosyVoiceTN))
        model = model_zoo.get_cosy_voice()
        pipeline.set_model(model)
        return pipeline

    @classmethod
    def create_postprocess_pipeline(cls, audio: NP_AUDIO, ctx: TTSPipelineContext):
        pipeline = FromAudioPipeline(audio=audio, ctx=ctx)
        cls.setup_base_modules(pipeline=pipeline)
        return pipeline
