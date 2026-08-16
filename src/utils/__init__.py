import logging
import os
import sys
from functools import wraps


def scan_directory(
    directory: str, extensions: list[str]
) -> tuple[list[str], list[str]]:
    """
    递归扫描指定目录，返回子文件夹列表和符合指定扩展名的文件列表

    Args:
        directory: 要扫描的根目录路径
        extensions: 要匹配的文件扩展名列表，必须包含点号（如[".mp4", ".avi"]），
                    匹配时不区分大小写

    Returns:
        tuple[list[str], list[str]]: 第一个元素是所有子文件夹的路径列表，
                                     第二个元素是符合扩展名的所有文件的路径列表

    该函数会：
    1. 扫描指定目录下的所有条目
    2. 将子文件夹和符合条件的文件分别添加到列表中
    3. 递归扫描每个子文件夹
    4. 返回完整的子文件夹列表和文件列表
    """
    subfolders, files = [], []

    for entry in os.scandir(directory):
        if entry.is_dir():
            subfolders.append(entry.path)
        elif entry.is_file() and os.path.splitext(entry.name)[1].lower() in extensions:
            files.append(entry.path)

    # Recursively scan subfolders
    for folder in list(subfolders):
        sf, f = scan_directory(folder, extensions)
        subfolders.extend(sf)
        files.extend(f)

    return subfolders, files


def timer(f):
    """
    计时器装饰器，用于测量函数执行时间

    Args:
        f: 要装饰的函数

    Returns:
        callable: 包装后的函数，执行时会打印函数名和执行时间
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        import time

        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        logging.debug(
            f"Function {f.__name__} executed in {end_time - start_time:.4f} seconds"
        )
        return result

    return wrapper


def get_path(path: str):
    """获取文件路径，即便是在打包后的环境中也能正常工作

    Args:
        path (str): 文件路径，支持相对路径和绝对路径
    """

    if hasattr(sys, "_MEIPASS"):
        # Running in a bundled environment
        return os.path.join(sys._MEIPASS, path)  # type: ignore[attr-defined]
    else:
        # Running in a development environment
        return os.path.join(os.getcwd(), path)
