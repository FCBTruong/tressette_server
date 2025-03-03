
from sqlalchemy import DECIMAL, TIMESTAMP, Boolean, Column, DateTime, ForeignKey, Integer, BigInteger, String, Text, func
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class UserInfoSchema(Base):
    __tablename__ = 'user_info'
    
    # Define the columns based on the table structure
    uid = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing field
    name = Column(String)  # Text column for name
    gold = Column(BigInteger)  # Integer column for gold
    level = Column(Integer)  # Integer column for level
    avatar = Column(String)  # Text column for avatar
    avatar_third_party = Column(String)  # Text column for third party avatar
    login_type = Column(Integer)  # Integer column for login type
    game_count = Column(Integer, default=0)  # Integer column for game count
    win_count = Column(Integer, default=0)  # Integer column for win count
    exp = Column(BigInteger, default=0)  # Integer column for experience
    is_active = Column(Boolean, nullable=False, default=True)
    last_time_received_support = Column(Integer, default=0)
    received_startup=Column(Boolean, default=False)
    guests = relationship("GuestsSchema", back_populates="user_info", uselist=False)  # If only one guest per user
    firebase_auth = relationship("FirebaseAuthSchema", back_populates="user_info", uselist=False)  # If only one firebase auth per user
    paypal_orders = relationship("PayPalOrder", back_populates="user")
    
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


class Friendship(Base):
    __tablename__ = 'friendships'

    friendship_id = Column(Integer, primary_key=True, autoincrement=True)
    user1_id = Column(Integer, ForeignKey('user_info.uid', ondelete='CASCADE'), nullable=False)
    user2_id = Column(Integer, ForeignKey('user_info.uid', ondelete='CASCADE'), nullable=False)
    status = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class AppleTransactions(Base):
    __tablename__ = 'apple_transactions'

    transaction_id = Column(String(255), primary_key=True)
    original_transaction_id = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey('user_info.uid'), nullable=False)
    product_id = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    purchase_date = Column(String, nullable=False)
    original_purchase_date = Column(String, nullable=False)
    is_trial_period = Column(Boolean, nullable=False, default=False)
    purchase_date_ms = Column(BigInteger, nullable=False)
    original_purchase_date_ms = Column(BigInteger, nullable=False)
    in_app_ownership_type = Column(String(255), nullable=False, default='PURCHASED')


class PayPalOrder(Base):
    __tablename__ = "paypal_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("user_info.uid"), nullable=False)  # Foreign Key to user_info.uid
    pack_id = Column(String(50), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationship to UserInfoSchema
    user = relationship("UserInfoSchema", back_populates="paypal_orders")