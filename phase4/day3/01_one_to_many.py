#One user has many posts. One post belongs to one user.
import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine,async_sessionmaker
from sqlalchemy.orm import DeclarativeBase,relationship,selectinload,joinedload
from sqlalchemy import Column,String,Integer,Text,Boolean,ForeignKey,DateTime,func,select
import asyncio

load_dotenv("phase4/.env")

DATABASE_URL=os.getenv("DATABASE_URL")


engine=create_async_engine(url=DATABASE_URL,echo=True)
AsyncSessionLocal=async_sessionmaker(bind=engine,expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__="users_rel"
    id          =   Column(Integer,primary_key=True)
    username    =   Column(String(50),nullable=False)
    email       =   Column(String(225),nullable=False)

    posts       =   relationship("Post",back_populates="author",cascade="all, delete-orphan",lazy="noload")
    comments    =   relationship("Comment",back_populates="author",cascade="all, delete-orphan",lazy="noload")

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"
    
class Post(Base):
    __tablename__="posts_rel"
    id          =   Column(Integer,primary_key=True)
    title       =   Column(String(200),nullable=False)
    content     =   Column(Text,nullable=False)
    published   =   Column(Boolean,default=False)
    author_id   =   Column(Integer,ForeignKey("users_rel.id",ondelete="CASCADE"),nullable=False)
    created_at  =   Column(DateTime(timezone=True),server_default=func.now())

    author      =   relationship("User",back_populates="posts",lazy="noload")
    comments    =   relationship("Comment",back_populates="post",cascade="all, delete-orphan",lazy="noload")

    def __repr__(self):
        return f"<Post id={self.id} title={self.title[:30]}>"
    
class Comment(Base):
    __tablename__="comments_rel"

    id          =   Column(Integer,primary_key=True)
    content     =   Column(Text,nullable=False)
    author_id   =   Column(Integer,ForeignKey("users_rel.id",ondelete="CASCADE"))
    post_id     =   Column(Integer,ForeignKey("posts_rel.id",ondelete="CASCADE"))
    created_at  =   Column(DateTime(timezone=True),server_default=func.now())

    author      =   relationship("User",back_populates="comments",lazy="noload")
    post        =   relationship("Post",back_populates="comments",lazy="noload")

    def __repr__(self):
        return f"<Comment id={self.id} post_id={self.post_id}>"
    


async def demo_one_to_many():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    
    async with AsyncSessionLocal() as db:
        alice=User(username="alice",email="alice@gmail.com")
        bob=User(username="bob",email="bob@gmail.com")
        db.add_all([alice,bob])
        await db.flush()

        post1=Post(title="FastAPI Basics",content="Content1.....",author_id=alice.id)
        post2=Post(title="Async SqlAlchemey",content="Content2.....",author_id=alice.id)
        post3=Post(title="Bob First Post",content="Content3......",author_id=bob.id)
        db.add_all([post1,post2,post3])
        await db.flush()

        c1=Comment(content="Great Post",author_id=bob.id,post_id=post1.id)
        c2=Comment(content="Very Helpful",author_id=alice.id,post_id=post1.id)
        c3=Comment(content="Thanks",author_id=alice.id,post_id=post3.id)
        db.add_all([c1,c2,c3])
        await db.commit()

        # --- QUERY PATTERN 1: Load user WITH posts ---
        # selectinload = 2 queries (users + posts separately)
        # Better for collections
        result=await db.execute(
            select(User).where(User.username=="alice").options(selectinload(User.posts))
        )
        print("------------------------------------------")
        print(result.scalar_one)
        print("------------------------------------------")
        alice=result.scalar_one()
        print(f"Alice has {len(alice.posts)} posts:")
        for p in alice.posts:
            print(f"-> {p.title}")

        # --- QUERY PATTERN 2: Load post WITH author ---
        # joinedload = 1 JOIN query
        # Better for single objects
        result=await db.execute(
            select(Post).where(Post.id==post1.id).options(joinedload(Post.author))
        )
        post=result.unique().scalar_one()
        print(f"\nPost '{post.title}' written by: {post.author}")

if __name__ == "__main__":
    asyncio.run(demo_one_to_many())
        





