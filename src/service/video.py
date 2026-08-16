import logging
import os
import subprocess
import time
from typing import Optional

from src import meta
from src.model.message import (
    CompressionCurrentProgressMessage,
    CompressionErrorMessage,
    CompressionFinishedMessage,
    CompressionStartMessage,
    CompressionTotalProgressMessage,
)
from src.model.video import (
    Task,
    VideoFile,
    is_progress_line,
    resolve_progress_time_ms,
    resolve_time_str,
)
from src.service.config import ConfigService
from src.service.message import MessageService
from src.utils import timer


def _build_ffmpeg_command(
    ffmpeg_path: str,
    input_file: str,
    output_path: str,
    cfg,
    delete_audio: bool,
) -> str:
    """
    根据编码器 + 码率控制模式拼装 ffmpeg 命令。

    关键：不同编码器的参数集不通用——
    - libx264/libx265 软编：preset/refs/bf/me_method/psy-rd/aq-mode 等高级参数
    - h264_nvenc/hevc_nvenc 硬编：preset(p1~p7)/rc/cq/multipass/spatial-aq
    - h264_amf 硬编：usage/quality/rc 等
    把 x264 专有参数丢给 NVENC 会直接报 "Option not found"。
    """
    encoder = cfg.encoder
    # auto：自动探测 GPU 可用编码器（NVENC > AMF > 软编）
    if encoder == "auto":
        encoder = resolve_encoder(ffmpeg_path)
        logging.info(f"自动选择编码器: {encoder}")
    rc = cfg.rate_control

    # ---------- 视频编码参数 ----------
    if encoder in ("libx264", "libx265"):
        parts = [
            f'"{ffmpeg_path}"',
            "-y",
            "-i",
            f'"{input_file}"',
            "-c:v",
            encoder,
            "-preset",
            cfg.preset,
            "-g",
            str(cfg.I),
            "-refs",
            str(cfg.r),
            "-bf",
            str(cfg.b),
        ]
        # x264 专有质量参数（x265 不认 me_method/psy-rd/aq-mode，需区分）
        if encoder == "libx264":
            parts += [
                "-me_method",
                "umh",
                "-sc_threshold",
                "60",
                "-b_strategy",
                "1",
                "-qcomp",
                "0.5",
                "-psy-rd",
                "0.3:0",
                "-aq-mode",
                "2",
                "-aq-strength",
                "0.8",
            ]
        else:
            parts += ["-x265-params", "aq-mode=2:aq-strength=0.8"]
        # 码率控制
        if rc == "crf":
            parts += ["-crf", str(cfg.crf)]
        elif rc == "abr":
            parts += ["-b:v", f"{cfg.bitrate}k"]
        elif rc == "capped_crf":
            parts += ["-crf", str(cfg.crf), "-maxrate", f"{cfg.maxrate}k", "-bufsize", f"{cfg.bufsize}k"]

    elif encoder in ("h264_nvenc", "hevc_nvenc"):
        parts = [
            f'"{ffmpeg_path}"',
            "-y",
            "-i",
            f'"{input_file}"',
            "-c:v",
            encoder,
            "-preset",
            cfg.nvenc_preset,
            "-rc",
            "vbr",
            "-spatial-aq",
            "1",
            "-multipass",
            "qres",
        ]
        if rc == "crf":
            parts += ["-cq", str(int(cfg.crf))]
        elif rc == "abr":
            parts += ["-b:v", f"{cfg.bitrate}k"]
        elif rc == "capped_crf":
            parts += ["-cq", str(int(cfg.crf)), "-maxrate", f"{cfg.maxrate}k", "-bufsize", f"{cfg.bufsize}k"]

    elif encoder == "h264_amf":
        parts = [
            f'"{ffmpeg_path}"',
            "-y",
            "-i",
            f'"{input_file}"',
            "-c:v",
            encoder,
            "-usage",
            "high_quality",
            "-quality",
            "high_quality",
        ]
        if rc == "crf":
            parts += ["-rc", "qvbr", "-qvbr_quality_level", str(int(cfg.crf))]
        elif rc == "abr":
            parts += ["-rc", "cbr", "-b:v", f"{cfg.bitrate}k", "-enforce_hrd", "1"]
        elif rc == "capped_crf":
            parts += ["-rc", "vbr_peak", "-b:v", f"{cfg.bitrate}k", "-maxrate", f"{cfg.maxrate}k", "-bufsize", f"{cfg.bufsize}k"]

    else:  # 未知编码器兜底
        raise ValueError(f"不支持的编码器: {encoder}")

    # ---------- 音频参数 ----------
    audio_out = True
    if delete_audio:
        parts.append("-an")
        audio_out = False
    elif cfg.audio_bitrate > 0:
        parts += ["-c:a", "aac", "-b:a", f"{cfg.audio_bitrate}k"]
    else:
        # 自适应：探测原视频音频码率，保持同码率转码
        src_br = _probe_audio_bitrate(input_file, ffmpeg_path)
        if src_br and src_br > 0:
            parts += ["-c:a", "aac", "-b:a", f"{src_br}k"]
            logging.info(f"音频自适应: 原音频 {src_br}kbps → 输出 {src_br}kbps")
        else:
            parts.append("-an")
            audio_out = False

    # ---------- 输出参数 ----------
    parts += ["-movflags", "faststart"]
    # 只映射第一条视频流，避免 -map 0: 把字幕/数据流也带进来
    parts += ["-map", "0:v:0"]
    if audio_out:
        # 尾部加 ? 容错：源文件无音轨时不报错
        parts += ["-map", "0:a:0?"]

    parts.append(f'"{output_path}"')
    # 进度输出到 stdout（pipe:1），key=value 格式便于解析；关闭默认 stats
    parts.append("-progress")
    parts.append("pipe:1")
    parts.append("-nostats")
    return " ".join(parts)


def resolve_encoder(ffmpeg_path: str) -> str:
    """
    自动探测可用的硬件编码器

    优先级：h264_nvenc > h264_amf > libx264
    通过检查 ffmpeg 编译是否包含对应编码器 + 运行时是否可用来判断。
    NVENC 需要 N 卡 + NVIDIA 驱动（用 nvidia-smi 确认）；
    AMF 需要 A 卡 + AMD 驱动（暂用 ffmpeg 编译列表判断）。

    Args:
        ffmpeg_path: ffmpeg 可执行文件路径

    Returns:
        str: 实际可用的编码器名
    """
    try:
        # 列出 ffmpeg 支持的所有编码器
        r = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        encoders = (r.stdout or "") + (r.stderr or "")

        # 1. NVIDIA NVENC：ffmpeg 支持 + nvidia-smi 可执行（确认 N 卡驱动在）
        if "h264_nvenc" in encoders and _nvidia_available():
            return "h264_nvenc"
        # 2. AMD AMF 次之
        if "h264_amf" in encoders:
            return "h264_amf"
        # 3. Intel QSV
        if "h264_qsv" in encoders:
            return "h264_qsv"
        # 4. 都没有则回退软编
        logging.warning("未检测到硬件编码器，回退到 CPU 软编 (libx264)")
        return "libx264"
    except Exception as e:
        logging.warning(f"硬件编码器探测失败，回退 libx264: {e}")
        return "libx264"


def _nvidia_available() -> bool:
    """
    检查 NVIDIA GPU 驱动是否可用（nvidia-smi 能跑）
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _probe_audio_bitrate(input_file: str, ffmpeg_path: str) -> int:
    """
    探测原视频音频码率（kbps）

    tools 目录没有 ffprobe，用 ffmpeg -i 的 stderr 输出解析。
    解析失败或没有音频流时返回 0（调用方自行降级）。

    Args:
        input_file: 输入视频文件路径
        ffmpeg_path: ffmpeg 可执行文件路径

    Returns:
        int: 音频码率 kbps；0=无音频/探测失败
    """
    try:
        r = subprocess.run(
            [ffmpeg_path, "-i", input_file],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        import re

        # 匹配形如: Audio: aac (LC) ..., 128 kb/s
        m = re.search(r"Audio:.*?(\d+)\s*kb/s", r.stderr or "")
        if m:
            return int(m.group(1))
        return 0
    except Exception as e:
        logging.warning(f"音频码率探测失败: {e}")
        return 0


class VideoService:
    """
    视频处理服务类，提供视频压缩和处理的核心功能

    该类作为应用程序的核心服务之一，负责视频文件的压缩处理，支持单个文件处理和批量任务处理。
    它使用FFmpeg、x264、NeroAACEnc等工具实现视频压缩，并通过消息服务发送处理状态和进度信息，
    使UI能够实时更新处理进度。
    """

    _instance: Optional["VideoService"] = None

    running_process: list[subprocess.Popen] = []

    def __init__(self) -> None:
        if self._instance is not None:
            raise ValueError("VideoService 是单例类，不能重复实例化")

        self.message_service = MessageService.get_instance()

    @staticmethod
    def get_instance() -> "VideoService":
        """
        获取 VideoService 的单例实例

        Returns:
            VideoService: VideoService 的单例实例
        """
        if VideoService._instance is None:
            VideoService._instance = VideoService()

        return VideoService._instance

    @timer
    @staticmethod
    def process_single_file(
        file: VideoFile,
        config_name: str,
        delete_audio: bool,
        delete_source: bool,
        encoder: str = "",
        rate_control: str = "",
        bitrate: int = 0,
        crf: float = 0.0,
        audio_bitrate: int = 0,
    ):
        """
        处理单个视频文件的压缩任务

        Args:
            file: 视频文件对象，包含源文件路径和输出路径信息
            config_name: 压缩配置文件名，用于获取压缩参数
            delete_audio: 是否删除视频中的音频轨道
            delete_source: 是否在压缩完成后删除源文件
            encoder: 编码器覆盖（空=用配置）
            rate_control: 码率控制模式覆盖（空=用配置）
            bitrate: 目标码率 kbps 覆盖（0=用配置）
            crf: CRF 覆盖（0=用配置）
            audio_bitrate: 音频码率 kbps 覆盖（0=用配置）

        Raises:
            ValueError: 当配置文件不存在或媒体信息读取错误时抛出
            subprocess.CalledProcessError: 当压缩命令执行失败时抛出
        """
        config_service = ConfigService.get_instance()

        # 读取配置
        config = config_service.get_config(config_name)
        if config is None:
            logging.error(f"配置文件 {config_name} 不存在")
            raise ValueError(f"配置文件 {config_name} 不存在")

        # 应用运行时覆盖（UI 传入的优先于 config 预设）
        cfg = config.x264
        if encoder:
            cfg.encoder = encoder
        if rate_control:
            cfg.rate_control = rate_control
        if bitrate > 0:
            cfg.bitrate = bitrate
        if crf > 0:
            cfg.crf = crf
        if audio_bitrate > 0:
            cfg.audio_bitrate = audio_bitrate

        # Generate output filename
        output_path = file.output_path

        ffmpeg_path = meta.FFMPEG_PATH
        input_file = file.file_path

        # 按编码器 + 码率控制模式生成命令
        command = _build_ffmpeg_command(
            ffmpeg_path=ffmpeg_path,
            input_file=input_file,
            output_path=output_path,
            cfg=cfg,
            delete_audio=delete_audio,
        )

        logging.info(f"执行命令: {command}")

        # 使用Popen创建子进程并添加到running_process列表
        process = subprocess.Popen(
            command,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并stdout和stderr到stdout
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        VideoService.running_process.append(process)

        # 等待进程完成，同时解析进度
        cur_time: float = -0.01  # 当前视频播放时间
        total_time: float = -1  # 视频总时长
        update_time = time.time()  # 上次更新进度的时间
        while process.poll() is None:
            line = ""
            try:
                stdout = process.stdout
                if not stdout:
                    continue

                line = stdout.readline()

                if not is_progress_line(line):
                    # -progress pipe:1 模式下 Duration 会输出到 stdout，也解析
                    if total_time == -1 and "Duration" in line:
                        # 解析视频总时长
                        total_time = resolve_time_str(
                            line.split("Duration: ")[1].split(",")[0]
                        )
                        logging.debug(f"视频总时长: {total_time}")

                    if line.strip() == "":
                        continue

                    logging.debug(f"{line.strip()}")
                    continue

                # 解析当前播放时间（out_time_ms 微秒 → 秒）
                cur_time = resolve_progress_time_ms(line)

                # 发送进度
                if update_time < time.time() - 1:
                    update_time = time.time()
                    MessageService.get_instance().send_message(
                        CompressionCurrentProgressMessage(
                            file_name=file.file_path,
                            current=cur_time,
                            total=total_time,
                        )
                    )

            except Exception as e:
                logging.error(f"读取 stdout 时出错:  {e} 输出: {line.strip()}")

        stdout, stderr = process.communicate()

        # 从running_process列表中移除已完成的进程
        if process in VideoService.running_process:
            VideoService.running_process.remove(process)

        # Log command output
        if stdout:
            logging.debug(f"command stdout: {stdout.strip()}")
        if stderr:
            logging.warning(f"command stderr: {stderr.strip()}")

        # Check return code
        if process.returncode != 0:
            logging.error(f"命令执行失败，退出码: {process.returncode}")
            raise subprocess.CalledProcessError(process.returncode, command)

        # Delete source if requested
        if delete_source and os.path.exists(output_path):
            logging.debug(f"存在输出文件：{output_path}，删除源文件: {file.file_path}")
            os.remove(file.file_path)

    @timer
    @staticmethod
    def process_task(task: Task):
        """
        处理视频压缩任务，支持批量处理多个视频文件

        Args:
            task: 视频处理任务对象，包含待处理文件列表和处理配置

        该方法会：
        1. 发送任务开始消息
        2. 遍历处理任务中的每个视频文件
        3. 发送当前文件处理进度消息
        4. 调用process_single_file处理单个文件
        5. 处理可能出现的异常并发送错误消息
        6. 发送任务完成消息
        """
        message_service = MessageService.get_instance()

        logging.info(f"process task: {task.info}")

        logging.debug(f"process task sequence: {task.video_sequence}")

        if task.files_num == 0:
            message_service.send_message(
                CompressionErrorMessage("错误", "没有找到可处理的视频文件")
            )
            return

        message_service.send_message(CompressionStartMessage(task.files_num))

        # Process each file
        for index, video_file in enumerate(task.video_sequence, 1):
            logging.debug(
                f"process file: {video_file.file_path}, index: {index}, total: {task.files_num}"
            )

            # Notify start of processing
            message_service.send_message(
                CompressionTotalProgressMessage(
                    index - 1,
                    task.files_num,
                    video_file.file_path,
                )
            )

            try:
                VideoService.clean_temp_files()
                VideoService.process_single_file(
                    file=video_file,
                    config_name=task.info.process_config_name,
                    delete_audio=task.info.delete_audio,
                    delete_source=task.info.delete_source,
                    encoder=task.info.encoder,
                    rate_control=task.info.rate_control,
                    bitrate=task.info.bitrate,
                    crf=task.info.crf,
                    audio_bitrate=task.info.audio_bitrate,
                )
            except Exception as e:
                logging.error(f"处理文件 {video_file.file_path} 失败: {e}")
                message_service.send_message(
                    CompressionErrorMessage(
                        "错误", f"处理文件 {video_file.file_path} 失败: {e}"
                    )
                )
            finally:
                VideoService.clean_temp_files()

        # Signal completion
        message_service.send_message(
            CompressionFinishedMessage(len(task.video_sequence))
        )

    @staticmethod
    def clean_temp_files():
        """
        清理视频处理过程中生成的临时文件

        该方法会遍历meta.TEMP_FILES中定义的所有临时文件路径，
        并删除存在的临时文件。如果删除失败，会记录警告日志但不会抛出异常。

        Returns:
            None
        """
        for temp_file in meta.TEMP_FILES:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    logging.warning(f"删除临时文件 {temp_file} 失败: {e}")

    @staticmethod
    def stop_process():
        """
        停止当前正在运行的视频处理进程

        该方法会终止running_process中存储的子进程，
        并等待其退出。如果进程未运行或已退出，
        则不执行任何操作。

        Returns:
            None
        """
        logging.info(
            f"正在停止所有视频处理进程，共 {len(VideoService.running_process)} 个进程"
        )

        # 创建进程列表的副本，避免在遍历过程中修改原列表
        processes_to_stop = list(VideoService.running_process)

        for process in processes_to_stop:
            try:
                logging.debug(f"正在终止进程: {process.pid}")
                process.terminate()

                # 等待进程退出，最多等待5秒
                logging.debug(f"等待进程 {process.pid} 退出")
                process.wait(timeout=5)

                if process.returncode is None:
                    # 如果进程仍未退出，强制终止
                    logging.warning(f"进程 {process.pid} 未在5秒内退出，正在强制终止")
                    process.kill()
                    # 再次等待确认进程退出
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logging.error(f"进程 {process.pid} 无法强制终止")
                else:
                    logging.debug(
                        f"进程 {process.pid} 已退出，退出码: {process.returncode}"
                    )
            except Exception as e:
                logging.error(f"处理进程 {process.pid} 时发生错误: {e}")

        # 清空进程列表
        VideoService.running_process.clear()
        logging.info("所有视频处理进程已停止")

    @staticmethod
    def is_processing() -> bool:
        """
        检查是否有正在运行的视频处理进程

        Returns:
            bool: 如果有正在运行的进程则返回True，否则返回False
        """
        return len(VideoService.running_process) > 0
