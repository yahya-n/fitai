"""
FitAI — Database Models (SQLAlchemy + SQLite)
==============================================
All records are hard-linked to user_id for data isolation.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


class User(db.Model):
    """User account — supports email/password and Google OAuth."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # Null for Google-only users
    name = db.Column(db.String(100), nullable=False, default="Athlete")
    google_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    plans = db.relationship("Plan", backref="user", lazy=True, cascade="all, delete-orphan")
    workouts = db.relationship("WorkoutLog", backref="user", lazy=True, cascade="all, delete-orphan")
    measurements = db.relationship("Measurement", backref="user", lazy=True, cascade="all, delete-orphan")
    profile = db.relationship("UserProfile", backref="user", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserProfile(db.Model):
    """Fitness profile — synced from the frontend FitStore."""
    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    age = db.Column(db.Integer, default=25)
    gender = db.Column(db.String(20), default="Male")
    fitness_level = db.Column(db.String(50), default="Intermediate")
    weight = db.Column(db.Float, default=75.0)
    height = db.Column(db.Float, default=178.0)
    goal = db.Column(db.String(100), default="General Fitness")
    equipment = db.Column(db.String(200), default="Full Gym")
    days_per_week = db.Column(db.Integer, default=4)
    session_duration = db.Column(db.Integer, default=60)
    limitations = db.Column(db.String(500), default="")
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "age": self.age, "gender": self.gender,
            "fitness_level": self.fitness_level,
            "weight": self.weight, "height": self.height,
            "goal": self.goal, "equipment": self.equipment,
            "days_per_week": self.days_per_week,
            "session_duration": self.session_duration,
            "limitations": self.limitations,
        }


class Plan(db.Model):
    """AI-generated workout plan, hard-linked to user_id."""
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_name = db.Column(db.String(200), default="Workout Plan")
    plan_data = db.Column(db.Text, nullable=False)  # JSON blob
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def get_data(self):
        import json
        try:
            return json.loads(self.plan_data)
        except Exception:
            return {}

    def to_dict(self):
        return {
            "id": self.id,
            "plan_name": self.plan_name,
            "plan_data": self.get_data(),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkoutLog(db.Model):
    """Logged workout session, hard-linked to user_id."""
    __tablename__ = "workout_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    workout_type = db.Column(db.String(100), default="General")
    duration = db.Column(db.Integer, default=0)  # minutes
    calories = db.Column(db.Integer, default=0)
    intensity = db.Column(db.String(50), default="Moderate")
    mood = db.Column(db.String(50), default="😐 Okay")
    notes = db.Column(db.String(500), default="")
    date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.workout_type,
            "dur": self.duration,
            "cal": self.calories,
            "intensity": self.intensity,
            "mood": self.mood,
            "notes": self.notes,
            "date": self.date.isoformat() if self.date else None,
        }


class Measurement(db.Model):
    """Body measurement entry, hard-linked to user_id."""
    __tablename__ = "measurements"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    weight = db.Column(db.Float, nullable=True)
    body_fat = db.Column(db.Float, nullable=True)
    date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "weight": self.weight,
            "body_fat": self.body_fat,
            "date": self.date.isoformat() if self.date else None,
        }


def init_db(app):
    """Initialize database and create tables."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
