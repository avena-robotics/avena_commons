from collections import deque


class LimitedQueue:
    """
    A queue with a maximum size. When the queue is full, adding a new item will remove the oldest item.

    :param max_size: The maximum size of the queue.
    :type max_size: int
    """

    def __init__(self, max_size: int = 10):
        self.queue = deque(maxlen=max_size)
        self.max_size = max_size

    def add(self, item):
        self.queue.append(item)

    def get_all(self):
        return list(self.queue)
