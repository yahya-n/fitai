# ⚡ FitAI — Adaptive AI Workout & Nutrition Platform

FitAI is a cutting-edge fitness platform that transforms how users interact with their health data. By leveraging a custom multi-model AI engine, FitAI generates hyper-personalized, multi-week workout routines, constructs tailored nutrition guides, and provides contextual 24/7 coaching.

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **🧠 Multi-Model AI Engine** | Intelligent try-catch-rotate logic across **7 top-tier OpenRouter models** (Llama 3.3 70B, DeepSeek V3, Gemma 3) to guarantee high availability and premium quality responses. |
| **🛡 Robust Data Parsing** | A highly resilient extraction layer utilizing custom RegEx and `json_repair` to perfectly parse complex JSON objects from unpredictable LLM outputs. |
| **🏋️ AI Workout Generation** | Produces comprehensive, day-by-day workout plans strictly personalized by a user's age, goals, fitness level, and available equipment. |
| **🥗 AI Nutrition Planner** | Auto-generates macro breakdowns, meal-by-meal plans, and hydration strategies based on dietary restrictions and fitness targets. |
| **💬 Interactive AI Coach** | A 24/7 contextual chat assistant providing science-backed form tips, recovery advice, and motivation. |
| **🔐 Secure Authentication** | Email/Password login (Bcrypt), **Google OAuth 2.0** integration, IP rate-limiting, and strict HTTP-only JWT access/refresh cookie management. |
| **📊 Intelligent Dashboard** | Live progress tracking, streak counting, muscle volume breakdown rings, and 28-day activity charts powered by Chart.js. |

---

## 🏗 Tech Stack

- **Backend:** Python 3, Flask, Flask-SQLAlchemy
- **Security:** PyJWT, Bcrypt, Flask-Limiter, Google Auth
- **AI Integration:** OpenRouter API (`requests`), json-repair
- **Database:** SQLite (Relational structure with strict `user_id` data isolation)
- **Frontend:** HTML5, Modern CSS3 (Glassmorphism & Dark UI), Vanilla JavaScript, Chart.js

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have Python 3.9+ installed.

### 2. Install Dependencies
Clone the repository and install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Environment Variables Configuration
To run FitAI, you need an OpenRouter API key. You can get a free key by signing up at [OpenRouter](https://openrouter.ai/).

Create a `.env` file in the root directory (or rename `.env.example`):
```env
# Required for AI Generation (Get free key from OpenRouter)
OPENROUTER_API_KEY="your-openrouter-key-here"

# Security (Change in production)
SECRET_KEY="fitai-secret-key-dev-2026"
JWT_SECRET="fitai-jwt-secret-change-in-production-2026"

# Optional: Google OAuth Integration
GOOGLE_CLIENT_ID="your-google-client-id"
```

### 4. Run the Application
Start the Flask development server:
```bash
python app.py
```

### 5. Access the Platform
Navigate your browser to: **http://localhost:5000**

---

## 📂 Project Structure

```text
fitai/
├── app.py                # Main Flask backend, Routes, and API controllers
├── ai_engine.py          # Multi-Model LLM routing, Fallback logic, JSON repair
├── auth.py               # Authentication, JWT handling, Google OAuth, Rate limiting
├── models.py             # SQLAlchemy Database models (User, Plan, WorkoutLog, etc.)
├── requirements.txt      # Python dependencies
├── .env                  # Environment Variables
├── templates/            # Jinja2 HTML Templates
│   ├── base.html         # Base layout (Sidebar, Chat Panel)
│   ├── login.html        # Authentication UI
│   ├── dashboard.html    # Main stats dashboard and activity tracking
│   ├── planner.html      # AI Model Workout Generator
│   ├── progress.html     # Historical logging and measurement visualization
│   └── nutrition.html    # AI Nutrition planner
└── static/               
    ├── css/main.css      # Custom UI tokens, animations, and responsive layouts
    └── js/               
        ├── main.js       # Base UI interactions and chat logic
        └── fitai-store.js# Frontend data state management
```

## 🛡️ Data Privacy & Isolation

FitAI is built with user privacy in mind. 
- **Database Level:** Every plan, workout log, and measurement is hard-linked to a specific `user_id`.
- **API Level:** The `@login_required` middleware ensures users can only query, modify, or delete resources that explicitly belong to their authenticated JWT session.
- **Cookie Security:** Auth relies on strictly configured HTTP-only, secure cookies to prevent XSS attacks across sessions.
