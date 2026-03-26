/* ========================================
   FITAI STORE — Shared Data Layer
   localStorage-backed persistence
   ======================================== */

const FitStore = (() => {
  // ─── Helpers ───
  function _get(key, fallback) {
    try {
      const raw = localStorage.getItem('fitai_' + key);
      return raw ? JSON.parse(raw) : fallback;
    } catch { return fallback; }
  }
  function _set(key, val) {
    localStorage.setItem('fitai_' + key, JSON.stringify(val));
  }
  function _todayStr() {
    return new Date().toISOString().split('T')[0];
  }
  function _daysBetween(a, b) {
    return Math.round((new Date(b) - new Date(a)) / 86400000);
  }

  // ═══════════════════════════════════════
  //  PROFILE
  // ═══════════════════════════════════════
  function getProfile() {
    return _get('profile', {
      name: 'Athlete',
      age: 25,
      gender: 'Male',
      fitness_level: 'Intermediate',
      weight: 75,
      height: 178,
      goal: 'Muscle Gain (Hypertrophy)',
      equipment: 'Full Gym (Barbells, Machines, Cables)',
      days_per_week: 4,
      session_duration: 60,
      plan_duration: 4,
      limitations: ''
    });
  }
  function setProfile(p) { _set('profile', p); }

  // ═══════════════════════════════════════
  //  ACTIVE PLAN
  // ═══════════════════════════════════════
  function getActivePlan() { return _get('active_plan', null); }
  function setActivePlan(plan) {
    if (plan) {
      plan._activated_on = _todayStr();
      plan._current_week = 0;
      plan._current_day = 0;
    }
    _set('active_plan', plan);
  }
  function clearActivePlan() { localStorage.removeItem('fitai_active_plan'); }

  function getTodayWorkout() {
    const plan = getActivePlan();
    if (!plan || !plan.weekly_schedule) return null;

    const activatedOn = plan._activated_on || _todayStr();
    const daysSince = _daysBetween(activatedOn, _todayStr());
    const daysPerWeek = 7;
    const weekIdx = Math.floor(daysSince / daysPerWeek) % (plan.weekly_schedule.length || 1);
    const dayOfWeek = new Date().getDay(); // 0=Sun

    const week = plan.weekly_schedule[weekIdx];
    if (!week || !week.days) return null;

    // Map JS day (0=Sun) to plan day names
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const todayName = dayNames[dayOfWeek];

    // Find matching day or fallback to index
    let todayPlan = week.days.find(d => d.day && d.day.toLowerCase() === todayName.toLowerCase());
    if (!todayPlan && week.days.length > 0) {
      // Fallback: use day index within available days
      const activeDays = week.days.filter(d => d.workout && d.workout.length > 0);
      if (activeDays.length > 0) {
        todayPlan = activeDays[dayOfWeek % activeDays.length];
      }
    }
    return { workout: todayPlan, weekNum: weekIdx + 1, plan_name: plan.plan_name };
  }

  // ═══════════════════════════════════════
  //  WORKOUT LOG
  // ═══════════════════════════════════════
  function getWorkoutLog() {
    return _get('workout_log', []);
  }
  function addWorkout(entry) {
    const log = getWorkoutLog();
    entry.id = Date.now();
    entry.date = entry.date || _todayStr();
    log.unshift(entry);
    _set('workout_log', log);
    return entry;
  }
  function removeWorkout(id) {
    const log = getWorkoutLog().filter(w => w.id !== id);
    _set('workout_log', log);
  }

  // ═══════════════════════════════════════
  //  BODY MEASUREMENTS
  // ═══════════════════════════════════════
  function getMeasurements() {
    return _get('measurements', []);
  }
  function addMeasurement(entry) {
    const list = getMeasurements();
    entry.id = Date.now();
    entry.date = entry.date || _todayStr();
    list.unshift(entry);
    _set('measurements', list);
    return entry;
  }

  // ═══════════════════════════════════════
  //  FOOD LOG  (keyed by date)
  // ═══════════════════════════════════════
  function _foodKey(date) { return 'food_' + (date || _todayStr()); }
  function getFoodLog(date) { return _get(_foodKey(date), []); }
  function addFood(food, date) {
    const log = getFoodLog(date);
    food.id = Date.now();
    log.push(food);
    _set(_foodKey(date), log);
    return log;
  }
  function removeFood(id, date) {
    const log = getFoodLog(date).filter(f => f.id !== id);
    _set(_foodKey(date), log);
    return log;
  }

  // ═══════════════════════════════════════
  //  HYDRATION  (keyed by date)
  // ═══════════════════════════════════════
  function _waterKey(date) { return 'water_' + (date || _todayStr()); }
  function getHydration(date) { return _get(_waterKey(date), 0); }
  function setHydration(count, date) { _set(_waterKey(date), count); }

  // ═══════════════════════════════════════
  //  SAVED NUTRITION PLAN
  // ═══════════════════════════════════════
  function getNutritionPlan() { return _get('nutrition_plan', null); }
  function setNutritionPlan(plan) { _set('nutrition_plan', plan); }

  // ═══════════════════════════════════════
  //  COMPUTED STATS
  // ═══════════════════════════════════════
  function getStats() {
    const log = getWorkoutLog();
    const measurements = getMeasurements();
    const profile = getProfile();
    const today = _todayStr();

    // Total workouts
    const totalWorkouts = log.length;

    // Total calories
    const totalCalories = log.reduce((s, w) => s + (Number(w.cal) || 0), 0);

    // Total hours
    const totalMinutes = log.reduce((s, w) => s + (Number(w.dur) || 0), 0);
    const totalHours = (totalMinutes / 60).toFixed(1);

    // Current streak — count consecutive days with workouts ending at today or yesterday
    let streak = 0;
    if (log.length > 0) {
      const uniqueDates = [...new Set(log.map(w => w.date))].sort().reverse();
      const checkDate = new Date(today);
      // Allow starting from today or yesterday
      let startIdx = uniqueDates.indexOf(today);
      if (startIdx === -1) {
        const yesterday = new Date(checkDate);
        yesterday.setDate(yesterday.getDate() - 1);
        const yStr = yesterday.toISOString().split('T')[0];
        startIdx = uniqueDates.indexOf(yStr);
      }
      if (startIdx !== -1) {
        let prev = new Date(uniqueDates[startIdx]);
        streak = 1;
        for (let i = startIdx + 1; i < uniqueDates.length; i++) {
          const cur = new Date(uniqueDates[i]);
          const diff = _daysBetween(uniqueDates[i], prev.toISOString().split('T')[0]);
          if (diff === 1) {
            streak++;
            prev = cur;
          } else {
            break;
          }
        }
      }
    }

    // This month's workouts
    const thisMonth = today.substring(0, 7);
    const monthWorkouts = log.filter(w => w.date && w.date.startsWith(thisMonth)).length;

    // This week's calories
    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekStartStr = weekStart.toISOString().split('T')[0];
    const weekCalories = log.filter(w => w.date >= weekStartStr).reduce((s, w) => s + (Number(w.cal) || 0), 0);

    // Last month comparison
    const lastMonth = new Date();
    lastMonth.setMonth(lastMonth.getMonth() - 1);
    const lastMonthStr = lastMonth.toISOString().split('T')[0].substring(0, 7);
    const lastMonthWorkouts = log.filter(w => w.date && w.date.startsWith(lastMonthStr)).length;

    // Latest weight
    const latestWeight = measurements.length > 0 ? measurements[0].weight : profile.weight;
    const latestFat = measurements.length > 0 ? measurements[0].body_fat : null;

    // Active plan info
    const plan = getActivePlan();
    let planInfo = null;
    if (plan) {
      const tw = getTodayWorkout();
      planInfo = {
        name: plan.plan_name,
        todayFocus: tw?.workout?.focus || 'Rest Day',
        weekNum: tw?.weekNum || 1
      };
    }

    return {
      totalWorkouts,
      totalCalories,
      totalHours,
      totalMinutes,
      streak,
      monthWorkouts,
      weekCalories,
      lastMonthWorkouts,
      latestWeight,
      latestFat,
      planInfo,
      profileName: profile.name || 'Athlete'
    };
  }

  // ═══════════════════════════════════════
  //  TICKER DATA
  // ═══════════════════════════════════════
  function getTickerItems() {
    const s = getStats();
    const items = [];
    if (s.planInfo) {
      items.push(`WEEK ${s.planInfo.weekNum} · ${s.planInfo.todayFocus.toUpperCase()}`);
    }
    items.push(`STREAK ${s.streak} DAY${s.streak !== 1 ? 'S' : ''}`);
    items.push(`CALORIES BURNED ${s.totalCalories.toLocaleString()}`);
    if (s.planInfo) {
      items.push(`PLAN: ${s.planInfo.name || 'ACTIVE'}`);
    }
    items.push(`WORKOUTS THIS MONTH ${s.monthWorkouts}`);
    items.push(`TOTAL SESSIONS ${s.totalWorkouts}`);
    return items;
  }

  // ═══════════════════════════════════════
  //  SEED DATA (first-time only)
  // ═══════════════════════════════════════
  function seedIfEmpty() {
    if (getWorkoutLog().length > 0) return; // Already has data

    const today = new Date();
    const seedWorkouts = [
      { type: 'Legs', dur: 55, cal: 420, intensity: 'Hard', mood: '💪 Strong', notes: 'New squat PR: 120kg!' },
      { type: 'Chest & Triceps', dur: 50, cal: 380, intensity: 'Moderate', mood: '😐 Okay', notes: '' },
      { type: 'Back & Biceps', dur: 60, cal: 440, intensity: 'Hard', mood: '🔥 On Fire', notes: 'Deadlift felt great' },
      { type: 'Full Body', dur: 45, cal: 360, intensity: 'Moderate', mood: '💪 Strong', notes: '' },
      { type: 'Cardio / HIIT', dur: 30, cal: 300, intensity: 'Max Effort', mood: '😴 Tired', notes: 'Brutal session' },
      { type: 'Shoulders & Arms', dur: 50, cal: 350, intensity: 'Moderate', mood: '💪 Strong', notes: '' },
      { type: 'Legs', dur: 60, cal: 450, intensity: 'Hard', mood: '🔥 On Fire', notes: 'Deep squats' },
      { type: 'Chest & Triceps', dur: 55, cal: 400, intensity: 'Hard', mood: '😐 Okay', notes: 'Bench PR 80kg' },
    ];
    seedWorkouts.forEach((w, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - (i * 2 + 1));
      w.date = d.toISOString().split('T')[0];
      w.id = Date.now() - i * 100000;
      const log = _get('workout_log', []);
      log.push(w);
      _set('workout_log', log);
    });

    // Seed measurements
    const seedMeasurements = [
      { weight: 75.2, body_fat: 16.4 },
      { weight: 75.8, body_fat: 16.8 },
      { weight: 76.4, body_fat: 17.1 },
      { weight: 77.0, body_fat: 17.5 },
      { weight: 77.8, body_fat: 17.9 },
      { weight: 78.5, body_fat: 18.2 },
    ];
    seedMeasurements.forEach((m, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - (i * 7));
      m.date = d.toISOString().split('T')[0];
      m.id = Date.now() - i * 50000;
      const list = _get('measurements', []);
      list.push(m);
      _set('measurements', list);
    });
  }

  // ═══════════════════════════════════════
  //  PUBLIC API
  // ═══════════════════════════════════════
  return {
    getProfile, setProfile,
    getActivePlan, setActivePlan, clearActivePlan, getTodayWorkout,
    getWorkoutLog, addWorkout, removeWorkout,
    getMeasurements, addMeasurement,
    getFoodLog, addFood, removeFood,
    getHydration, setHydration,
    getNutritionPlan, setNutritionPlan,
    getStats, getTickerItems,
    seedIfEmpty
  };
})();

// Seed sample data on first visit
FitStore.seedIfEmpty();
