#!/usr/bin/env python3
"""Interactive visualization server for typing tutor statistics."""

import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from flask import Flask, render_template_string
from plotly.subplots import make_subplots

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "stats.db"
ONE_WEEK = 7 * 24 * 3600

TOP_BIGRAMS = 100

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Typing Tutor Stats</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .chart { background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
        .stat-value { font-size: 32px; font-weight: bold; color: #2196F3; }
        .stat-label { color: #666; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Typing Tutor Statistics</h1>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Current CPS</div>
                <div class="stat-value">{{ current_cps }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Current Accuracy</div>
                <div class="stat-value">{{ current_accuracy }}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Lessons</div>
                <div class="stat-value">{{ total_lessons }}</div>
            </div>
        </div>
        <div class="chart">
            <div id="bigram-weights"></div>
        </div>
        <div class="chart">
            <div id="accuracy-speed"></div>
        </div>
        <div class="chart">
            <div id="daily-stats"></div>
        </div>
    </div>
    <script>
        var bigramData = {{ bigram_json | safe }};
        var accuracySpeedData = {{ accuracy_speed_json | safe }};
        var dailyStatsData = {{ daily_stats_json | safe }};
        Plotly.newPlot('bigram-weights', bigramData.data, bigramData.layout);
        Plotly.newPlot('accuracy-speed', accuracySpeedData.data, accuracySpeedData.layout);
        Plotly.newPlot('daily-stats', dailyStatsData.data, dailyStatsData.layout);
    </script>
</body>
</html>
"""


def get_bigram_weights() -> dict[str, float]:
    now = __import__("time").time()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT word, char_index, timestamp FROM mistakes").fetchall()
    weights: dict[str, float] = {}
    for word, index, ts in rows:
        bigram = (f"^{word[0].lower()}" if index == 0 else word[index - 1 : index + 1].lower())
        weights[bigram] = weights.get(bigram, 0) + math.exp((ts - now) / ONE_WEEK)
    return weights


def compute_arrhythmicity(timestamps_ns):
    """Compute standard deviation of inter-key intervals."""
    if len(timestamps_ns) < 3:
        return None
    intervals = [(timestamps_ns[i + 1] - timestamps_ns[i]) / 1e9 for i in range(len(timestamps_ns) - 1)]
    if len(intervals) < 2:
        return None
    mean_val = sum(intervals) / len(intervals)
    variance = sum((x - mean_val) ** 2 for x in intervals) / (len(intervals) - 1)
    return math.sqrt(variance)


def get_lesson_stats():
    """Fetch all lessons with computed accuracy, CPS, and arrhythmicity."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, text_required, text_typed, duration FROM lessons WHERE duration IS NOT NULL ORDER BY timestamp"
        )
        rows = cursor.fetchall()
        
        cursor.execute("SELECT lesson_id, timestamp FROM key_presses ORDER BY lesson_id, timestamp ASC")
        kp_rows = cursor.fetchall()

    # Group key presses by lesson
    from collections import defaultdict
    kp_map = defaultdict(list)
    for lid, ts in kp_rows:
        kp_map[lid].append(ts)

    stats = []
    for lesson_id, ts, text_required, text_typed, duration in rows:
        # Compute accuracy
        mistakes = 0
        total_typed = 0
        processed_typed = ""
        for char in text_typed:
            if char == "\b":
                if processed_typed:
                    processed_typed = processed_typed[:-1]
            else:
                total_typed += 1
                if len(processed_typed) < len(text_required):
                    if char != text_required[len(processed_typed)]:
                        mistakes += 1
                processed_typed += char

        if total_typed == 0:
            continue

        accuracy = ((total_typed - mistakes) / total_typed) * 100
        cps = len(processed_typed) / duration if duration > 0 else 0
        date = datetime.fromtimestamp(ts).date()
        
        # Compute arrhythmicity
        arrhythmicity = compute_arrhythmicity(kp_map.get(lesson_id, []))

        stats.append(
            {
                "timestamp": ts,
                "date": date,
                "accuracy": accuracy,
                "cps": cps,
                "arrhythmicity": arrhythmicity,
                "lesson_id": lesson_id,
            }
        )

    return stats


def aggregate_by_date(stats):
    """Aggregate stats by date (average accuracy, CPS, and arrhythmicity)."""
    daily = {}
    for stat in stats:
        date = stat["date"]
        if date not in daily:
            daily[date] = {"accuracy": [], "cps": [], "arrhythmicity": [], "timestamp": stat["timestamp"]}
        daily[date]["accuracy"].append(stat["accuracy"])
        daily[date]["cps"].append(stat["cps"])
        if stat["arrhythmicity"] is not None:
            daily[date]["arrhythmicity"].append(stat["arrhythmicity"])

    result = []
    for date in sorted(daily.keys()):
        acc_avg = sum(daily[date]["accuracy"]) / len(daily[date]["accuracy"])
        cps_avg = sum(daily[date]["cps"]) / len(daily[date]["cps"])
        arr_avg = sum(daily[date]["arrhythmicity"]) / len(daily[date]["arrhythmicity"]) if daily[date]["arrhythmicity"] else None
        result.append({"date": date, "accuracy": acc_avg, "cps": cps_avg, "arrhythmicity": arr_avg, "timestamp": daily[date]["timestamp"]})

    return result


def apply_exponential_smoothing(daily_stats):
    """Apply exponential smoothing with time-decay weights (same as tutor EMA)."""
    if not daily_stats:
        return [], [], []

    now = daily_stats[-1]["timestamp"]
    
    # Compute weights
    total_weight = 0.0
    weighted_acc = 0.0
    weighted_cps = 0.0
    weighted_arr = 0.0
    total_weight_arr = 0.0
    
    smoothed_acc = []
    smoothed_cps = []
    smoothed_arr = []
    
    for i, stat in enumerate(daily_stats):
        t_weeks = (stat["timestamp"] - now) / ONE_WEEK
        weight = math.exp(t_weeks)
        
        total_weight += weight
        weighted_acc += stat["accuracy"] * weight
        weighted_cps += stat["cps"] * weight
        
        smoothed_acc.append(weighted_acc / total_weight if total_weight > 0 else stat["accuracy"])
        smoothed_cps.append(weighted_cps / total_weight if total_weight > 0 else stat["cps"])
        
        if stat["arrhythmicity"] is not None:
            total_weight_arr += weight
            weighted_arr += stat["arrhythmicity"] * weight
            smoothed_arr.append(weighted_arr / total_weight_arr if total_weight_arr > 0 else stat["arrhythmicity"])
        else:
            smoothed_arr.append(None)
    
    return smoothed_acc, smoothed_cps, smoothed_arr


def compute_pareto_frontier(stats):
    """Compute Pareto frontier: points not dominated by any other (higher CPS and higher accuracy)."""
    if not stats:
        return [], []

    frontier = [
        s for s in stats
        if not any(o["cps"] >= s["cps"] and o["accuracy"] >= s["accuracy"] and (o["cps"] > s["cps"] or o["accuracy"] > s["accuracy"]) for o in stats)
    ]
    frontier.sort(key=lambda s: s["cps"])
    return [s["cps"] for s in frontier], [s["accuracy"] for s in frontier]


@app.route("/")
def index():
    stats = get_lesson_stats()

    if not stats:
        return render_template_string(
            HTML_TEMPLATE,
            current_cps="N/A",
            current_accuracy="N/A",
            total_lessons=0,
            bigram_json="{}",
            accuracy_speed_json="{}",
            daily_stats_json="{}",
        )

    # Current stats (last lesson)
    last = stats[-1]
    current_cps = f"{last['cps']:.2f}"
    current_accuracy = f"{last['accuracy']:.1f}"
    total_lessons = len(stats)

    # Bigram EMA weights
    bw = get_bigram_weights()
    top_bigrams = sorted(bw.items(), key=lambda x: x[1], reverse=True)[:TOP_BIGRAMS]
    bigram_fig = go.Figure(go.Treemap(
        labels=[b for b, _ in top_bigrams],
        parents=[""] * len(top_bigrams),
        values=[v for _, v in top_bigrams],
    ))
    bigram_fig.update_layout(
        title=f"Top {TOP_BIGRAMS} bigrams by EMA mistake frequency",
        height=350,
    )

    # Accuracy vs Speed scatter with Pareto frontier
    pareto_cps, pareto_acc = compute_pareto_frontier(stats)

    import time as _time
    now = _time.time()
    ws = [math.exp((s["timestamp"] - now) / ONE_WEEK) for s in stats]
    total_w = sum(ws)
    ema_cps_pt = sum(s["cps"] * w for s, w in zip(stats, ws)) / total_w
    ema_acc_pt = sum(s["accuracy"] * w for s, w in zip(stats, ws)) / total_w

    # Weighted linear regression: accuracy = a * cps + b
    import numpy as np
    xs = np.array([s["cps"] for s in stats])
    ys = np.array([s["accuracy"] for s in stats])
    coeffs = np.polyfit(xs, ys, 1, w=ws)
    a, b = coeffs
    reg_x = [xs.min(), xs.max()]
    reg_y = [a * reg_x[0] + b, a * reg_x[1] + b]
    denom = 1  # always valid with polyfit

    accuracy_speed = go.Figure()
    accuracy_speed.add_trace(
        go.Scatter(
            x=[s["cps"] for s in stats],
            y=[s["accuracy"] for s in stats],
            mode="markers",
            marker=dict(size=8, color=[s["timestamp"] for s in stats], colorscale="Viridis"),
            text=[s["date"].isoformat() for s in stats],
            hovertemplate="<b>%{text}</b><br>CPS: %{x:.2f}<br>Accuracy: %{y:.1f}%<extra></extra>",
            name="Lessons",
        )
    )
    accuracy_speed.add_trace(
        go.Scatter(
            x=pareto_cps,
            y=pareto_acc,
            mode="lines+markers",
            line=dict(color="red", width=2, dash="dash"),
            marker=dict(size=6, color="red"),
            name="Pareto Frontier",
            hovertemplate="CPS: %{x:.2f}<br>Accuracy: %{y:.1f}%<extra></extra>",
        )
    )
    accuracy_speed.add_trace(
        go.Scatter(
            x=reg_x,
            y=reg_y,
            mode="lines",
            line=dict(color="orange", width=2),
            name=f"Regression (slope {a:.2f})",
            hoverinfo="skip",
        )
    )
    accuracy_speed.add_trace(
        go.Scatter(
            x=[ema_cps_pt],
            y=[ema_acc_pt],
            mode="markers",
            marker=dict(size=14, color="yellow", symbol="star", line=dict(color="black", width=1)),
            name=f"EMA ({ema_cps_pt:.2f} CPS, {ema_acc_pt:.1f}%)",
            hovertemplate=f"EMA CPS: {ema_cps_pt:.2f}<br>EMA Accuracy: {ema_acc_pt:.1f}%<extra></extra>",
        )
    )
    accuracy_speed.update_layout(
        title="Accuracy vs Speed (with Pareto Frontier)",
        xaxis_title="Characters Per Second",
        yaxis_title="Accuracy (%)",
        hovermode="closest",
        height=400,
    )

    # Daily aggregated stats
    daily = aggregate_by_date(stats)
    smoothed_acc, smoothed_cps, smoothed_arr = apply_exponential_smoothing(daily)
    
    daily_stats = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                 specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
                                 vertical_spacing=0.12)
    
    # Accuracy and CPS
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=[d["accuracy"] for d in daily],
            name="Accuracy (daily avg)",
            mode="markers",
            marker=dict(size=6, color="lightblue"),
        ),
        row=1, col=1, secondary_y=False,
    )
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=smoothed_acc,
            name="Accuracy (EMA)",
            mode="lines",
            line=dict(color="blue"),
        ),
        row=1, col=1, secondary_y=False,
    )
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=[d["cps"] for d in daily],
            name="CPS (daily avg)",
            mode="markers",
            marker=dict(size=6, color="lightyellow"),
        ),
        row=1, col=1, secondary_y=True,
    )
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=smoothed_cps,
            name="CPS (EMA)",
            mode="lines",
            line=dict(color="orange"),
        ),
        row=1, col=1, secondary_y=True,
    )
    
    # Arrhythmicity
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=[d["arrhythmicity"] for d in daily],
            name="Arrhythmicity (daily avg)",
            mode="markers",
            marker=dict(size=6, color="lightcoral"),
        ),
        row=2, col=1,
    )
    daily_stats.add_trace(
        go.Scatter(
            x=[d["date"].isoformat() for d in daily],
            y=smoothed_arr,
            name="Arrhythmicity (EMA)",
            mode="lines",
            line=dict(color="red"),
        ),
        row=2, col=1,
    )
    daily_stats.update_layout(
        title="Daily Statistics",
        hovermode="x unified",
        height=600,
    )
    daily_stats.update_yaxes(title_text="Accuracy (%)", row=1, secondary_y=False)
    daily_stats.update_yaxes(title_text="CPS", row=1, secondary_y=True)
    daily_stats.update_yaxes(title_text="Arrhythmicity (s)", row=2, secondary_y=False)
    daily_stats.update_xaxes(title_text="Date", row=2)

    return render_template_string(
        HTML_TEMPLATE,
        current_cps=current_cps,
        current_accuracy=current_accuracy,
        total_lessons=total_lessons,
        bigram_json=bigram_fig.to_json(),
        accuracy_speed_json=accuracy_speed.to_json(),
        daily_stats_json=daily_stats.to_json(),
    )


if __name__ == "__main__":
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1:5000"]
    app.run(debug=True, port=5000, host="127.0.0.1")
