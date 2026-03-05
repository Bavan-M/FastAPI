
class AppException(Exception):
    def __init__(self, status_code:int,error:str,message:str,details:dict = None):
        self.staus_code=status_code
        self.error=error
        self.message=message
        self.details=details or {}


class NotFoundException(AppException):
    def __init__(self, resource:str,identifier):
        super().__init__(
            status_code=404,
            error="not found", 
            message=f"{resource} {identifier} not found", 
            details={"resource":resource,"identifier":identifier})
        
class ForbiddenException(AppException):
    def __init__(self,message:str="you dont have permission"):
        super().__init__(
            status_code=403, 
            error="forbidden", 
            message=message)
        
class ConflictException(AppException):
    def __init__(self, resource:str,field:str,value:str):
        super().__init__(
            status_code=409, 
            error="conflict", 
            message=f"{resource} with {field},{value} already exists",
            details={"resource":resource,"field":field,"value":value})
        

class UnAuthorizedException(AppException):
    def __init__(self, message:str="Authentication required"):
        super().__init__(
            status_code=401, 
            error="unauthorized",
            message=message)
        


