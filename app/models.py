from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, BigInteger, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.sql import func
from app.database import Base
import uuid

reflection_mode_enum = ENUM('guided', 'collaborative', name='reflection_mode', create_type=False)
user_type_enum = ENUM('user', 'admin', name='user_type_enum', create_type=False)

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=True)
    email = Column(String(256), unique=True, nullable=False)
    phone_number = Column(BigInteger, nullable=True)
    user_type = Column(user_type_enum, default='user')
    proficiency_score = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(SmallInteger, default=1)
    is_anonymous = Column(Boolean, nullable=True, default=None)


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
    system_prompt = Column(Text, nullable=True)   

class Feedback(Base):
    """Feedback model for collecting user experience feedback"""
    __tablename__ = "feedback"
    
    feedback_no = Column(SmallInteger, primary_key=True)
    feedback_text = Column(Text, nullable=True)

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
    delivery_mode = Column(SmallInteger, default=None, nullable=True) 
    is_anonymous = Column(Boolean, nullable=True, default=None)
    sender_name = Column(String, nullable=True, default=None)
    feedback_type = Column(SmallInteger, ForeignKey("feedback.feedback_no"), default=0)  # Links to feedback table

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

class DistressLog(Base):
    __tablename__ = "distress_logs"
    
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reflection_id = Column(UUID(as_uuid=True), ForeignKey("reflections.reflection_id"), nullable=False)
    message_id = Column(BigInteger, ForeignKey("messages.message_id"), nullable=False)
    distress_level = Column(SmallInteger, nullable=False)  
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    invite_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invite_code = Column(String(64), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), unique=True, nullable=True)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint('invite_code', name='uq_invite_code'),
        UniqueConstraint('user_id', name='uq_invite_user_id'),  
    )

class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True)
    otp = Column(String(6), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())