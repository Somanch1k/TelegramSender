from app.database.database import DatabaseManager
from app.services.admin_service import AdminService
from app.services.group_service import GroupService
from app.utils.logger import setup_logger


class Application:

    def __init__(self):

        self.logger = setup_logger()

        self.logger.info("Инициализация приложения...")

        self.database = DatabaseManager()
        self.admins = AdminService(self.database)
        self.groups = GroupService(self.database)
        self.sender = None
        self.scheduler = None
        self.interface_bot = None

        self.logger.info("База данных успешно подключена.")

    def run(self):

        self.logger.info("Telegram Sender успешно запущен.")

        self.database.close()

        self.logger.info("Приложение завершило работу.")
