
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class UserInfoSchema(Base):
    __tablename__ = 'user_info'
    
    # Define the columns based on the table structure
    uid = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing field
    name = Column(String)  # Text column for name
    gold = Column(Integer)  # Integer column for gold
    level = Column(Integer)  # Integer column for level