from typing import Optional

from src import meta
from src.model.store import JSONStore


class StoreService:
    """
    存储服务类，用于管理应用程序的持久化存储

    该类采用单例模式实现，封装了JSONStore的操作，
    提供了访问和管理应用程序数据的方法。
    """

    _instance: Optional["StoreService"] = None

    def __init__(self) -> None:
        """
        初始化存储服务实例

        创建并打开JSONStore对象，用于持久化存储应用程序数据。

        Raises:
            ValueError: 当尝试创建多个StoreService实例时抛出
            FileNotFoundError: 当存储文件路径不存在时抛出
        """
        if StoreService._instance is not None:
            raise ValueError("StoreService 只能实例化一次")

        self.store: JSONStore = JSONStore(meta.STORE_PATH)

        self.store.open()

        StoreService._instance = self

    @staticmethod
    def get_instance() -> "StoreService":
        """
        获取存储服务的单例实例

        Returns:
            StoreService: 存储服务的单例实例

        该方法采用懒加载模式，只有在第一次调用时才会创建StoreService实例。
        """
        if StoreService._instance is None:
            StoreService._instance = StoreService()

        return StoreService._instance

    def get_store(self) -> JSONStore:
        """
        获取JSONStore实例

        Returns:
            JSONStore: JSONStore实例，用于直接操作存储的数据
        """
        return self.store

    def dump(self):
        """
        将内存中的数据保存到存储文件

        该方法调用JSONStore的dump方法，将当前内存中的数据持久化到磁盘。
        """
        self.store.dump()
