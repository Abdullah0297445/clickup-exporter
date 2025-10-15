class BaseExp(Exception):
    default_message = "Exception occurred."
    status = 500

    def __init__(self, status: int | None = None, message: str | None = None):
        if not status:
            status = self.status
        if not message:
            message = self.default_message
        self.message = message
        super().__init__(f"{status}: {message}")


class ExportError(BaseExp):
    pass


class ClickupTeamIDMissing(BaseExp):
    default_message = "Clickup Team ID is missing."
    status = 500
