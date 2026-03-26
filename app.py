"""
FitAI — Main Application (Refactored)
======================================
- Multi-model AI fallback via ai_engine
- Authentication with JWT + Google OAuth
- SQLite database with user data isolation
- Robust JSON parsing with json_repair fallback
- Rate limiting on auth endpoints
"""

from flask import Flask, render_template, request, jsonify, g, redirect
import json
import os
import logging
from datetime import datetime, timezone

# ── Load .env BEFORE local imports (they read os.environ at module level) ──
from dotenv import load_dotenv
load_dotenv()

# ── Local modules ──
from models import db, User, UserProfile, Plan, WorkoutLog, Measurement, init_db
from auth import auth_bp, login_required, get_current_user, refresh_cookies_if_needed, GOOGLE_CLIENT_ID
from ai_engine import call_ai, call_ai_json, extract_json, get_failed_models

# ═══════════════════════════════════════
#  APP SETUP
# ═══════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fitai-secret-key-dev-2026")

# Database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'fitai.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize
init_db(app)
app.register_blueprint(auth_bp)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("fitai")

# ── After-request: refresh JWT cookies if needed ──
@app.after_request
def after_request(response):
    return refresh_cookies_if_needed(response)


# ═══════════════════════════════════════
#  PAGE ROUTES (Protected)
# ═══════════════════════════════════════

@app.route("/")
def index():
    user = get_current_user()
    if user:
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/login")
def login_page():
    user = get_current_user()
    if user:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/planner")
@login_required
def planner():
    return render_template("planner.html")


@app.route("/progress")
@login_required
def progress():
    return render_template("progress.html")


@app.route("/nutrition")
@login_required
def nutrition():
    return render_template("nutrition.html")


# ═══════════════════════════════════════
#  AI API ENDPOINTS (Protected)
# ═══════════════════════════════════════

@app.route("/api/generate-plan", methods=["POST"])
@login_required
def generate_plan():
    data = request.json
    profile = data.get("profile", {})
    user = g.current_user

    system_prompt = (
        "You are FitAI, an elite personal fitness coach and exercise scientist. "
        "Create detailed, science-backed, personalized workout plans. "
        "Structure your response as a complete workout plan with days, exercises, "
        "sets, reps, rest periods, and coaching notes."
    )

    user_message = f"""Create a personalized {profile.get('duration', 4)}-week workout plan for:
- Name: {profile.get('name', user.name)}
- Age: {profile.get('age', 25)} years
- Gender: {profile.get('gender', 'Not specified')}
- Fitness Level: {profile.get('fitness_level', 'Beginner')}
- Goal: {profile.get('goal', 'General Fitness')}
- Available Equipment: {profile.get('equipment', 'No equipment')}
- Workout Days per Week: {profile.get('days_per_week', 3)}
- Session Duration: {profile.get('session_duration', 45)} minutes
- Health Limitations: {profile.get('limitations', 'None')}
- Current Weight: {profile.get('weight', 'Not specified')} kg
- Height: {profile.get('height', 'Not specified')} cm

Respond with this JSON structure:
{{
  "plan_name": "string",
  "overview": "string",
  "weekly_schedule": [
    {{
      "week": 1,
      "days": [
        {{
          "day": "Monday",
          "focus": "string",
          "warmup": [{{"exercise": "string", "duration": "string"}}],
          "workout": [
            {{
              "exercise": "string",
              "sets": number,
              "reps": "string",
              "rest": "string",
              "notes": "string",
              "muscle_group": "string"
            }}
          ],
          "cooldown": [{{"exercise": "string", "duration": "string"}}],
          "estimated_calories": number
        }}
      ]
    }}
  ],
  "nutrition_tips": ["string"],
  "progression_notes": "string",
  "safety_reminders": ["string"]
}}"""

    plan_data, error = call_ai_json(
        [{"role": "user", "content": user_message}],
        system_prompt,
    )

    if plan_data and not error:
        # Save plan to database, linked to user_id
        try:
            db_plan = Plan(
                user_id=user.id,
                plan_name=plan_data.get("plan_name", "Workout Plan"),
                plan_data=json.dumps(plan_data),
            )
            db.session.add(db_plan)
            db.session.commit()
            plan_data["_db_id"] = db_plan.id
        except Exception as e:
            logger.warning(f"Failed to save plan to DB: {e}")

        return jsonify({"success": True, "plan": plan_data})
    else:
        return jsonify({"success": False, "error": error or "Failed to parse AI response"})


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])
    user = g.current_user

    system_prompt = (
        "You are FitAI Coach, a friendly, motivating, and knowledgeable AI fitness assistant. "
        "You help users with workout advice, form tips, nutrition guidance, injury prevention, and motivation. "
        "Keep responses concise, practical, and encouraging. Use fitness terminology appropriately. "
        f"The user's name is {user.name}."
    )

    messages = history[-12:] + [{"role": "user", "content": message}]
    response = call_ai(messages, system_prompt)

    # Clean response
    import re
    if "<think>" in response:
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

    return jsonify({"success": True, "response": response})


@app.route("/api/analyze-progress", methods=["POST"])
@login_required
def analyze_progress():
    data = request.json
    workouts = data.get("workouts", [])
    profile = data.get("profile", {})

    system_prompt = (
        "You are a fitness analytics expert. Analyze workout data and provide insights."
    )

    user_message = f"""Analyze this workout history and provide insights:
Profile: {json.dumps(profile)}
Recent Workouts: {json.dumps(workouts)}

Respond with JSON:
{{
  "overall_assessment": "string",
  "strengths": ["string"],
  "areas_to_improve": ["string"],
  "recommendations": ["string"],
  "estimated_progress": {{
    "strength_gain": "string",
    "endurance_improvement": "string",
    "consistency_score": number
  }},
  "next_week_focus": "string",
  "motivational_message": "string"
}}"""

    result, error = call_ai_json(
        [{"role": "user", "content": user_message}],
        system_prompt,
    )

    if result:
        return jsonify({"success": True, "analysis": result})
    return jsonify({"success": False, "error": error or "Failed to parse analysis"})


@app.route("/api/nutrition-plan", methods=["POST"])
@login_required
def nutrition_plan():
    data = request.json
    profile = data.get("profile", {})

    system_prompt = (
        "You are a certified sports nutritionist. Create personalized nutrition plans."
    )

    user_message = f"""Create a nutrition plan for:
- Goal: {profile.get('goal', 'General Fitness')}
- Weight: {profile.get('weight', 70)} kg
- Height: {profile.get('height', 170)} cm
- Age: {profile.get('age', 25)}
- Activity Level: {profile.get('fitness_level', 'Moderate')}
- Dietary Preferences: {profile.get('diet', 'No restrictions')}

Respond with JSON:
{{
  "daily_calories": number,
  "macros": {{"protein_g": number, "carbs_g": number, "fat_g": number}},
  "meal_plan": [
    {{
      "meal": "string",
      "time": "string",
      "foods": [{{"item": "string", "amount": "string", "calories": number}}],
      "total_calories": number
    }}
  ],
  "hydration": "string",
  "supplements": ["string"],
  "pre_workout": "string",
  "post_workout": "string",
  "tips": ["string"]
}}"""

    result, error = call_ai_json(
        [{"role": "user", "content": user_message}],
        system_prompt,
    )

    if result:
        return jsonify({"success": True, "plan": result})
    return jsonify({"success": False, "error": error or "Failed to parse nutrition plan"})


@app.route("/api/exercise-info", methods=["POST"])
@login_required
def exercise_info():
    data = request.json
    exercise = data.get("exercise", "")

    system_prompt = (
        "You are a certified personal trainer and exercise physiologist. "
        "Provide detailed exercise information."
    )

    user_message = f"""Provide detailed information about: {exercise}

JSON format:
{{
  "name": "string",
  "category": "string",
  "muscle_groups": {{"primary": ["string"], "secondary": ["string"]}},
  "difficulty": "string",
  "equipment": ["string"],
  "instructions": ["string"],
  "common_mistakes": ["string"],
  "variations": ["string"],
  "benefits": ["string"],
  "calories_per_minute": number
}}"""

    result, error = call_ai_json(
        [{"role": "user", "content": user_message}],
        system_prompt,
    )

    if result:
        return jsonify({"success": True, "info": result})
    return jsonify({"success": False, "error": error or "Failed to parse exercise info"})


# ═══════════════════════════════════════
#  DATA API ENDPOINTS (User-Isolated)
# ═══════════════════════════════════════

@app.route("/api/plans", methods=["GET"])
@login_required
def get_plans():
    """Get all plans for the current user."""
    plans = Plan.query.filter_by(user_id=g.current_user.id).order_by(Plan.created_at.desc()).all()
    return jsonify({"plans": [p.to_dict() for p in plans]})


@app.route("/api/plans/<int:plan_id>/activate", methods=["POST"])
@login_required
def activate_plan(plan_id):
    """Activate a specific plan (deactivate all others)."""
    plan = Plan.query.filter_by(id=plan_id, user_id=g.current_user.id).first()
    if not plan:
        return jsonify({"error": "Plan not found"}), 404

    # Deactivate all other plans
    Plan.query.filter_by(user_id=g.current_user.id).update({"is_active": False})
    plan.is_active = True
    db.session.commit()
    return jsonify({"success": True, "plan": plan.to_dict()})


@app.route("/api/workouts", methods=["GET", "POST"])
@login_required
def workouts_api():
    """GET: List user's workouts. POST: Log a new workout."""
    user_id = g.current_user.id

    if request.method == "POST":
        data = request.json or {}
        log = WorkoutLog(
            user_id=user_id,
            workout_type=data.get("type", "General"),
            duration=int(data.get("dur", 0)),
            calories=int(data.get("cal", 0)),
            intensity=data.get("intensity", "Moderate"),
            mood=data.get("mood", "😐 Okay"),
            notes=data.get("notes", ""),
        )
        if data.get("date"):
            try:
                log.date = datetime.fromisoformat(data["date"]).date()
            except Exception:
                pass
        db.session.add(log)
        db.session.commit()
        return jsonify({"success": True, "workout": log.to_dict()})

    # GET
    logs = WorkoutLog.query.filter_by(user_id=user_id).order_by(WorkoutLog.date.desc()).limit(50).all()
    return jsonify({"workouts": [w.to_dict() for w in logs]})


@app.route("/api/workouts/<int:workout_id>", methods=["DELETE"])
@login_required
def delete_workout(workout_id):
    """Delete a workout — only if it belongs to the current user."""
    log = WorkoutLog.query.filter_by(id=workout_id, user_id=g.current_user.id).first()
    if not log:
        return jsonify({"error": "Workout not found"}), 404
    db.session.delete(log)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/measurements", methods=["GET", "POST"])
@login_required
def measurements_api():
    """GET: List measurements. POST: Add new measurement."""
    user_id = g.current_user.id

    if request.method == "POST":
        data = request.json or {}
        m = Measurement(
            user_id=user_id,
            weight=float(data.get("weight")) if data.get("weight") else None,
            body_fat=float(data.get("body_fat")) if data.get("body_fat") else None,
        )
        db.session.add(m)
        db.session.commit()
        return jsonify({"success": True, "measurement": m.to_dict()})

    # GET
    items = Measurement.query.filter_by(user_id=user_id).order_by(Measurement.date.desc()).limit(30).all()
    return jsonify({"measurements": [m.to_dict() for m in items]})


@app.route("/api/profile", methods=["GET", "POST"])
@login_required
def profile_api():
    """GET/POST user fitness profile (isolated by user_id)."""
    user = g.current_user

    if request.method == "POST":
        data = request.json or {}
        profile = UserProfile.query.filter_by(user_id=user.id).first()
        if not profile:
            profile = UserProfile(user_id=user.id)
            db.session.add(profile)

        for field in ["age", "gender", "fitness_level", "weight", "height",
                       "goal", "equipment", "days_per_week", "session_duration", "limitations"]:
            if field in data:
                setattr(profile, field, data[field])

        # Also update user name if provided
        if data.get("name"):
            user.name = data["name"]

        db.session.commit()
        return jsonify({"success": True, "profile": profile.to_dict()})

    # GET
    profile = UserProfile.query.filter_by(user_id=user.id).first()
    if profile:
        result = profile.to_dict()
        result["name"] = user.name
        return jsonify({"profile": result})
    return jsonify({"profile": {"name": user.name}})


# ═══════════════════════════════════════
#  HEALTH / MONITORING
# ═══════════════════════════════════════

@app.route("/api/health")
def health():
    """Health check endpoint — also shows failed models for monitoring."""
    return jsonify({
        "status": "ok",
        "failed_models": get_failed_models()[-10:],  # Last 10
    })


# ═══════════════════════════════════════
#  RUN
# ═══════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
