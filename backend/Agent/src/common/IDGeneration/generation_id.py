import uuid


class IDGenerator:
    """
    ID生成器
    """
    def generate_id(self) -> str:
        """
        生成一个ID
        """
        return str(uuid.uuid4())





