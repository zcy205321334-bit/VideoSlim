import json
import logging
from abc import ABC, abstractmethod


class IStore(ABC):
    """
    存储接口类
    """

    @abstractmethod
    def get(self, key: str, default: str = "") -> str:
        """
        获取存储中的值

        Args:
            key (str): 键值
            default (str, optional): 默认值。如果键不存在，则返回默认值。默认值为""。

        Returns:
            str: 存储中的值
        """
        pass

    @abstractmethod
    def set(self, key: str, value: str):
        """
        设置存储中的值

        Args:
            key (str): 键值
            value (str): 要设置的值
        """
        pass


class IPersistentStore(IStore):
    """
    持久化存储接口类，继承自IStore接口，用于定义持久化存储的方法。
    """

    @property
    @abstractmethod
    def file_path(self) -> str:
        """
        获取存储文件路径

        Returns:
            str: 存储文件路径
        """
        pass

    @abstractmethod
    def open(self):
        """
        打开存储，准备进行读写操作。
        """
        pass

    @abstractmethod
    def dump(self):
        """
        保存到持久化文件
        """
        pass


class JSONStore(IPersistentStore):
    """
    JSON存储类，实现IStore接口，用于存储和获取JSON格式的数据。
    """

    def __init__(self, file_path: str):
        """
        初始化JSONStore类

        Args:
            file_path (str): JSON文件路径
        """
        self._file_path = file_path

    @property
    def file_path(self) -> str:
        """
        获取存储文件路径

        Returns:
            str: 存储文件路径
        """
        return self._file_path

    def open(self):
        """
        加载 JSON 文件中的数据
        """
        self.data = {}

        try:
            with open(self.file_path, "r") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            logging.error(f"Error loading config file: {self.file_path} not found")
            self.data = {}

    def get(self, key: str, default: str = "") -> str:
        return self.data.get(key, default)

    def set(self, key: str, value: str):
        self.data[key] = value

    def dump(self):
        """
        保存存储中的数据到JSON文件
        """
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)
