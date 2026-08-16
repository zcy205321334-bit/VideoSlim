from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

X264Preset: TypeAlias = Literal[
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
]

EncoderName: TypeAlias = Literal[
    "auto",
    "libx264",
    "libx265",
    "h264_nvenc",
    "hevc_nvenc",
    "h264_amf",
]

RateControlMode: TypeAlias = Literal[
    "crf",  # 质量优先（体积浮动）
    "abr",  # 固定码率（体积可控）
    "capped_crf",  # CRF + 码率上限（质量优先但封顶）
]


class EncoderConfigModel(BaseModel):
    """
    编码器配置模型类，用于定义视频编码器的参数

    支持软编（libx264/libx265）与硬编（NVENC/AMF）：
    - rate_control="crf"：质量模式，crf 生效
    - rate_control="abr"：固定码率模式，bitrate 生效（体积可预估）
    - rate_control="capped_crf"：CRF+码率上限，crf/maxrate/bufsize 生效
    """

    encoder: EncoderName = Field(
        default="libx264",
        description="编码器：libx264 软编 / libx265 软编 / h264_nvenc 硬编 / hevc_nvenc 硬编 / h264_amf 硬编",
    )
    rate_control: RateControlMode = Field(
        default="crf",
        description="码率控制模式：crf 质量 / abr 固定码率 / capped_crf CRF+上限",
    )
    crf: float = Field(
        default=23.5, gt=0, lt=51, description="CRF值，范围在0-51之间，值越小质量越高"
    )
    bitrate: int = Field(
        default=2000, gt=0, le=100000, description="目标视频码率（kbps），abr/capped_crf 模式用"
    )
    maxrate: int = Field(
        default=4000, gt=0, le=100000, description="码率上限（kbps），capped_crf 模式用"
    )
    bufsize: int = Field(
        default=8000, gt=0, le=200000, description="码率缓冲（kbps），建议 2x maxrate"
    )
    audio_bitrate: int = Field(
        default=0, ge=0, le=512, description="音频码率（kbps），0=自适应原视频音频码率"
    )
    preset: X264Preset = Field(
        default="slow",
        description="x264/x265编码预设（软编专用）",
    )
    nvenc_preset: str = Field(
        default="p5",
        description="NVENC编码预设（p1最快~p7最好，默认p5）",
    )
    I: int = Field(default=600, description="关键帧间隔（GOP），影响视频的可编辑性和压缩率")
    r: int = Field(default=4, description="B帧参考数，影响视频质量和编码速度")
    b: int = Field(default=3, description="B帧数量，影响视频质量和压缩率")


class ConfigModel(BaseModel):
    """
    视频压缩配置模型类，用于定义完整的视频压缩配置

    该类包含配置名称和编码器配置，用于完整描述一组视频压缩参数。
    """

    name: str = Field(default="default", description="配置名称，用于标识不同的压缩配置")
    x264: EncoderConfigModel = Field(
        default_factory=EncoderConfigModel, description="编码器配置参数"
    )


class ConfigsModel(BaseModel):
    """
    配置集合模型类，用于管理多个视频压缩配置

    该类包含一个配置列表，用于存储和管理应用程序支持的所有视频压缩配置。
    """

    configs: list[ConfigModel] = Field(
        default_factory=lambda: [ConfigModel()], description="视频压缩配置列表"
    )
