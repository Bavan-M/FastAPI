class AppException(Exception):
    def __init__(self, status_code:int,error:str,message:str,details:dict=None):
        self.status_code=status_code
        self.error=error
        self.message=message
        self.details=details or {}

class UnAuthorizedException(AppException):
    def __init__(self,message:str="Authentication required"):
        super().__init__(401, "unauthorized", message)

class ForbiddenException(AppException):
    def __init__(self,message:str="Permission denied"):
        super().__init__(403, "forbidden", message)

class NotFoundExcpetion(AppException):
    def __init__(self,resource:str,identifier=None):
        super().__init__(
            404, 
            "not found",
            f"{resource} not found",
            {"resource":resource,"identifier":str(identifier) if identifier else None})
        
class ConflictException(AppException):
    def __init__(self, message:str):
        super().__init__(409, "conflict", message)

class RateLimitException(AppException):
    def __init__(self,message, retry_after:int=60):
        super().__init__(429, "rate limit exceeded", message, {"retry_after":retry_after})

class AccountLockedException(AppException):
    def __init__(self, minutes_remaining:int):
        super().__init__(423,
                        "account locked",
                        f"Account locked. Try again in {minutes_remaining}", 
                        {"retry_after_minutes":minutes_remaining})