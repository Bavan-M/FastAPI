import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from sqlalchemy import Column,Integer,String,Boolean,DateTime,Text,ForeignKey,Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase,relationship
import enum
from sqlalchemy.sql import func
from sqlalchemy import Table

class Base(DeclarativeBase):
    # DeclarativeBase is the foundation class that allows you to define database tables as Python classes. 
    # It's the "magic" that turns your Python code into database tables.
    pass

# ENUMS — stored as strings in DB
class UserRole(str,enum.Enum):
    ADMIN="admin"
    USER="user"
    GUEST="guest"

class PostStatus(str,enum.Enum):
    DRAFT="draft"
    PUBLISHED="published"
    ARCHIVED="archived"

# MODELS
class TimestampMixin:
    """
    Reusable mixin — adds created_at and updated_at
    to any model that inherits it.
    Every table in production should have these.
    """
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  #Sets timestamp on INSERT only
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),        # Updates timestamp on EVERY UPDATE
        nullable=False
    )
    

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    username     = Column(String(50), unique=True, nullable=False, index=True)
    email        = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # nullable for OAuth users
    role         = Column(SAEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active    = Column(Boolean, default=True, nullable=False)
    auth_provider = Column(String(50), default="local", nullable=False)
    google_id    = Column(String(255), unique=True, nullable=True)

    # Relationships — defined here, used later in Day 3
    posts        = relationship("Post", back_populates="author", cascade="all, delete-orphan") #user relation with table Posts in two way(back_populates) and if deleted from user also deletes from posts
    api_keys     = relationship("APIKey", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self): #create the string representation of the object according to our needs.
        return f"<User id={self.id} username={self.username} role={self.role}>"


    
class Post(TimestampMixin, Base):
    __tablename__ = "posts"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(200), nullable=False)
    content     = Column(Text, nullable=False)
    status      = Column(SAEnum(PostStatus), default=PostStatus.DRAFT, nullable=False)
    author_id   = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Relationship back to user
    author      = relationship("User", back_populates="posts")
    tags        = relationship("Tag", secondary="post_tags", back_populates="posts")

    def __repr__(self):
        return f"<Post id={self.id} title={self.title[:30]} status={self.status}>"
    
class Tag(Base):
    __tablename__ = "tags"

    id    = Column(Integer, primary_key=True, index=True)
    name  = Column(String(50), unique=True, nullable=False, index=True)
    posts = relationship("Post", secondary="post_tags", back_populates="tags")

    def __repr__(self):
        return f"<Tag id={self.id} name={self.name}>"
    
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",  Integer, ForeignKey("tags.id",  ondelete="CASCADE"), primary_key=True)
)

class APIKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    hashed_key  = Column(String(255), unique=True, nullable=False)
    masked_key  = Column(String(20), nullable=False)
    owner_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    scopes      = Column(String(500), default="read")  # comma-separated
    usage_count = Column(Integer, default=0, nullable=False)

    owner = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey id={self.id} name={self.name} owner_id={self.owner_id}>"
    
if __name__ == "__main__":
    # Print all table definitions
    for table_name, table in Base.metadata.tables.items():
        print(f"\nTable: {table_name}")
        for col in table.columns:
            print(f"  {col.name:20} {col.type}  {'PK' if col.primary_key else ''} {'NULL' if col.nullable else 'NOT NULL'} {'UNIQUE' if col.unique else ''}")



# Table: users
#   id                   INTEGER  PK NOT NULL 
#   username             VARCHAR(50)   NOT NULL UNIQUE
#   email                VARCHAR(255)   NOT NULL UNIQUE
#   hashed_password      VARCHAR(255)   NULL 
#   role                 VARCHAR(5)   NOT NULL 
#   is_Active            BOOLEAN   NOT NULL 
#   auth_provider        VARCHAR(50)   NOT NULL 
#   google_id            VARCHAR(255)   NULL UNIQUE
#   created_At           DATETIME   NOT NULL 
#   updated_at           DATETIME   NOT NULL 

# Table: posts
#   id                   INTEGER  PK NOT NULL 
#   title                VARCHAR(200)   NOT NULL 
#   content              TEXT   NOT NULL
#   staus                VARCHAR(9)   NOT NULL
#   author_id            INTEGER   NOT NULL
#   created_At           DATETIME   NOT NULL
#   updated_at           DATETIME   NOT NULL

# Table: tags
#   id                   INTEGER  PK NOT NULL
#   name                 VARCHAR(50)   NOT NULL UNIQUE

# Table: post_tags
#   post_id              INTEGER  PK NOT NULL
#   tag_id               INTEGER  PK NOT NULL

# Table: api_keys
#   id                   INTEGER  PK NOT NULL
#   name                 VARCHAR(100)   NOT NULL
#   hashed_key           VARCHAR(255)   NOT NULL UNIQUE
#   masked_key           VARCHAR(20)   NOT NULL
#   owner_id             INTEGER   NOT NULL
#   is_active            BOOLEAN   NOT NULL
#   scopes               VARCHAR(500)   NULL
#   usage_count          INTEGER   NOT NULL
#   created_At           DATETIME   NOT NULL
#   updated_at           DATETIME   NOT NULL