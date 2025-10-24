import os, uuid, subprocess, threading, time, signal, logging, json
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from pathlib import Path
from db import get_db
from utils.yaml_tools import ensure_yaml
from utils.file_tools import new_file, ensure_run_structure, to_relative_path, ensure_workspace_path
from utils.env_tools import find_environment_executable


# Global dictionaries for process management
RUN_PROCS: Dict[str, subprocess.Popen] = {}
RUN_STATUS: Dict[str, str] = {}  # Track process status
RUN_THREADS: Dict[str, threading.Thread] = {}  # Track monitoring threads

# Port management for ML-Agents environments
PORT_BASE = 5000  # Starting port for ML-Agents environments
PORT_SPACING = 10  # Minimum spacing between port ranges to avoid conflicts
RUN_PORTS: Dict[str, tuple[int, int]] = {}  # Maps run_id to (base_port, num_envs)
import threading as port_threading
PORT_LOCK = port_threading.Lock()  # Lock for thread-safe port allocation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RunnerError(Exception):
	"""Custom exception for runner operations"""
	pass

class ProcessError(RunnerError):
	"""Exception for process-related errors"""
	pass

class ValidationError(RunnerError):
	"""Exception for validation errors"""
	pass


def _allocate_ports(run_id: str, num_envs: int) -> int:
	"""
	Allocate a port range for a run.

	Args:
		run_id: Run identifier
		num_envs: Number of environments (determines port range size)

	Returns:
		base_port: Starting port for this run

	Raises:
		RunnerError: If unable to allocate ports
	"""
	with PORT_LOCK:
		# Find all currently allocated port ranges
		allocated_ranges = []
		for other_run_id, (base, envs) in RUN_PORTS.items():
			if other_run_id != run_id:
				# Each run uses ports [base, base + envs - 1], add spacing
				allocated_ranges.append((base, base + envs + PORT_SPACING - 1))

		# Sort ranges by start port
		allocated_ranges.sort()

		# Find first available port range
		candidate_port = PORT_BASE
		for start, end in allocated_ranges:
			if candidate_port + num_envs + PORT_SPACING <= start:
				# Found a gap before this range
				break
			# Try after this range
			candidate_port = end + 1

		# Allocate the port range
		RUN_PORTS[run_id] = (candidate_port, num_envs)
		logger.info(f"Allocated ports {candidate_port}-{candidate_port + num_envs - 1} for run {run_id} ({num_envs} envs)")

		return candidate_port


def _deallocate_ports(run_id: str) -> None:
	"""
	Deallocate ports for a completed run.

	Args:
		run_id: Run identifier
	"""
	with PORT_LOCK:
		if run_id in RUN_PORTS:
			base_port, num_envs = RUN_PORTS.pop(run_id)
			logger.info(f"Deallocated ports {base_port}-{base_port + num_envs - 1} for run {run_id}")


WORKSPACE = os.getenv("WORKSPACE", "/workspace")
# TB_DIR removed - results now stored in individual run directories

def _get_run_directory(run_id: str) -> str:
	"""Get the run directory path by looking up run metadata from database"""
	try:
		db = get_db()
		run_doc = db.runs.find_one({"_id": run_id})
		if not run_doc:
			# Fallback for legacy runs or runs not in database
			return f"{WORKSPACE}/runs/{run_id}"
		
		experiment_id = run_doc.get("experiment_id")
		revision_id = run_doc.get("revision_id")
		
		if experiment_id and revision_id:
			return ensure_run_structure(experiment_id, revision_id, run_id)
		else:
			# Fallback for runs without proper metadata
			return f"{WORKSPACE}/runs/{run_id}"
	except Exception:
		# Fallback on any error
		return f"{WORKSPACE}/runs/{run_id}"

def _resolve_environment_path(env_path: str, executable_file: str = None) -> str:
	"""
	Resolve environment path to executable.
	Handles both old single-file paths and new directory-based paths with separate executable files.
	"""
	try:
		if not env_path:
			raise ValidationError("Environment path is required")
		
		# Check if path exists
		if not os.path.exists(env_path):
			raise ValidationError(f"Environment path does not exist: {env_path}")
		
		# If it's a file and executable, return as is (legacy support)
		if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
			logger.info(f"Using environment file: {env_path}")
			return env_path
		
		# If it's a directory, construct path from env_path + executable_file
		if os.path.isdir(env_path):
			if executable_file:
				# Construct full executable path
				full_executable_path = os.path.join(env_path, executable_file)
				if os.path.exists(full_executable_path) and os.access(full_executable_path, os.X_OK):
					logger.info(f"Using environment executable: {full_executable_path}")
					return full_executable_path
				else:
					logger.warning(f"Executable file not found or not executable: {full_executable_path}")
			
			# Fall back to trying to find executable (legacy compatibility)
			executable_relative = find_environment_executable(env_path)
			if executable_relative:
				full_executable_path = os.path.join(env_path, executable_relative)
				if os.path.exists(full_executable_path) and os.access(full_executable_path, os.X_OK):
					logger.info(f"Found environment executable: {full_executable_path}")
					return full_executable_path
			
			# Fall back to directory path (some ML-Agents setups work with directories)
			logger.warning(f"No executable found in {env_path}, using directory path")
			return env_path
		
		# If we get here, path exists but is neither executable file nor directory
		logger.warning(f"Environment path is not executable or directory: {env_path}")
		return env_path
		
	except ValidationError:
		raise
	except Exception as e:
		logger.error(f"Error resolving environment path: {e}")
		raise ValidationError(f"Error resolving environment path: {e}")




def _validate_run_params(experiment: dict, revision: dict, yaml_text: str) -> str:
	"""
	Validate run parameters before launching.

	Args:
		experiment: Experiment document
		revision: Revision document
		yaml_text: YAML configuration content

	Returns:
		Resolved environment executable path

	Raises:
		ValidationError: If validation fails
	"""
	if not experiment:
		raise ValidationError("Experiment data is required")

	if not yaml_text or not yaml_text.strip():
		raise ValidationError("YAML configuration is required")

	# Validate critical experiment fields
	if "_id" not in experiment:
		raise ValidationError("Experiment must have an _id")

	# Validate revision
	if not revision:
		raise ValidationError("Revision data is required")

	if "_id" not in revision:
		raise ValidationError("Revision must have an _id")

	# Get environment path from revision's environment_id
	environment_id = revision.get("environment_id")
	if not environment_id:
		raise ValidationError(f"Revision {revision['_id']} has no environment_id")

	# Fetch environment to get env_path and executable_file
	try:
		db = get_db()
		environment = db.environments.find_one({"_id": environment_id})
		if not environment:
			raise ValidationError(f"Environment {environment_id} not found")

		env_path = environment.get("env_path")
		executable_file = environment.get("executable_file")

		if not env_path:
			raise ValidationError(f"Environment {environment_id} has no env_path")

	except Exception as e:
		logger.error(f"Error fetching environment path: {e}")
		raise ValidationError(f"Error fetching environment path: {e}")

	# Use the resolver to validate and get proper executable path
	try:
		resolved_path = _resolve_environment_path(env_path, executable_file)
		return resolved_path
	except ValidationError as e:
		logger.error(f"Environment validation failed: {e}")
		raise

def check_process_health(run_id: str) -> dict:
	"""
	Check if a process appears to be stuck or unhealthy.
	Returns health status information.
	"""
	try:
		proc = RUN_PROCS.get(run_id)
		if not proc:
			return {
				"healthy": False,
				"reason": "Process not found in active runs",
				"stuck": False
			}

		# Check if process is still running
		if proc.poll() is not None:
			return {
				"healthy": False,
				"reason": f"Process exited with code {proc.returncode}",
				"stuck": False
			}

		# Check log file activity
		try:
			run_dir = _get_run_directory(run_id)
			stdout_log = f"{run_dir}/stdout.log"

			if not os.path.exists(stdout_log):
				return {
					"healthy": True,
					"reason": "Log file not yet created (early startup)",
					"stuck": False
				}

			# Check when log was last modified
			log_mtime = os.path.getmtime(stdout_log)
			current_time = time.time()
			seconds_since_update = current_time - log_mtime

			# Get run start time from database
			db = get_db()
			run_doc = db.runs.find_one({"_id": run_id})
			if not run_doc:
				return {
					"healthy": False,
					"reason": "Run not found in database",
					"stuck": False
				}

			started_at = run_doc.get("started_at")
			if started_at:
				# Ensure timezone-aware comparison (MongoDB returns naive UTC datetimes)
				if started_at.tzinfo is None:
					started_at = started_at.replace(tzinfo=timezone.utc)
				runtime_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
			else:
				runtime_seconds = 0

			# Consider stuck if:
			# - Process has been running > 2 minutes (past startup)
			# - No log activity for > 2 minutes
			is_stuck = runtime_seconds > 120 and seconds_since_update > 120

			return {
				"healthy": not is_stuck,
				"reason": f"No log activity for {int(seconds_since_update)} seconds" if is_stuck else "Process appears healthy",
				"stuck": is_stuck,
				"pid": proc.pid,
				"runtime_seconds": int(runtime_seconds),
				"seconds_since_log_update": int(seconds_since_update),
				"log_size_bytes": os.path.getsize(stdout_log)
			}

		except Exception as e:
			logger.error(f"Error checking process health for {run_id}: {e}")
			return {
				"healthy": False,
				"reason": f"Error checking health: {str(e)}",
				"stuck": False
			}

	except Exception as e:
		logger.error(f"Unexpected error in check_process_health for {run_id}: {e}")
		return {
			"healthy": False,
			"reason": f"Unexpected error: {str(e)}",
			"stuck": False
		}

def get_stale_runs() -> List[dict]:
	"""
	Get list of all active runs that appear to be stuck/stale.
	"""
	stale_runs = []
	for run_id in list(RUN_PROCS.keys()):
		health = check_process_health(run_id)
		if health.get("stuck"):
			stale_runs.append({
				"run_id": run_id,
				"health": health
			})
	return stale_runs

def force_kill_run(run_id: str) -> bool:
	"""
	Force kill a run immediately without graceful shutdown.
	Use this for stuck processes that won't respond to normal stop.
	"""
	try:
		proc = RUN_PROCS.get(run_id)
		if not proc:
			logger.warning(f"Cannot force kill {run_id}: process not found")
			return False

		logger.warning(f"Force killing run {run_id} (PID: {proc.pid})")

		# Force kill entire process group
		try:
			if os.name != 'nt':
				pgid = os.getpgid(proc.pid)
				os.killpg(pgid, signal.SIGKILL)
				logger.info(f"Sent SIGKILL to process group {pgid}")
			else:
				proc.kill()
				logger.info(f"Sent kill signal to process {proc.pid}")
		except (OSError, ProcessLookupError) as e:
			logger.warning(f"Process {run_id} may already be dead: {e}")

		# Update database
		try:
			db = get_db()
			db.runs.update_one(
				{"_id": run_id},
				{"$set": {
					"status": "killed",
					"ended_at": datetime.now(timezone.utc)
				}}
			)
			logger.info(f"Updated database for force-killed run {run_id}")
		except Exception as db_error:
			logger.error(f"Failed to update database for {run_id}: {db_error}")

		# Cleanup
		RUN_PROCS.pop(run_id, None)
		RUN_STATUS.pop(run_id, None)
		RUN_THREADS.pop(run_id, None)
		_deallocate_ports(run_id)

		return True

	except Exception as e:
		logger.error(f"Error force killing run {run_id}: {e}")
		return False

def _monitor_process_health(run_id: str, proc: subprocess.Popen) -> None:
	"""Monitor process health and update status with improved error handling"""
	try:
		# Initial status
		RUN_STATUS[run_id] = "starting"
		logger.info(f"Starting health monitoring for process {run_id} (PID: {proc.pid})")

		# Monitor with more frequent checks initially
		startup_checks = 0
		max_startup_checks = 12  # 1 minute of startup monitoring

		while proc.poll() is None:
			# More frequent checks during startup
			if startup_checks < max_startup_checks:
				time.sleep(5)  # Check every 5 seconds during startup
				startup_checks += 1
				# Check again after sleep before updating status
				if proc.poll() is None:
					RUN_STATUS[run_id] = "starting"
			else:
				time.sleep(10)  # Check every 10 seconds during steady state
				# Check again after sleep before updating status
				if proc.poll() is None:
					RUN_STATUS[run_id] = "running"

			# Verify process is still accessible
			try:
				proc.poll()  # This will update returncode if process died
			except Exception as e:
				logger.warning(f"Error polling process {run_id}: {e}")
				break
				
		# Process has finished or died
		return_code = proc.returncode

		# Check if this was a user-initiated stop before setting final status
		db = get_db()
		current_db_status = None
		try:
			run_doc = db.runs.find_one({"_id": run_id})
			if run_doc:
				current_db_status = run_doc.get("status")
		except Exception as e:
			logger.warning(f"Error checking DB status for {run_id}: {e}")

		# If DB already shows "stopped", preserve that status (user-initiated)
		if current_db_status == "stopped":
			status = "stopped"
			logger.info(f"Process {run_id} preserving user-initiated stopped status")
		else:
			# Determine final status based on return code and timing
			if return_code is None:
				status = "error"  # Process died unexpectedly
				logger.error(f"Process {run_id} died without return code")
			elif return_code == 0:
				status = "succeeded"
				logger.info(f"Process {run_id} completed successfully")
			elif return_code < 0:
				status = "killed"  # Process was killed by signal
				logger.warning(f"Process {run_id} was killed by signal {-return_code}")
			else:
				status = "failed"  # Process failed with error code
				logger.error(f"Process {run_id} failed with return code {return_code}")

		RUN_STATUS[run_id] = status
		logger.info(f"Process {run_id} monitoring completed with status: {status}")

		# Immediately update database with failure status to avoid showing stale "starting"/"running" status
		if status in ["failed", "error", "killed"]:
			try:
				db.runs.update_one(
					{"_id": run_id},
					{"$set": {"status": status, "ended_at": datetime.now(timezone.utc), "return_code": return_code}}
				)
				logger.info(f"Immediately updated database for failed run {run_id} with status: {status}")
			except Exception as db_error:
				logger.error(f"Failed to immediately update database for {run_id}: {db_error}")
		
	except Exception as e:
		logger.error(f"Critical error monitoring process {run_id}: {e}")
		RUN_STATUS[run_id] = "error"
	finally:
		# Ensure cleanup happens even if monitoring fails
		logger.debug(f"Health monitoring cleanup for {run_id}")

def get_run_logs(run_id: str, max_lines: int = 20000) -> List[str]:  # High limit to show comprehensive run logs
	"""Get recent log lines for a specific run"""
	try:
		run_dir = _get_run_directory(run_id)
		stdout_log = f"{run_dir}/stdout.log"
		from utils.file_tools import LogStreamer
		streamer = LogStreamer(stdout_log)
		return streamer.tail_lines(max_lines)
	except Exception as e:
		logger.error(f"Error reading logs for run {run_id}: {e}")
		return []

def stream_run_logs(run_id: str, follow: bool = True) -> Optional[Any]:
	"""Generator function to stream log lines as they are written"""
	if run_id not in RUN_PROCS:
		return None
	
	run_dir = _get_run_directory(run_id)
	stdout_log = f"{run_dir}/stdout.log"
	
	try:
		with open(stdout_log, 'r', encoding='utf-8') as f:
			# Seek to end of file if following
			if follow:
				f.seek(0, 2)
			
			while True:
				line = f.readline()
				if line:
					yield line.rstrip()
				else:
					if not follow or run_id not in RUN_PROCS:
						break
					time.sleep(0.1)  # Brief pause before checking again
	except Exception as e:
		logger.error(f"Error streaming logs for run {run_id}: {e}")
		return None

def get_run_metrics(run_id: str) -> dict:
	"""Get basic metrics for a run"""
	try:
		proc = RUN_PROCS.get(run_id)
		if not proc:
			return {}
		
		# Basic process info
		metrics = {
			"pid": proc.pid,
			"status": RUN_STATUS.get(run_id, "unknown"),
			"return_code": proc.returncode
		}
		
		# Try to get process statistics (if psutil is available)
		try:
			import psutil
			process = psutil.Process(proc.pid)
			metrics.update({
				"cpu_percent": process.cpu_percent(),
				"memory_mb": process.memory_info().rss / 1024 / 1024,
				"create_time": process.create_time()
			})
		except ImportError:
			logger.debug("psutil not available for process metrics")
		except psutil.NoSuchProcess:
			logger.debug(f"Process {proc.pid} no longer exists")
		except Exception as e:
			logger.debug(f"Error getting process metrics: {e}")
		
		return metrics
	except Exception as e:
		logger.error(f"Error getting metrics for run {run_id}: {e}")
		return {}


def create_run(
	experiment: dict,
	revision: dict,
	yaml_text: str,
	cli_flags: dict,
	description: str = "",
	results_text: str = "",
	parent_run_id: Optional[str] = None,
	parent_revision_id: Optional[str] = None
) -> str:
	"""
	Create a new ML-Agents run without executing it (immutable).

	Args:
		experiment: Experiment document
		revision: Revision document
		yaml_text: YAML configuration content
		cli_flags: CLI flags for mlagents-learn (time_scale, no_graphics, num_envs, etc.)
		description: Run description
		results_text: Run results notes
		parent_run_id: Optional parent run ID
		parent_revision_id: Optional parent revision ID

	Returns:
		Created run ID

	Raises:
		RunnerError: If run creation fails
		ValidationError: If validation fails
	"""
	try:
		# Validate input parameters and get resolved environment path
		resolved_env_path = _validate_run_params(experiment, revision, yaml_text)

		db = get_db()
		run_id = str(uuid.uuid4())
		logger.info(f"Creating new run {run_id} for experiment {experiment.get('_id')}")

		try:
			# Get experiment and revision IDs
			experiment_id = experiment.get('_id')
			revision_id = revision.get('_id')

			if not experiment_id or not revision_id:
				raise RunnerError("experiment_id and revision_id are required for run creation")

			# Get names for directory structure
			experiment_name = experiment.get('name', 'unknown')
			revision_name = revision.get('name', 'unknown')

			# Create run directory structure using the new path format with names
			run_dir = ensure_run_structure(experiment_id, revision_id, run_id, experiment_name, revision_name)
			logger.info(f"Created run directory: {run_dir}")

			# Validate and write YAML configuration
			yaml_text = ensure_yaml(yaml_text)
			yaml_path = f"{run_dir}/config.yaml"
			new_file(run_dir, "config.yaml", yaml_text)

			# Setup log directories and results directory
			# ML-Agents creates {results_dir}/{run_name}/ so we will pass run_dir as results_dir
			# and use "results" as run_name to get content in run_dir/results/
			tb_logdir = f"{run_dir}/results"  # This is where content will actually end up
			stdout_log = f"{run_dir}/stdout.log"
			# Note: results directory will be created by mlagents-learn when invoked with --run-id=results
			# Do not pre-create the directory here

		except Exception as e:
			logger.error(f"Failed to setup run directories for {run_id}: {e}")
			raise RunnerError(f"Failed to setup run directories: {e}") from e

		try:
			# Create run document (status: "created", not executed yet)
			run_doc = {
				"_id": run_id,
				"revision_id": str(revision_id),
				"experiment_id": str(experiment_id),
				"parent_revision_id": parent_revision_id or "",
				"parent_run_id": parent_run_id or "",
				"status": "created",  # Not executed yet
				"yaml_path": to_relative_path(yaml_path),
				"yaml_snapshot": yaml_text,  # Immutable snapshot
				"cli_flags": cli_flags,
				"cli_flags_snapshot": cli_flags.copy(),  # Immutable snapshot
				"resolved_env_path": resolved_env_path,  # Store resolved path separately
				"tb_logdir": to_relative_path(tb_logdir),
				"stdout_log_path": to_relative_path(stdout_log),
				"artifacts_dir": to_relative_path(run_dir),
				"description": description,
				"results_text": results_text,
				"created_at": datetime.now(timezone.utc),
				"started_at": None,  # Will be set when executed
				"ended_at": None,
				"execution_count": 0,  # New field
				"last_restarted_at": None,  # New field
				"metrics_snapshot": {},
				"process_id": None,  # Will be set when executed
				"command": ""  # Will be set when executed
			}
			db.runs.insert_one(run_doc)
			logger.info(f"Run document created in database for {run_id}")

		except Exception as e:
			logger.error(f"Failed to create run document for {run_id}: {e}")
			raise RunnerError(f"Failed to create run document: {e}") from e

		return run_id

	except Exception as e:
		logger.error(f"Unexpected error in create_run: {e}")
		raise

def execute_run(run_id: str, restart_mode: str = None) -> bool:
	"""Execute an existing run using its immutable configuration

	Args:
		run_id: ID of the run to execute
		restart_mode: Optional restart mode - 'resume' or 'force'
	"""
	try:
		db = get_db()

		# Get run from database
		run_doc = db.runs.find_one({"_id": run_id})
		if not run_doc:
			raise RunnerError(f"Run {run_id} not found")

		# Check if run is already executing
		if run_id in RUN_PROCS:
			raise RunnerError(f"Run {run_id} is already executing")

		logger.info(f"Executing run {run_id}")

		# Get immutable configuration from run document
		yaml_text = run_doc.get("yaml_snapshot")
		cli_flags = run_doc.get("cli_flags_snapshot", {})
		experiment_id = run_doc.get("experiment_id")
		resolved_env_path = run_doc.get("resolved_env_path")

		if not yaml_text or not experiment_id:
			raise RunnerError(f"Run {run_id} missing required configuration")

		if not resolved_env_path:
			raise RunnerError(f"Run {run_id} missing resolved environment path")

		# Get experiment data
		experiment = db.experiments.find_one({"_id": experiment_id})
		if not experiment:
			raise RunnerError(f"Experiment {experiment_id} not found")

		try:
			# Get paths from run document
			run_dir = ensure_workspace_path(run_doc.get("artifacts_dir", ""))
			yaml_path = ensure_workspace_path(run_doc.get("yaml_path", ""))
			stdout_log = ensure_workspace_path(run_doc.get("stdout_log_path", ""))

			# Setup results directory for ML-Agents
			results_base_dir = run_dir  # ML-Agents will create run_dir/{run_name}/

			# Clear/recreate stdout log for fresh execution
			with open(stdout_log, "w", encoding="utf-8"):
				pass  # Create empty file
			
			# Build mlagents-learn command using resolved environment path
			# Use "results" as run_name so ML-Agents creates content in results/ directory
			run_name = "results"
			time_scale = str(cli_flags.get("time_scale", 20))
			no_graphics = cli_flags.get("no_graphics", True)
			num_envs = int(cli_flags.get("num_envs", 1))  # Default to 1 environment

			# Extract additional CLI flags
			seed = int(cli_flags.get("seed", -1))
			torch_device = cli_flags.get("torch_device", "auto")
			width = int(cli_flags.get("width", 84))
			height = int(cli_flags.get("height", 84))
			quality_level = int(cli_flags.get("quality_level", 5))

			# Allocate ports for this run
			base_port = _allocate_ports(run_id, num_envs)

			cmd = [
				"mlagents-learn", yaml_path,
				f"--run-id={run_name}",
				f"--env={resolved_env_path}",
				f"--time-scale={time_scale}",
				f"--base-port={base_port}",
				f"--num-envs={num_envs}",
			]
			if no_graphics:
				cmd.append("--no-graphics")

			# Add results directory for ML-Agents output
			if results_base_dir:
				cmd.append(f"--results-dir={results_base_dir}")

			# Add additional CLI flags
			if seed != -1:
				cmd.append(f"--seed={seed}")

			# Map 'auto' to default behavior (don't specify flag)
			if torch_device and torch_device.lower() != "auto":
				cmd.append(f"--torch-device={torch_device}")

			cmd.append(f"--width={width}")
			cmd.append(f"--height={height}")
			cmd.append(f"--quality-level={quality_level}")

			# Add restart mode flags if specified
			if restart_mode == 'resume':
				cmd.append("--resume")
				logger.info(f"Adding --resume flag for run {run_id}")
			elif restart_mode == 'force':
				cmd.append("--force")
				logger.info(f"Adding --force flag for run {run_id}")

			logger.info(f"Constructed command: {' '.join(cmd)}")
			
		except Exception as e:
			logger.error(f"Failed to construct command for {run_id}: {e}")
			raise RunnerError(f"Failed to construct command: {e}") from e
		
		try:
			# Setup environment variables
			env = os.environ.copy()
			env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")

			# Write command header to log file first
			with open(stdout_log, "w", encoding="utf-8") as out:
				out.write(f"=== ML-Agents Training Run ===\n")
				out.write(f"Run ID: {run_id}\n")
				out.write(f"Command: {' '.join(cmd)}\n")
				out.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
				out.write(f"{'=' * 50}\n\n")
			
			# Launch subprocess with proper error handling (append mode to preserve header)
			with open(stdout_log, "a", buffering=1) as out:
				proc = subprocess.Popen(
					cmd,
					stdout=out,
					stderr=subprocess.STDOUT,
					env=env,
					cwd='.',
					preexec_fn=os.setsid if os.name != 'nt' else None
				)
			
			# Store process reference and initial status
			RUN_PROCS[run_id] = proc
			RUN_STATUS[run_id] = "starting"
			logger.info(f"Process started for run {run_id} with PID {proc.pid}")
			
		except Exception as e:
			logger.error(f"Failed to start process for {run_id}: {e}")
			# Cleanup on failure
			RUN_PROCS.pop(run_id, None)
			RUN_STATUS.pop(run_id, None)
			_deallocate_ports(run_id)  # Release allocated ports on failure
			raise ProcessError(f"Failed to start process: {e}") from e
		
		try:
			# Update run document with execution info
			execution_count = run_doc.get("execution_count", 0) + 1
			now = datetime.now(timezone.utc)
			
			update_data = {
				"status": "running",
				"started_at": now if execution_count == 1 else run_doc.get("started_at"),  # Keep first start time
				"last_restarted_at": now if execution_count > 1 else None,
				"ended_at": None,
				"execution_count": execution_count,
				"process_id": proc.pid,
				"command": ' '.join(cmd)
			}
			
			db.runs.update_one({"_id": run_id}, {"$set": update_data})
			logger.info(f"Run document updated for execution {run_id}")
			
		except Exception as e:
			logger.error(f"Failed to update run document for {run_id}: {e}")
			# Cleanup on database failure
			if run_id in RUN_PROCS:
				RUN_PROCS[run_id].terminate()
				RUN_PROCS.pop(run_id, None)
			RUN_STATUS.pop(run_id, None)
			_deallocate_ports(run_id)  # Release allocated ports on database failure
			raise RunnerError(f"Failed to update run document: {e}") from e
		
		# Start monitoring thread (same as before)
		def process_waiter():
			final_status = "error"
			return_code = None

			try:
				_monitor_process_health(run_id, proc)
				# Get return code - process should already be finished from monitoring
				return_code = proc.returncode
				if return_code is None:
					# Process still running somehow, wait briefly
					try:
						return_code = proc.wait(timeout=5)
					except subprocess.TimeoutExpired:
						logger.warning(f"Process {run_id} still running after monitoring completed")
						return_code = None

				final_status = RUN_STATUS.get(run_id, "unknown")

				if final_status == "unknown":
					final_status = "succeeded" if return_code == 0 else "failed"

				logger.info(f"Run {run_id} process waiter completed with status: {final_status}, return_code: {return_code}")

			except Exception as e:
				logger.error(f"Error in process waiter for {run_id}: {e}")
				final_status = "error"
			finally:
				# Capture end time when process actually finishes
				ended_at = datetime.now(timezone.utc)

				try:
					current_run_doc = db.runs.find_one({"_id": run_id})
					current_db_status = current_run_doc.get("status") if current_run_doc else None

					if current_db_status == "stopped":
						final_status = "stopped"
						logger.info(f"Preserving user-initiated stopped status for run {run_id}")

					update_data = {
						"status": final_status,
						"ended_at": ended_at
					}
					if return_code is not None:
						update_data["return_code"] = return_code

					db.runs.update_one({"_id": run_id}, {"$set": update_data})
					logger.info(f"Updated database for run {run_id} with final status: {final_status}")
				except Exception as db_error:
					logger.error(f"Failed to update database for run {run_id}: {db_error}")

				try:
					RUN_PROCS.pop(run_id, None)
					RUN_STATUS.pop(run_id, None)
					RUN_THREADS.pop(run_id, None)
					_deallocate_ports(run_id)  # Release allocated ports
					logger.debug(f"Cleaned up process references for run {run_id}")
				except Exception as cleanup_error:
					logger.error(f"Error cleaning up process references for {run_id}: {cleanup_error}")
		
		thread = threading.Thread(target=process_waiter, daemon=True)
		thread.start()
		RUN_THREADS[run_id] = thread
		
		return True
		
	except Exception as e:
		logger.error(f"Unexpected error in execute_run: {e}")
		raise

def restart_run(run_id: str, mode: str = None) -> bool:
	"""Restart an existing run, cleaning execution artifacts but preserving immutable config

	Args:
		run_id: ID of the run to restart
		mode: Optional restart mode - 'resume' or 'force'
	"""
	try:
		db = get_db()

		# Get run from database
		run_doc = db.runs.find_one({"_id": run_id})
		if not run_doc:
			raise RunnerError(f"Run {run_id} not found")

		# Stop run if it's currently executing
		if run_id in RUN_PROCS:
			logger.info(f"Stopping currently running process for restart {run_id}")
			stop_run(run_id)
			# Wait a moment for cleanup
			import time
			time.sleep(1)

		logger.info(f"Restarting run {run_id} with mode={mode}")

		# Clean execution artifacts (skip if resuming)
		if mode != 'resume':
			try:
				stdout_log_path = ensure_workspace_path(run_doc.get("stdout_log_path", ""))
				tb_logdir = ensure_workspace_path(run_doc.get("tb_logdir", ""))

				# Clear stdout log
				if os.path.exists(stdout_log_path):
					with open(stdout_log_path, "w", encoding="utf-8"):
						pass  # Create empty file

				# Optionally clear results directory for fresh metrics
				if os.path.exists(tb_logdir):
					import shutil
					shutil.rmtree(tb_logdir)
					os.makedirs(tb_logdir, exist_ok=True)

				logger.info(f"Cleaned execution artifacts for run {run_id}")

			except Exception as e:
				logger.warning(f"Error cleaning artifacts for run {run_id}: {e}")
				# Continue with restart even if cleanup fails
		else:
			logger.info(f"Skipping artifact cleanup for resume mode")

		# Execute the run with existing immutable configuration
		success = execute_run(run_id, restart_mode=mode)

		if success:
			logger.info(f"Successfully restarted run {run_id}")

		return success

	except Exception as e:
		logger.error(f"Unexpected error in restart_run: {e}")
		raise

def launch_run(
	experiment: dict,
	revision: dict,
	yaml_text: str,
	cli_flags: dict,
	description: str = "",
	results_text: str = "",
	parent_run_id: Optional[str] = None,
	parent_revision_id: Optional[str] = None
) -> str:
	"""
	Launch a new ML-Agents training run (create and execute).

	Args:
		experiment: Experiment document
		revision: Revision document
		yaml_text: YAML configuration content
		cli_flags: CLI flags for mlagents-learn
		description: Run description
		results_text: Run results notes
		parent_run_id: Optional parent run ID
		parent_revision_id: Optional parent revision ID

	Returns:
		Created run ID

	Raises:
		RunnerError: If run creation or execution fails
	"""
	try:
		# Create the run first
		run_id = create_run(
			experiment=experiment,
			revision=revision,
			yaml_text=yaml_text,
			cli_flags=cli_flags,
			description=description,
			results_text=results_text,
			parent_run_id=parent_run_id,
			parent_revision_id=parent_revision_id
		)

		# Then execute it
		execute_run(run_id)

		return run_id

	except Exception as e:
		logger.error(f"Unexpected error in launch_run: {e}")
		raise


def stop_run(run_id: str) -> bool:
	"""Stop a running process gracefully with enhanced error handling and cleanup"""
	try:
		proc = RUN_PROCS.get(run_id)
		if not proc:
			logger.warning(f"No active process found for run {run_id}")
			# Check if it appears to be running according to centralized status
			try:
				current_status = get_effective_run_status(run_id)
				if current_status in ["running", "pending"]:
					# This is an orphaned run - update database to reflect that process is no longer active
					db = get_db()
					db.runs.update_one(
						{"_id": run_id}, 
						{"$set": {"status": "stopped", "ended_at": datetime.now(timezone.utc)}}
					)
					logger.info(f"Updated orphaned run {run_id} status to stopped")
					return True
			except Exception as db_e:
				logger.error(f"Error checking status for run {run_id}: {db_e}")
			return False
		
		logger.info(f"Stopping run {run_id} (PID: {proc.pid})")
		
		# Verify process is still alive before attempting to stop it
		try:
			if proc.poll() is not None:
				logger.info(f"Process {run_id} already terminated with code {proc.returncode}")
				# Process already dead, just cleanup
				RUN_PROCS.pop(run_id, None)
				RUN_STATUS.pop(run_id, None)
				return True
		except Exception as e:
			logger.warning(f"Error checking process status for {run_id}: {e}")
		
		# Attempt graceful termination
		termination_successful = False
		try:
			if os.name != 'nt':
				# Unix-like systems: Kill entire process group
				try:
					pgid = os.getpgid(proc.pid)
					logger.info(f"Terminating process group {pgid} for run {run_id}")
					os.killpg(pgid, signal.SIGTERM)  # Send SIGTERM to entire process group
					logger.debug(f"Sent SIGTERM to process group {pgid}")
				except (OSError, ProcessLookupError) as e:
					logger.warning(f"Could not get process group for {run_id}: {e}, falling back to process termination")
					proc.terminate()
			else:
				# Windows: Fall back to process termination
				proc.terminate()
				logger.debug(f"Sent SIGTERM to process {run_id}")
			
			# Wait for graceful shutdown with timeout
			try:
				proc.wait(timeout=30)  # Wait up to 30 seconds
				logger.info(f"Process {run_id} terminated gracefully")
				termination_successful = True
			except subprocess.TimeoutExpired:
				# Force kill if it doesn't respond to SIGTERM
				logger.warning(f"Process {run_id} did not respond to SIGTERM, sending SIGKILL")
				try:
					if os.name != 'nt':
						# Unix-like: Force kill entire process group
						try:
							pgid = os.getpgid(proc.pid)
							logger.info(f"Force killing process group {pgid} for run {run_id}")
							os.killpg(pgid, signal.SIGKILL)  # Send SIGKILL to entire process group
						except (OSError, ProcessLookupError):
							proc.kill()  # Fallback to process kill
					else:
						proc.kill()  # Windows: Force kill process
					
					proc.wait(timeout=10)  # Wait for force kill to complete
					logger.info(f"Process {run_id} force killed")
					termination_successful = True
				except Exception as kill_e:
					logger.error(f"Error force killing process {run_id}: {kill_e}")
					termination_successful = False
		except Exception as term_e:
			logger.error(f"Error terminating process {run_id}: {term_e}")
			termination_successful = False
		
		# Update database regardless of termination success
		try:
			db = get_db()
			update_data = {
				"status": "stopped" if termination_successful else "error",
				"ended_at": datetime.now(timezone.utc)
			}
			db.runs.update_one({"_id": run_id}, {"$set": update_data})
			logger.info(f"Updated database for run {run_id} with status: {update_data['status']}")
		except Exception as db_e:
			logger.error(f"Failed to update database for stopped run {run_id}: {db_e}")
		
		# Always attempt cleanup of process references
		try:
			RUN_PROCS.pop(run_id, None)
			RUN_STATUS.pop(run_id, None)

			# Handle monitoring thread cleanup
			thread = RUN_THREADS.pop(run_id, None)
			if thread and thread.is_alive():
				logger.debug(f"Monitoring thread for {run_id} will cleanup automatically")

			_deallocate_ports(run_id)  # Release allocated ports
			logger.debug(f"Cleaned up process references for run {run_id}")
		except Exception as cleanup_e:
			logger.error(f"Error during cleanup for run {run_id}: {cleanup_e}")
		
		return termination_successful
		
	except Exception as e:
		logger.error(f"Unexpected error stopping run {run_id}: {e}")
		# Attempt emergency cleanup
		try:
			RUN_PROCS.pop(run_id, None)
			RUN_STATUS.pop(run_id, None)
			RUN_THREADS.pop(run_id, None)
			_deallocate_ports(run_id)  # Release allocated ports in emergency cleanup
		except:
			pass  # Ignore cleanup errors in emergency case
		return False

def get_run_status(run_id: str) -> Optional[str]:
	"""Get current status of a run"""
	return RUN_STATUS.get(run_id)

def get_active_runs() -> List[str]:
	"""Get list of currently active run IDs"""
	return list(RUN_PROCS.keys())

def get_effective_run_status(run_id: str) -> str:
	"""
	Get the true current status of a run - single source of truth.

	Args:
		run_id: ID of the run

	Returns:
		Status string: "created", "running", "succeeded", "failed", "stopped", "unknown"
	"""
	# Check if run is in active processes (overrides DB status)
	if run_id in RUN_PROCS:
		return RUN_STATUS.get(run_id, "running")

	# Check DB for run status (includes created, completed, etc.)
	try:
		db = get_db()
		run_doc = db.runs.find_one({"_id": run_id})
		if run_doc:
			# Return actual DB status (created, succeeded, failed, stopped, etc.)
			return run_doc.get("status", "unknown")
	except Exception as e:
		logger.warning(f"Error checking DB status for run {run_id}: {e}")

	# Run doesn't exist in DB or error occurred
	return "unknown"

def cleanup_all_runs() -> None:
	"""Cleanup all running processes - used for graceful shutdown"""
	logger.info("Cleaning up all running processes...")
	for run_id in list(RUN_PROCS.keys()):
		stop_run(run_id)
	logger.info("All processes cleaned up")

def _setup_signal_handlers() -> None:
	"""Setup signal handlers for graceful shutdown"""
	def signal_handler(signum, _):
		logger.info(f"Received signal {signum}, cleaning up processes...")
		cleanup_all_runs()
		exit(0)
	
	if os.name != 'nt':  # Unix-like systems
		signal.signal(signal.SIGTERM, signal_handler)
		signal.signal(signal.SIGINT, signal_handler)

# Setup signal handlers when module is imported
_setup_signal_handlers()