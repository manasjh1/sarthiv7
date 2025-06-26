from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, BigInteger, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.sql import func
from app.database import Base
import uuid

# PostgreSQL ENUMs
reflection_mode_enum = ENUM('guided', 'collaborative', name='reflection_mode', create_type=False)
reflection_delivery_mode_enum = ENUM('whatsapp', 'email', 'private', name='reflection_delivery_mode', create_type=False)
user_type_enum = ENUM('user', 'admin', name='user_type_enum', create_type=False)

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=False)
    email = Column(String(256), unique=True, nullable=False)
    phone_number = Column(BigInteger, nullable=True)
    user_type = Column(user_type_enum, default='user')
    proficiency_score = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(SmallInteger, default=1)

class StageDict(Base):
    __tablename__ = "stages_dict"
    
    stage_no = Column(Integer, primary_key=True)
    stage_name = Column(String(256), nullable=False, unique=True)
    status = Column(SmallInteger, default=1)
    prompt = Column(Text, nullable=True)

class CategoryDict(Base):
    __tablename__ = "category_dict"
    
    category_no = Column(Integer, primary_key=True)
    category_name = Column(String(256), nullable=False, unique=True)
    status = Column(SmallInteger, default=1)

class Reflection(Base):
    __tablename__ = "reflections"
    
    reflection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_no = Column(Integer, ForeignKey("stages_dict.stage_no"), nullable=False)
    category_no = Column(Integer, ForeignKey("category_dict.category_no"), nullable=True)
    receiver_user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    giver_user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    mode = Column(reflection_mode_enum, default='guided')
    name = Column(String(256), nullable=True)
    relation = Column(String(256), nullable=True)
    status = Column(SmallInteger, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reflection = Column(Text, nullable=True)
    delivery_mode = Column(reflection_delivery_mode_enum, default='email')

class Message(Base):
    __tablename__ = "messages"
    
    message_id = Column(BigInteger, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    reflection_id = Column(UUID(as_uuid=True), ForeignKey("reflections.reflection_id"), nullable=False)
    sender = Column(SmallInteger, nullable=False)
    status = Column(SmallInteger, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_distress = Column(Boolean, default=False)
    stage_no = Column(Integer, ForeignKey("stages_dict.stage_no"), nullable=False)
