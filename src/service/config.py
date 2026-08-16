import json
import logging
from typing import Optional

from src import meta
from src.model.config import ConfigModel, ConfigsModel
from src.model.message import ConfigLoadMessage
from src.service.message import MessageService


class ConfigService:
    """
    配置服务类，用于管理应用程序的配置信息

    该类采用单例模式实现，确保应用程序中只有一个配置服务实例。
    它负责从配置文件加载配置，并提供访问配置的方法。
    """

    _instance: Optional["ConfigService"] = None

    def __init__(self) -> None:
        """
        初始化配置服务实例

        从配置文件加载配置数据，并使用ConfigModel解析配置。

        Raises:
            ValueError: 当尝试创建多个ConfigService实例时抛出
            FileNotFoundError: 当配置文件不存在时抛出
            json.JSONDecodeError: 当配置文件格式错误时抛出
        """
        if ConfigService._instance is not None:
            raise ValueError("ConfigService already initialized")

        config_file_path = meta.CONFIG_FILE_PATH

        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                configs = json.load(f)

            self.configs_model = ConfigsModel(**configs)
        except (TypeError, FileNotFoundError, ValueError) as e:
            match e:
                case FileNotFoundError():
                    logging.warning(f"Config file not found: {config_file_path}")
                case TypeError():
                    logging.error(f"Decode config file error: {e}")
                case ValueError():
                    logging.error(f"ValueError occur when load config: {e}")
                case _:
                    logging.error(f"Error loading config file: {e}")

            logging.warning("generate default config.")

            # 重新生成默认配置
            self.configs_model = ConfigsModel()

            # 导出默认配置
            with open(config_file_path, "w", encoding="utf-8") as f:
                f.write(self.configs_model.model_dump_json(indent=4))

        # 发送配置加载消息
        config_names = self.get_config_name_list()

        logging.info(f"load config names: {config_names}")
        logging.debug(
            f"configs: {[c.model_dump() for c in self.configs_model.configs]}"
        )

        MessageService.get_instance().send_message(ConfigLoadMessage(config_names))

    @staticmethod
    def get_instance() -> "ConfigService":
        """
        获取配置服务的单例实例

        Returns:
            ConfigService: 配置服务的单例实例

        该方法采用懒加载模式，只有在第一次调用时才会创建ConfigService实例。
        """
        if ConfigService._instance is None:
            ConfigService._instance = ConfigService()

        return ConfigService._instance

    def get_config(self, name: str) -> Optional[ConfigModel]:
        """
        根据名称获取指定的配置对象

        Args:
            name (str): 配置名称

        Returns:
            Optional[ConfigModel]: 配置模型对象，如果不存在则返回None
        """

        for config in self.configs_model.configs:
            if config.name == name:
                return config
        return None

    def get_config_name_list(self) -> list[str]:
        """
        获取所有配置名称的列表

        Returns:
            list[str]: 所有配置名称的列表
        """
        return [c.name for c in self.configs_model.configs]
