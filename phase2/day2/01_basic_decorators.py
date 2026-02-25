import time
import functools

def log_call(func):
    @functools.wraps(func)
    def wrapper(*args,**kwargs):
        print(f"Calling function {func.__name__}:{args}:{kwargs}")
        result=func(*args,**kwargs)
        print(f"End of the function {func.__name__}:{args}:{kwargs}")
        return result
    return wrapper

@log_call
def say_hello(name:str):
    print(f"Hello, {name}")

say_hello("Bob")

def timer(func):
    @functools.wraps(func)
    def wrapper(*args,**kwargs):
        start=time.perf_counter()
        result=func(*args,**kwargs)
        end=time.perf_counter()
        print(f"[TIMER] {func.__name__} took {end-start:.4f} seconds")
        return result
    return wrapper

@timer
def slow_function():
    time.sleep(0.5)
    return "Done"

#slow_function()

def repeat(times:int):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kwargs):
            for _ in range(times):
                result=func(*args,**kwargs)
            return result
        return wrapper
    return decorator

@repeat(3)
def greet(name:str):
    print(f"Hello, {name}")

#greet("Alice")


def bad_decorator(func):
    def wrapper(*args,**kwargs):
        return func(*args,**kwargs)
    return wrapper

def good_decorator(func):
    @functools.wraps(func)
    def wrapper(*args,**kwargs):
        return func(*args,**kwargs)
    return wrapper

@bad_decorator
def bad_function():
    """this is a bad function"""
    pass

@good_decorator
def good_function():
    """this is a good function"""
    pass

#print(bad_function.__name__)
#print(good_function.__name__)