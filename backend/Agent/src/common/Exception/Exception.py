
class TaskCreateError(Exception):
    pass


class ParentTaskBuildError(TaskCreateError):
    pass

class ChildTaskBuildError(TaskCreateError):
    pass


class TaskSaveError(Exception):
    pass

class ParentTaskSaveError(TaskSaveError):
    pass

class ChildTaskSaveError(TaskSaveError):
    pass

#
# class TaskPersistError(TaskCreateError):
#     pass

class QueuePublishError(TaskCreateError):
    pass
