
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class UserInfoSchema(Base):
    __tablename__ = 'user_info'
    
    # Define the columns based on the table structure
    uid = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing field
    name = Column(String)  # Text column for name
    gold = Column(Integer)  # Integer column for gold
    level = Column(Integer)  # Integer column for level
    avatar = Column(String)  # Text column for avatar
    login_type = Column(Integer)  # Integer column for login type
    guests = relationship("GuestsSchema", back_populates="user_info", uselist=False)  # If only one guest per user
    firebase_auth = relationship("FirebaseAuthSchema", back_populates="user_info", uselist=False)  # If only one firebase auth per user

class GuestsSchema(Base):
    __tablename__ = 'guests'
    
    guest_id = Column(String(255), primary_key=True)
    uid = Column(Integer, ForeignKey('user_info.uid'))
  
    user_info = relationship("UserInfoSchema", back_populates="guests")

class FirebaseAuthSchema(Base):
    __tablename__ = 'firebase_auth'
    
    firebase_user_id = Column(String(255), primary_key=True)
    uid = Column(Integer, ForeignKey('user_info.uid'))
    name = Column(String)
    sign_in_provider = Column(String)
    email = Column(String)
    picture = Column(String)
  
    user_info = relationship("UserInfoSchema", back_populates="firebase_auth")