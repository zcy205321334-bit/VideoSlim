from queue import Queue
from typing import Optional

from src.model.message import IMessage


class MessageService:
    """
    消息服务类，用于管理应用程序中的消息传递

    该类采用单例模式实现，提供了线程安全的消息队列机制，
    用于在应用程序的不同组件之间传递消息。
    """

    _instance: Optional["MessageService"] = None

    def __init__(self) -> None:
        """
        初始化消息服务实例

        创建一个线程安全的消息队列，用于存储和传递消息。

        Raises:
            ValueError: 当尝试创建多个MessageService实例时抛出
        """
        if MessageService._instance is not None:
            raise ValueError("MessageService already initialized")

        self.queue = Queue()

    @staticmethod
    def get_instance() -> "MessageService":
        """
        获取消息服务的单例实例

        Returns:
            MessageService: 消息服务的单例实例

        该方法采用懒加载模式，只有在第一次调用时才会创建MessageService实例。
        """
        if MessageService._instance is None:
            MessageService._instance = MessageService()

        return MessageService._instance

    def send_message(self, message: IMessage):
        """
        发送消息到消息队列

        Args:
            message: 要发送的消息对象，必须实现IMessage接口

        该方法将消息放入队列，等待接收者处理。
        """
        self.queue.put(message)

    def receive_message(self) -> IMessage:
        """
        从消息队列接收消息（阻塞式）

        Returns:
            IMessage: 接收到的消息对象

        该方法会阻塞当前线程，直到有消息可用或超时。
        """
        return self.queue.get()

    def try_receive_message(self) -> Optional[IMessage]:
        """
        尝试从消息队列接收消息（非阻塞式）

        Returns:
            Optional[IMessage]: 接收到的消息对象，如果队列为空则返回None

        该方法不会阻塞当前线程，如果队列中没有消息，则立即返回None。
        """
        if self.queue.empty():
            return None
        return self.queue.get_nowait()
