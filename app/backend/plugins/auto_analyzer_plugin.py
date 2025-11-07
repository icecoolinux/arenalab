"""
Auto Analyzer Plugin.

AI-powered run analysis and insights generation.
Monitors training progress and provides automated analysis.
"""

from datetime import datetime
from .core import register_plugin

# LLM Prompts
LLM_ANALYSIS_PROMPT = """Analyze this ML training run and provide insights on:
1. Training performance and trends
2. Potential issues or anomalies
3. Recommendations for improvement
Keep the analysis concise and actionable."""

LLM_STUCK_DETECTION_PROMPT = """Analyze the training metrics and determine if training is stuck or making no progress.

Consider:
1. Are key performance metrics (ELO/rewards) flatlined or oscillating without improvement?
2. Are losses converging or stuck at high values?
3. Is there any positive trend in the recent data?

Respond with a JSON object:
{
  "is_stuck": true/false,
  "reason": "Brief explanation of why training is/isn't stuck"
}

Be conservative - only mark as stuck if there's clear evidence of no progress."""

LLM_RECOMMENDATION_PROMPT = """Based on the training metrics provided, suggest specific hyperparameter adjustments that could improve performance.
Focus on: learning_rate, batch_size, network architecture, buffer_size, and other relevant ML-Agents hyperparameters.
Be specific with recommended values or ranges."""


@register_plugin(
    name="auto_analyzer",
    scope="run",
    description="AI-powered run analysis and insights generation",
    icon="🤖",
    settings_schema={
        "analysis_frequency": {
            "type": "int",
            "default": 5,
            "min": 1,
            "label": "Analysis Frequency (minutes)",
            "description": "How often to analyze training progress (in minutes)"
        },
        "enable_llm": {
            "type": "boolean",
            "default": False,
            "label": "AI-Powered Analysis",
            "description": "Use LLM (Claude/GPT-4) for advanced insights. Requires ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable."
        },
        "detect_stuck": {
            "type": "boolean",
            "default": False,
            "label": "Auto-Stop Stuck Training",
            "description": "Automatically stop training when no progress is detected. With AI-Powered Analysis enabled, uses LLM intelligence; otherwise uses variance-based detection."
        },
        "stuck_window_size": {
            "type": "int",
            "default": 20,
            "min": 5,
            "label": "Stuck Detection Window",
            "description": "Number of recent data points to check for stagnation. Larger values = more conservative detection."
        },
        "stuck_variance_threshold": {
            "type": "float",
            "default": 1e-6,
            "label": "Stuck Variance Threshold",
            "description": "Minimum variance required to consider training as progressing. Lower values = stricter detection (e.g., 1e-6 means nearly zero change)."
        },
        "generate_summary": {
            "type": "boolean",
            "default": True,
            "label": "Generate Final Summary",
            "description": "Create detailed summary with hyperparameter recommendations when training completes"
        }
    }
)
def auto_analyzer_plugin(context, api):
    """
    Auto-Analyzer Plugin - Real-time training analysis and insights.

    Features:
    - Periodic analysis during training
    - Non-LLM analysis: trend detection, convergence checks, performance metrics
    - Optional LLM-powered insights with custom prompts
    - Stuck detection with auto-stop capability
    - Final summary with hyperparameter recommendations
    """

    # Get settings
    frequency = context.settings.get("analysis_frequency", 5)  # minutes
    use_llm = context.settings.get("enable_llm", False)
    detect_stuck = context.settings.get("detect_stuck", False)
    stuck_window = context.settings.get("stuck_window_size", 20)
    stuck_threshold = context.settings.get("stuck_variance_threshold", 1e-6)
    generate_summary = context.settings.get("generate_summary", True)

    # Verify LLM availability if enabled
    if use_llm and not api.is_llm_available():
        api.add_note("⚠️ LLM analysis requested but no API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        use_llm = False

    # Get run info once at start
    run = api.get_run()
    if not run:
        api.add_note("❌ Run not found")
        return

    api.add_note(f"🤖 Auto-Analyzer started (frequency: {frequency}min, LLM: {use_llm}, stuck detection: {detect_stuck})")

    # Analysis loop
    while not context.should_stop:
        
        # Get current run status
        run = api.get_run()

        if not run:
            break

        status = run.get("status")

        # Check if run is still running
        if status == "running":
            # Perform analysis
            analysis_result = _analyze_training(api, run, use_llm)

            # Add analysis note
            if analysis_result:
                api.add_note(f"📊 {analysis_result}")

            # Check if training is stuck
            if detect_stuck:
                if use_llm:
                    # Use AI-powered stuck detection
                    stuck_check = _check_if_stuck_llm(api, run)
                else:
                    # Use variance-based stuck detection
                    stuck_check = _check_if_stuck(api, stuck_window, stuck_threshold)

                if stuck_check["is_stuck"]:
                    api.add_note(f"⚠️ Training appears stuck: {stuck_check['reason']}")
                    api.add_note("🛑 Stopping run due to stuck detection")
                    api.stop_run()
                    break

        elif status in ["completed", "failed", "stopped"]:
            # Run finished - generate final summary if enabled
            if generate_summary:
                summary = _generate_final_summary(api, run, use_llm)
                api.add_note(f"📋 Final Summary:\n{summary}")
            break

        # Wait before next analysis (automatically monitors current run for early exit)
        api.wait(minutes=frequency)

    api.add_note("🤖 Auto-Analyzer stopped")


def _analyze_training(api, run, use_llm):
    """Perform training analysis using metrics and optionally LLM."""

    # Get metrics from TensorBoard
    metrics = api.get_metrics()

    if "error" in metrics:
        return f"Unable to analyze: {metrics['error']}"

    # Timestamp for this analysis
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Define specific metrics to track
    TRACKED_METRICS = [
        "Environment/Group Cumulative Reward",
        "Environment/Cumulative Reward",
        "Losses/Policy Loss",
        "Environment/Episode Length",
        "Policy/Entropy",
        "Policy/Extrinsic Value Estimate",
        "Self-play/ELO",
    ]

    # Non-LLM analysis: Basic trend and convergence checks
    analysis_lines = [f"[{timestamp}] Training Analysis:"]

    # Check available metrics
    if "latest" in metrics and metrics["latest"]:
        latest = metrics["latest"]
        summary = metrics.get("summary", {})
        scalars = metrics.get("scalars", {})

        for metric_name in TRACKED_METRICS:
            if metric_name not in latest:
                continue

            current = latest[metric_name]
            stats = summary.get(metric_name, {})

            # Get historical data for trend detection
            history = scalars.get(metric_name, [])

            # Format the metric line
            if "Reward" in metric_name or "Return" in metric_name or "ELO" in metric_name:
                # Reward and ELO metrics (higher is better)
                max_val = stats.get("max", current)
                trend = _determine_reward_trend(current, history)
                analysis_lines.append(f"   {metric_name}: {current:.2f} ({trend}, max: {max_val:.2f})")

            elif "Loss" in metric_name or "Entropy" in metric_name:
                # Loss and entropy metrics
                trend = _determine_loss_trend(current, history, stats)
                analysis_lines.append(f"   {metric_name}: {current:.4f} ({trend})")

            elif "Episode Length" in metric_name:
                # Episode length
                analysis_lines.append(f"   {metric_name}: {current:.1f}")

            elif "Value Estimate" in metric_name:
                # Value estimates
                mean_val = stats.get("mean", current)
                analysis_lines.append(f"   {metric_name}: {current:.3f} (mean: {mean_val:.3f})")

    # If no metrics available yet
    if len(analysis_lines) == 1:
        analysis_lines.append("   Training in progress, waiting for metrics...")

    base_analysis = "\n".join(analysis_lines)

    # LLM analysis if enabled
    if use_llm:
        try:
            # Prepare context for LLM
            logs = api.get_run().get("stdout_log_path", "")
            recent_logs = []
            if logs:
                try:
                    with open(logs, 'r') as f:
                        recent_logs = f.readlines()[-50:]  # Last 50 lines
                except:
                    pass

            context_data = {
                "metrics": metrics.get("latest", {}),
                "summary_stats": metrics.get("summary", {}),
                "recent_logs": recent_logs,
                "run_status": run.get("status"),
                "base_analysis": base_analysis
            }

            llm_insight = api.llm(LLM_ANALYSIS_PROMPT, context_data)
            return f"{base_analysis}\n\n🧠 AI Insight: {llm_insight}"

        except Exception as e:
            return f"{base_analysis}\n\n⚠️ LLM analysis failed: {str(e)}"

    return base_analysis


def _determine_reward_trend(current_value, history):
    """Determine trend for reward metrics with emoji indicators."""
    if len(history) < 5:
        return "initializing..."

    # Get recent values (last 20% of data, min 5 points)
    recent_count = max(5, len(history) // 5)
    recent_values = [value for _, value, _ in history[-recent_count:]]

    # Calculate trend
    mean = sum(recent_values) / len(recent_values)

    # Compare current to recent mean
    if current_value > mean * 1.05:  # 5% improvement
        return "improving 📈"
    elif current_value < mean * 0.95:  # 5% decline
        return "declining 📉"
    else:
        return "stable ➡️"


def _determine_loss_trend(current_value, history, stats):
    """Determine trend for loss metrics."""
    if len(history) < 5:
        return "initializing..."

    min_val = stats.get("min", current_value)

    # Loss should decrease over time
    if current_value < min_val * 1.1:
        return "converging ✓"
    else:
        return "fluctuating"


def _check_if_stuck(api, window_size, variance_threshold):
    """Check if training is stuck (no progress) using variance-based detection."""

    metrics = api.get_metrics()

    if "scalars" not in metrics:
        return {"is_stuck": False, "reason": "No metrics available"}

    # Determine if self-play is enabled by checking for ELO metric
    has_elo = any("elo" in k.lower() for k in metrics["scalars"].keys())

    # Prioritize ELO for self-play, otherwise use reward metrics
    if has_elo:
        # Self-play mode - check ELO metric
        elo_metrics = [k for k in metrics["scalars"].keys() if "elo" in k.lower()]
        primary_metrics = elo_metrics
    else:
        # Regular mode - check reward metrics
        reward_metrics = [k for k in metrics["scalars"].keys() if "reward" in k.lower() or "return" in k.lower()]
        primary_metrics = reward_metrics

    for metric in primary_metrics:
        data = metrics["scalars"][metric]

        if len(data) < window_size:
            continue

        # Get recent values
        recent_values = [value for _, value, _ in data[-window_size:]]

        # Calculate variance
        mean = sum(recent_values) / len(recent_values)
        variance = sum((x - mean) ** 2 for x in recent_values) / len(recent_values)

        if variance < variance_threshold:
            return {
                "is_stuck": True,
                "reason": f"{metric} flatlined (variance: {variance:.2e} < {variance_threshold:.2e})"
            }

    return {"is_stuck": False, "reason": "Training progressing normally"}


def _check_if_stuck_llm(api, run):
    """Check if training is stuck using AI-powered analysis."""

    try:
        metrics = api.get_metrics()

        # Determine if self-play is enabled
        has_elo = any("elo" in k.lower() for k in metrics.get("scalars", {}).keys())
        primary_metric = "ELO" if has_elo else "reward"

        context_data = {
            "metrics": metrics.get("latest", {}),
            "summary_stats": metrics.get("summary", {}),
            "scalars": metrics.get("scalars", {}),
            "run_status": run.get("status"),
            "is_selfplay": has_elo,
            "primary_metric": primary_metric
        }

        llm_response = api.llm(LLM_STUCK_DETECTION_PROMPT, context_data)

        # Parse LLM response (expect JSON)
        import json
        try:
            result = json.loads(llm_response)
            return {
                "is_stuck": result.get("is_stuck", False),
                "reason": result.get("reason", "AI analysis completed")
            }
        except json.JSONDecodeError:
            # Fallback if LLM doesn't return valid JSON
            is_stuck = "stuck" in llm_response.lower() or "flatlined" in llm_response.lower()
            return {
                "is_stuck": is_stuck,
                "reason": llm_response[:200]  # Truncate long responses
            }

    except Exception as e:
        # If LLM fails, don't stop training
        return {"is_stuck": False, "reason": f"AI analysis failed: {str(e)}"}


def _generate_final_summary(api, run, use_llm):
    """Generate final summary with insights and hyperparameter recommendations."""

    metrics = api.get_metrics()

    summary_parts = []
    summary_parts.append(f"Status: {run.get('status', 'unknown')}")

    # Performance summary
    if "summary" in metrics and metrics["summary"]:
        summary_parts.append("\n📊 Performance Metrics:")

        for metric, stats in list(metrics["summary"].items())[:5]:  # Top 5 metrics
            summary_parts.append(
                f"  • {metric}: "
                f"final={stats['latest']:.4f}, "
                f"mean={stats['mean']:.4f}, "
                f"min={stats['min']:.4f}, "
                f"max={stats['max']:.4f}"
            )

    # LLM-powered recommendations
    if use_llm:
        try:
            context_data = {
                "final_metrics": metrics.get("summary", {}),
                "run_status": run.get("status"),
                "cli_flags": run.get("cli_flags", {})
            }

            recommendations = api.llm(LLM_RECOMMENDATION_PROMPT, context_data)
            summary_parts.append(f"\n💡 Hyperparameter Recommendations:\n{recommendations}")

        except Exception as e:
            summary_parts.append(f"\n⚠️ Could not generate recommendations: {str(e)}")
    else:
        # Basic non-LLM recommendations
        summary_parts.append("\n💡 Recommendations:")
        summary_parts.append("  • Enable LLM analysis for AI-powered hyperparameter recommendations")
        summary_parts.append("  • Review TensorBoard for detailed metric trends")

    return "\n".join(summary_parts)
