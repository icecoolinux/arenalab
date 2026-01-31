"""
Auto Analyzer Plugin.

AI-powered run analysis and insights generation.
Monitors training progress and provides automated analysis.
"""

import yaml
from .core import register_plugin

# LLM Prompts
LLM_FINAL_ANALYSIS_PROMPT = r"""
You are an expert Reinforcement Learning (RL) researcher analyzing a **completed Unity ML-Agents training run**.

You will receive **one JSON object** with (at least) the following fields:

- `metrics_history`: a dict mapping metric names (strings) to time series.
  - Each time series is a list of triplets: `[step, value, wall_clock_timestamp]`.
  - Example: `"Environment/Episode Length": [[10000, 876.875, 1763171301.10], ...]`.
  - Steps are training steps, sorted in ascending order.
- `final_metrics`: a dict with summary statistics for each metric over the run.
  - For each metric: `{ "min": ..., "max": ..., "mean": ..., "latest": ..., "count": ... }`.
  - `"latest"` corresponds to the last value in `metrics_history` for that metric.
- `latest_values`: a flat dict with the latest value of key metrics for convenience.
- `yaml_config`: the exact ML-Agents YAML used for this behavior, including:
  - `trainer_type`, `hyperparameters`, `network_settings`,
    `reward_signals`, `self_play`, and other relevant options.
- `cli_flags`: command-line flags used when launching `mlagents-learn`
  (e.g., `--no-graphics`, `--time-scale`, `--num-envs`, `--torch-device`).
- `run_status`: string describing how the run ended (e.g., `"completed"`, `"stopped"`, `"aborted"`).
- Optionally, there may also be:
  - `env_notes`: short free-text notes about the environment
    (sparse vs dense rewards, self-play, action/observation spaces, etc.).
  - `resource_profile`: info about wall-clock time, steps per second, GPU/CPU utilization.

---

### Metric semantics (interpretation guide)

Use the following **typical meaning** of metric families (when present):

- `Environment/*`:
  - `Environment/Cumulative Reward`: per-agent cumulative reward per episode.
  - `Environment/Group Cumulative Reward`: team- or group-level cumulative reward.
  - `Environment/Episode Length`: average number of steps per episode.
- `Self-play/ELO`:
  - Rating of agent skill in self-play; increasing ELO usually means stronger policy.
- `Policy/*`:
  - `Policy/Extrinsic Reward`: average extrinsic reward used by the trainer.
  - `Policy/Extrinsic Value Estimate` / `Baseline Estimate`: critic or baseline estimates.
  - `Policy/Entropy`: action distribution entropy (higher = more exploration;
    very low = potential exploration collapse).
  - `Policy/Learning Rate`, `Policy/Beta`, `Policy/Epsilon`, etc.: effective
    learning rate, entropy regularization, clipping epsilon, and related hyperparameters.
- `Losses/*`:
  - `Losses/Policy Loss`, `Losses/Value Loss`, `Losses/Baseline Loss`:
    optimization objectives for policy and value function.
  - Look for divergence (exploding losses) or overly small losses combined with no learning.

You should interpret trends **across all metrics together**, not in isolation.

---

### Your task

Given the JSON input, produce a **very concise written analysis** describing (in total **at most 120 words** before the JSON block):

1. **Overall training outcome**
   - How successful was learning? Did the policy clearly improve?
   - Is the final policy likely stable and usable, or still under-trained / unstable?
2. **Metric trends over time**
   - Describe how key metrics evolved: reward/ELO, episode length, policy/value losses,
     entropy, and any other informative signals.
   - Point out patterns: monotonic improvements, plateaus, oscillations, regressions,
     or recoveries after regressions.
3. **Issues or anomalies**
   - Mention signs of:
     - Instability or divergence.
     - Entropy collapse (over-exploitation).
     - Very long or very short episodes with poor reward.
     - Reward/ELO plateaus suggesting the agent hit a performance ceiling.
   - Explicitly state when the run appears **too short** or **data is too sparse**
     to draw strong conclusions.
4. **Efficiency and configuration**
   - Comment on whether the training duration and configuration (e.g. max_steps,
     time scale, num_envs, learning rate schedule) seem efficient for this problem.
   - If `run_status` is `"stopped"` or `"aborted"` before `max_steps`, mention
     whether the current metrics suggest it was prematurely stopped or reasonably stopped.
5. **Hyperparameter insights**
   - Based on the observed behavior, recommend **specific, high-impact** hyperparameter
     changes for the next run (e.g., `learning_rate`, `batch_size`, `buffer_size`,
     `beta`/entropy coefficient, `epsilon`, network size, `time_horizon`, etc.).
   - Refer to the **exact parameter names and values** in `yaml_config`.
   - Prefer **small, incremental** changes over drastic ones, unless the run clearly
     failed (e.g., no learning at all).
6. **Next steps**
   - Provide 3–6 concrete, actionable recommendations (hyperparameter changes, curriculum,
     reward shaping, training longer, modifying self-play settings, etc.) that would be
     reasonable to try in the next experiment.

---

### Reasoning guidelines

- Consider **the entire time series** of metrics, not only the last few points.
- If some metrics improve (e.g., ELO or reward) while others are noisy, acknowledge the
  mixed signals instead of declaring clear success or failure.
- Do **not** over-interpret tiny changes in metrics when `count` or the number of data
  points is very small.
- When evidence is weak (few points, short run, very noisy data), say so explicitly
  and be conservative in your conclusions.
- Always ground your suggestions in RL principles:
  - Higher entropy early in training, then gradual reduction.
  - Learning rate too high → instability, oscillations.
  - Learning rate too low → very slow improvement / plateau.
  - Too small batch/buffer → noisy gradients; too large → slow updates.
- It is acceptable to state uncertainty and propose multiple options (e.g. “either
  increase entropy or simplify the task first”), as long as you explain why.

---

### Output format

1. First, write your analysis in **at most 5 bullet points** (no paragraphs),
   with a **total of no more than 120 words**. Do not add titles, introductions,
   or conclusions; go straight to the key points.
2. Then, append **exactly one JSON block** with only the recommended hyperparameter changes,
   using this format:

{
  "recommended_hyperparameters": [
    {
      "param": "<name exactly as in YAML>",
      "current": "<value from yaml_config or 'unknown'>",
      "suggested": "<new value or small range>",
      "reason": "Brief justification based on the observed metrics and behavior."
    }
  ]
}

If you do not recommend any changes, output:

{ "recommended_hyperparameters": [] }

"""







@register_plugin(
    name="auto_analyzer",
    scope="run",
    description="AI-powered monitoring with final analysis and hyperparameter recommendations",
    icon="🤖",
    settings_schema={
        "generate_summary": {
            "type": "boolean",
            "default": True,
            "label": "Generate Final Summary",
            "description": "Create detailed summary with hyperparameter recommendations when training completes"
        },
        "enable_llm": {
            "type": "boolean",
            "default": True,
            "label": "AI-Powered Final Analysis",
            "description": "Use LLM (Claude/GPT-5) for comprehensive final summary and hyperparameter recommendations when training completes. Configure API keys in Settings page."
        },
        "detect_stuck": {
            "type": "boolean",
            "default": True,
            "label": "Auto-Stop Stuck Training",
            "description": "Automatically stop training when no progress is detected using step-based plateau detection (analyzes trends, improvement, and noise over training steps)."
        },
        "analysis_frequency": {
            "type": "int",
            "default": 5,
            "min": 1,
            "label": "Check Frequency (minutes)",
            "description": "How often to check for stuck training condition (in minutes)"
        },
        "window_steps": {
            "type": "int",
            "default": 100_000,
            "min": 10_000,
            "label": "Recent Window (steps)",
            "description": "Number of training steps in the recent window for trend analysis. Smaller values = more sensitive to recent changes."
        },
        "burn_in_steps": {
            "type": "int",
            "default": 500_000,
            "min": 50_000,
            "label": "Burn-in Period (steps)",
            "description": "Minimum training steps before stuck detection begins. Training won't be stopped before reaching this threshold."
        },
        "patience_steps": {
            "type": "int",
            "default": 1_000_000,
            "min": 100_000,
            "label": "Patience Window (steps)",
            "description": "Number of steps to check for improvement. If no improvement is seen in this window, training may be considered stuck."
        },
        "min_improvement": {
            "type": "float",
            "default": 0.01,
            "min": 0.001,
            "label": "Minimum Improvement (%)",
            "description": "Minimum relative improvement required (e.g., 0.01 = 1% improvement). Higher values = stricter detection."
        },
        "trend_threshold": {
            "type": "float",
            "default": 1e-3,
            "min": 1e-5,
            "label": "Trend Threshold",
            "description": "Threshold for detecting flat trends. Lower values = stricter flat detection (e.g., 1e-3 means nearly zero slope)."
        },
        "cv_threshold": {
            "type": "float",
            "default": 0.05,
            "min": 0.01,
            "label": "Noise Threshold (CV)",
            "description": "Coefficient of variation threshold for low noise detection. Higher values = stricter detection (allows more variance while still being considered stuck, e.g., 0.05 = 5% variation)."
        }
    }
)
def auto_analyzer_plugin(context, api):
    """
    Auto-Analyzer Plugin - Intelligent training monitoring with comprehensive final analysis.

    Features:
    - Periodic monitoring for stuck detection (every N minutes)
    - Step-based plateau detection with auto-stop (analyzes trends, improvement, and noise)
    - AI-powered comprehensive final analysis when training completes
    - Complete metrics history and hyperparameter recommendations at the end
    """

    # Get settings
    frequency = context.settings.get("analysis_frequency", 5)  # minutes
    use_llm = context.settings.get("enable_llm", False)
    detect_stuck = context.settings.get("detect_stuck", False)
    window_steps = context.settings.get("window_steps", 100_000)
    burn_in_steps = context.settings.get("burn_in_steps", 500_000)
    patience_steps = context.settings.get("patience_steps", 1_000_000)
    min_improvement = context.settings.get("min_improvement", 0.01)
    trend_threshold = context.settings.get("trend_threshold", 1e-3)
    cv_threshold = context.settings.get("cv_threshold", 0.05)
    generate_summary = context.settings.get("generate_summary", True)

    # Verify LLM availability if enabled
    if use_llm and not api.is_llm_available():
        api.log("⚠️ LLM analysis requested but no API key found. Configure API keys in Settings page.", level="WARNING")
        use_llm = False

    # Get run info once at start
    run = api.get_run()
    if not run:
        api.log("❌ Run not found", level="ERROR")
        api.add_note("❌ Run not found")
        return

    api.log(f"🤖 Auto-Analyzer started (frequency: {frequency}min, LLM: {use_llm}, stuck detection: {detect_stuck})", level="INFO")
    api.add_note(f"🤖 Auto-Analyzer started (frequency: {frequency}min, LLM: {use_llm}, stuck detection: {detect_stuck})")

    # Analysis loop
    while True:

        # Get current run status
        run = api.get_run()

        if not run:
            break

        status = run.get("status")

        # Check if run has finished - perform final analysis BEFORE checking plugin stop
        if status in ["completed", "failed", "stopped", "stopping"]:
            # Run finished - perform full analysis and generate final summary
            if generate_summary or use_llm:
                api.log("🔍 Generating final analysis...", level="INFO")
                api.add_note("🔍 Generating final analysis...")
                summary = _generate_final_summary(api, run, use_llm)
                api.add_note(f"📋 Final Analysis & Summary:\n{summary}")
            break

        # Check if plugin should stop (after final analysis check)
        if context.should_stop:
            api.log("⚠️ Plugin stopped before run completed", level="WARNING")
            api.add_note("⚠️ Plugin stopped before run completed")
            break

        # Check if run is still running
        if status == "running":
            # Only check if training is stuck during periodic checks
            if detect_stuck:
                api.log(f"🔍 Running stuck detection check...", level="DEBUG")
                # Use step-based stuck detection
                stuck_check = _check_if_stuck(
                    api,
                    window_steps=window_steps,
                    burn_in_steps=burn_in_steps,
                    patience_steps=patience_steps,
                    min_improvement=min_improvement,
                    trend_threshold=trend_threshold,
                    cv_threshold=cv_threshold
                )

                if stuck_check["is_stuck"]:
                    api.log(f"⚠️ Training appears stuck: {stuck_check['reason']}", level="WARNING",
                           metadata=stuck_check)
                    api.log("🛑 Stopping run due to stuck detection", level="WARNING")
                    api.add_note(f"⚠️ Training appears stuck: {stuck_check['reason']}")
                    api.add_note("🛑 Stopping run due to stuck detection")
                    api.stop_run()
                    # Don't break - let it loop again to detect "stopped" status and generate final analysis
                    continue
                else:
                    api.log(f"✅ Training progressing normally: {stuck_check['reason']}", level="DEBUG")

        # Wait before next analysis (automatically monitors current run for early exit)
        api.wait(minutes=frequency)

    api.log("🤖 Auto-Analyzer stopped", level="INFO")
    api.add_note("🤖 Auto-Analyzer stopped")


def _check_if_stuck(
    api,
    window_steps: int = 100_000,
    burn_in_steps: int = 500_000,
    patience_steps: int = 1_000_000,
    min_improvement: float = 0.01,
    trend_threshold: float = 1e-3,
    cv_threshold: float = 0.05,
):
    """
    Detect whether training is 'stuck' (plateaued) using:
    - A burn-in period in steps
    - Lack of new best values over a patience window in steps
    - Flat trend + low noise over a short recent window in steps

    Assumes each scalar metric entry is of the form: (step, value, wall_time).
    """

    api.log("🔍 [STUCK DETECTION] Starting stuck detection check...", level="DEBUG")
    api.log(f"   Parameters: window={window_steps}, burn_in={burn_in_steps}, patience={patience_steps}", level="DEBUG")
    api.log(f"   Thresholds: min_improvement={min_improvement}, trend={trend_threshold}, cv={cv_threshold}", level="DEBUG")

    metrics = api.get_metrics()

    if "scalars" not in metrics:
        api.log("   ℹ️  No scalar metrics available yet", level="DEBUG")
        return {"is_stuck": False, "reason": "No metrics available"}

    # Detect if we have ELO (self-play) or use reward/return
    has_elo = any("elo" in k.lower() for k in metrics["scalars"].keys())
    api.log(f"   📊 Metric type detected: {'ELO (self-play)' if has_elo else 'Reward/Return'}", level="DEBUG")

    if has_elo:
        primary_metrics = [k for k in metrics["scalars"].keys() if "elo" in k.lower()]
    else:
        primary_metrics = [
            k
            for k in metrics["scalars"].keys()
            if "reward" in k.lower() or "return" in k.lower()
        ]

    if not primary_metrics:
        api.log("   ⚠️  No primary metrics (ELO/reward) found", level="DEBUG")
        return {"is_stuck": False, "reason": "No primary metrics (ELO/reward) found"}

    api.log(f"   ✅ Found {len(primary_metrics)} primary metric(s): {primary_metrics}", level="DEBUG")

    def _analyze_metric(name: str):
        api.log(f"\n   🔬 Analyzing metric: {name}", level="DEBUG")
        data = metrics["scalars"][name]

        # Basic sanity check: need at least a few points
        if len(data) < 5:
            api.log(f"      ⏭️  Only {len(data)} data points - skipping", level="DEBUG")
            return {"is_stuck": False, "reason": f"{name}: not enough data points yet"}

        steps = [s for (s, _, _) in data]
        values = [v for (_, v, _) in data]

        current_step = steps[-1]
        api.log(f"      📍 Current step: {current_step:,} | Data points: {len(data)} | Latest value: {values[-1]:.4f}", level="DEBUG")

        # Burn-in: do not judge too early in training
        if current_step < burn_in_steps:
            api.log(f"      🌱 Still in burn-in period ({current_step:,} < {burn_in_steps:,})", level="DEBUG")
            return {
                "is_stuck": False,
                "reason": f"{name}: burn-in period (step={current_step} < {burn_in_steps})",
            }

        # Split history into past vs recent based on patience_steps
        patience_start_step = current_step - patience_steps

        past_indices = [i for i, s in enumerate(steps) if s < patience_start_step]
        recent_indices = [i for i, s in enumerate(steps) if s >= patience_start_step]

        if not past_indices or not recent_indices:
            # Not enough history to compare past vs recent
            api.log(f"      ⏳ Not enough history for patience window (need {patience_steps:,} steps)", level="DEBUG")
            return {
                "is_stuck": False,
                "reason": f"{name}: not enough history for patience window "
                          f"(patience_steps={patience_steps})",
            }

        past_values = [values[i] for i in past_indices]
        recent_values = [values[i] for i in recent_indices]

        past_best = max(past_values)
        recent_best = max(recent_values)

        denom = max(1.0, abs(past_best))
        improvement = (recent_best - past_best) / denom  # can be negative
        no_new_best = improvement < min_improvement

        api.log(f"      📈 Improvement analysis:", level="DEBUG")
        api.log(f"         Past best: {past_best:.4f} | Recent best: {recent_best:.4f}", level="DEBUG")
        api.log(f"         Relative improvement: {improvement:.4f} ({improvement*100:.2f}%)", level="DEBUG")
        api.log(f"         No new best? {no_new_best} (threshold: {min_improvement*100:.2f}%)", level="DEBUG")

        # Short recent window in steps for trend + variance
        window_start_step = current_step - window_steps
        window_indices = [i for i, s in enumerate(steps) if s >= window_start_step]

        # If very few points fall in the window, fallback to "recent" subset
        if len(window_indices) < 2:
            window_indices = recent_indices

        if len(window_indices) < 2:
            # Still too few points to estimate slope / variance
            api.log(f"      ⚠️  Not enough points in recent window", level="DEBUG")
            return {
                "is_stuck": False,
                "reason": f"{name}: not enough points in recent window",
            }

        window_values = [values[i] for i in window_indices]
        window_steps_list = [steps[i] for i in window_indices]

        m = len(window_values)
        mean_val = sum(window_values) / m
        var = sum((x - mean_val) ** 2 for x in window_values) / max(1, m - 1)
        std = var ** 0.5
        cv = std / (abs(mean_val) + 1e-8)

        # Linear regression slope over (normalized) steps in the window
        # Normalize time axis so numbers are numerically stable
        min_step_w = window_steps_list[0]
        max_step_w = window_steps_list[-1]
        step_range = max(1.0, max_step_w - min_step_w)

        xs = [(s - min_step_w) / step_range for s in window_steps_list]
        x_mean = sum(xs) / m
        y_mean = mean_val

        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, window_values))
        den_slope = sum((x - x_mean) ** 2 for x in xs) or 1.0
        slope = num / den_slope  # value change per normalized time unit

        # Normalize slope by global best value to get dimensionless measure
        global_best = max(values)
        rel_denom = max(1.0, abs(global_best))
        rel_slope = slope / rel_denom

        flat_trend = abs(rel_slope) < trend_threshold
        low_noise = cv < cv_threshold

        api.log(f"      📉 Trend & noise analysis (window: last {window_steps:,} steps, {len(window_values)} points):", level="DEBUG")
        api.log(f"         Mean: {mean_val:.4f} | Std: {std:.4f} | CV: {cv:.4f}", level="DEBUG")
        api.log(f"         Relative slope: {rel_slope:.6f} | Flat trend? {flat_trend} (threshold: {trend_threshold:.6f})", level="DEBUG")
        api.log(f"         Low noise? {low_noise} (CV < {cv_threshold:.4f})", level="DEBUG")

        if no_new_best and flat_trend and low_noise:
            api.log(f"      🛑 STUCK DETECTED: All conditions met (no improvement + flat trend + low noise)", level="DEBUG")
            return {
                "is_stuck": True,
                "reason": (
                    f"{name} plateau: no new best over last ~{patience_steps} steps "
                    f"(rel_improvement={improvement:.3g}), flat trend "
                    f"(rel_slope={rel_slope:.3g}), low noise (cv={cv:.3g})"
                ),
            }

        api.log(f"      ✅ NOT STUCK: Conditions not met", level="DEBUG")
        return {
            "is_stuck": False,
            "reason": (
                f"{name}: still improving or too noisy "
                f"(rel_improvement={improvement:.3g}, rel_slope={rel_slope:.3g}, cv={cv:.3g})"
            ),
        }

    # Combine multiple primary metrics:
    # - If at least one clearly not stuck -> overall not stuck (conservative).
    # - If all that have enough data look stuck -> stuck.
    stuck_reasons = []
    not_stuck_reasons = []

    for metric in primary_metrics:
        res = _analyze_metric(metric)
        if res["is_stuck"]:
            stuck_reasons.append(res["reason"])
        else:
            not_stuck_reasons.append(res["reason"])

    api.log(f"\n   🎯 [FINAL DECISION] Combining {len(primary_metrics)} metric(s):", level="DEBUG")
    api.log(f"      Stuck count: {len(stuck_reasons)}", level="DEBUG")
    api.log(f"      Not stuck count: {len(not_stuck_reasons)}", level="DEBUG")

    if stuck_reasons and not not_stuck_reasons:
        api.log(f"      ⛔ VERDICT: STUCK - All metrics show plateau", level="DEBUG")
        return {"is_stuck": True, "reason": "; ".join(stuck_reasons)}

    if not_stuck_reasons and not stuck_reasons:
        api.log(f"      ✅ VERDICT: NOT STUCK - All metrics progressing", level="DEBUG")
        return {"is_stuck": False, "reason": "; ".join(not_stuck_reasons)}

    # Mixed signals: prefer to not kill the run
    if stuck_reasons and not_stuck_reasons:
        api.log(f"      ⚖️  VERDICT: NOT STUCK - Mixed signals (conservative: keeping run alive)", level="DEBUG")
        return {
            "is_stuck": False,
            "reason": (
                "Mixed signals: some metrics look plateaued, others still changing. "
                f"Stuck: {stuck_reasons}; Not stuck: {not_stuck_reasons}"
            ),
        }

    api.log(f"      ✅ VERDICT: NOT STUCK - Training progressing normally", level="DEBUG")
    return {"is_stuck": False, "reason": "Training progressing normally"}


def _generate_final_summary(api, run, use_llm):
    """Generate final summary with insights and hyperparameter recommendations."""

    metrics = api.get_metrics()

    summary_parts = []
    summary_parts.append(f"Status: {run.get('status', 'unknown')}")

    # Performance summary - show ALL metrics
    if "summary" in metrics and metrics["summary"]:
        summary_parts.append("\n📊 Performance Metrics:")

        for metric, stats in metrics["summary"].items():  # ALL metrics
            summary_parts.append(
                f"  • {metric}: "
                f"final={stats['latest']:.4f}, "
                f"mean={stats['mean']:.4f}, "
                f"min={stats['min']:.4f}, "
                f"max={stats['max']:.4f}"
            )

    if use_llm:
        try:
            config = yaml.safe_load(run.get("yaml_snapshot", "")) or {}

            context_data = {
                "final_metrics": metrics.get("summary", {}),
                "metrics_history": metrics.get("scalars", {}),
                "latest_values": metrics.get("latest", {}),
                "run_status": run.get("status"),
                "yaml_config": config,
                "cli_flags": run.get("cli_flags", {}),
            }

            analysis = api.llm(LLM_FINAL_ANALYSIS_PROMPT, context_data)
            summary_parts.append(f"\n🧠 AI Analysis & Recommendations:\n{analysis}")

        except Exception as e:
            summary_parts.append(f"\n⚠️ AI analysis failed: {str(e)}")

    return "\n".join(summary_parts)
