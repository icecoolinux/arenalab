"""
TensorBoard metrics fetching and processing for plugins.
"""

import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def get_metrics(
    db,
    run_id: str,
    metric_names: List[str] = None
) -> Dict[str, Any]:
    """
    Get training metrics from TensorBoard via its data API.

    Args:
        db: Database connection
        run_id: Run ID to fetch metrics for
        metric_names: List of specific metrics to fetch. If None, fetches all available

    Returns:
        Dictionary with metric data: {
            "scalars": {metric_name: [(step, value, wall_time), ...]},
            "latest": {metric_name: value},
            "summary": {metric_name: {"min": x, "max": y, "mean": z, "latest": w}}
        }
    """
    try:
        # Query TensorBoard data API directly (TensorBoard is already running and indexing experiments)
        from config import TENSORBOARD_HOST, TENSORBOARD_PATH_PREFIX

        # Build base URL with path prefix (if configured)
        tb_prefix = TENSORBOARD_PATH_PREFIX.rstrip('/')
        tb_base_url = f"{TENSORBOARD_HOST}{tb_prefix}/data"

        # Get available tags for this run
        tags_url = f"{tb_base_url}/plugin/scalars/tags"
        tags_response = requests.get(tags_url, timeout=5)

        if tags_response.status_code != 200:
            logger.debug(f"Run {run_id}: TensorBoard API returned {tags_response.status_code}")
            return {"scalars": {}, "latest": {}, "summary": {}}

        # TensorBoard returns data organized by run name
        tags_data = tags_response.json()

        # Find our run in the TensorBoard data (run_id might be nested in path)
        matching_runs = [run_name for run_name in tags_data.keys() if run_id in run_name]

        if not matching_runs:
            logger.debug(f"Run {run_id}: No data found in TensorBoard yet")
            return {"scalars": {}, "latest": {}, "summary": {}}

        # Use the first matching run
        tb_run_name = matching_runs[0]
        available_tags = list(tags_data[tb_run_name].keys())

        if not available_tags:
            logger.debug(f"Run {run_id}: No scalar tags available yet")
            return {"scalars": {}, "latest": {}, "summary": {}}

        # Filter by requested metrics if specified
        tags_to_fetch = metric_names if metric_names else available_tags

        scalars = {}
        latest = {}
        summary = {}

        # Fetch data for each tag
        for tag in tags_to_fetch:
            if tag not in available_tags:
                continue

            try:
                scalars_url = f"{tb_base_url}/plugin/scalars/scalars"
                params = {"run": tb_run_name, "tag": tag}
                scalar_response = requests.get(scalars_url, params=params, timeout=5)

                if scalar_response.status_code != 200:
                    continue

                data_points = scalar_response.json()
                if not data_points:
                    continue

                # Convert to our format: [(step, value, wall_time), ...]
                data = [(point[1], point[2], point[0]) for point in data_points]  # [wall_time, step, value]
                scalars[tag] = data

                # Get latest value
                latest[tag] = data[-1][1] if data else 0

                # Calculate summary statistics
                values = [point[1] for point in data]
                if values:
                    summary[tag] = {
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                        "latest": values[-1],
                        "count": len(values)
                    }

            except Exception as e:
                logger.warning(f"Error fetching tag {tag} for run {run_id}: {e}")
                continue

        # Filter out stale metrics from TensorBoard cache after run restart
        run_doc = db.runs.find_one({"_id": run_id})
        if run_doc and run_doc.get("last_cleanup_at"):
            last_cleanup_at = run_doc["last_cleanup_at"]
            # Convert to timestamp for comparison
            cleanup_timestamp = last_cleanup_at.timestamp() if hasattr(last_cleanup_at, 'timestamp') else last_cleanup_at

            # Filter scalars: keep only metrics newer than last cleanup
            filtered_scalars = {}
            for tag, data_points in scalars.items():
                # Filter data points: (step, value, wall_time)
                fresh_points = [(step, value, wall_time) for step, value, wall_time in data_points
                               if wall_time >= cleanup_timestamp]
                if fresh_points:
                    filtered_scalars[tag] = fresh_points

            # If no fresh metrics, return empty (prevents plugin confusion from stale cache)
            if not filtered_scalars:
                logger.debug(f"Run {run_id}: All metrics are stale (older than last_cleanup_at), returning empty")
                return {"scalars": {}, "latest": {}, "summary": {}}

            # Recalculate latest and summary from filtered data
            scalars = filtered_scalars
            latest = {}
            summary = {}
            for tag, data in scalars.items():
                latest[tag] = data[-1][1] if data else 0
                values = [point[1] for point in data]
                if values:
                    summary[tag] = {
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                        "latest": values[-1],
                        "count": len(values)
                    }

        return {
            "scalars": scalars,
            "latest": latest,
            "summary": summary
        }

    except requests.exceptions.RequestException as e:
        logger.warning(f"TensorBoard API not available: {e}")
        return {"scalars": {}, "latest": {}, "summary": {}}
    except Exception as e:
        logger.error(f"Error fetching metrics from TensorBoard: {e}")
        return {"error": str(e), "scalars": {}, "latest": {}, "summary": {}}
