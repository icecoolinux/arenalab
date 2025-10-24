import os
import shutil
import time
import re
from pathlib import Path
from typing import Generator, List, Callable, Optional

# Workspace paths configuration
WORKSPACE_ROOT = os.getenv("WORKSPACE", "/workspace")

class Paths:
    def __init__(self):
        self.WORKSPACE_ROOT = WORKSPACE_ROOT
        self.EXPERIMENTS_DIR = os.path.join(WORKSPACE_ROOT, "experiments")
        self.CONFIG_DIR = os.path.join(WORKSPACE_ROOT, "config")

# Global paths object
paths = Paths()

def to_relative_path(absolute_path: str) -> str:
    """
    Convert absolute workspace path to relative path from workspace root.
    
    Args:
        absolute_path (str): Absolute path that may include workspace root
        
    Returns:
        str: Relative path from workspace root (without leading slash)
        
    Examples:
        "/workspace/experiments/44/config.yaml" -> "experiments/44/config.yaml"
    """
    if not absolute_path:
        return ""
    
    # Normalize the path
    absolute_path = os.path.normpath(absolute_path)
    workspace_root = os.path.normpath(WORKSPACE_ROOT)
    
    # If path starts with workspace root, remove it
    if absolute_path.startswith(workspace_root):
        relative_path = absolute_path[len(workspace_root):]
        # Remove leading slash if present
        return relative_path.lstrip('/')
    
    # If path doesn't contain workspace root, assume it's already relative
    return absolute_path.lstrip('/')

def has_workspace_prefix(path: str) -> bool:
    """
    Check if a path already starts with the workspace root.
    
    Args:
        path (str): Path to check
        
    Returns:
        bool: True if path starts with workspace root, False otherwise
    """
    if not path:
        return False
    
    # Normalize paths for comparison
    normalized_path = os.path.normpath(path)
    normalized_workspace = os.path.normpath(WORKSPACE_ROOT)
    
    return normalized_path.startswith(normalized_workspace)

def ensure_workspace_path(path: str) -> str:
    """
    Ensure a path has the workspace root prefix.
    
    Args:
        path (str): Path that may or may not have workspace prefix
        
    Returns:
        str: Path with workspace root prefix
        
    Examples:
        "experiments/44/config.yaml" -> "/workspace/experiments/44/config.yaml"
        "/other/path" -> "/workspace/other/path"
    """
    if not path:
        return WORKSPACE_ROOT
    
    # If path already has workspace prefix, return as-is
    if has_workspace_prefix(path):
        return path
    
    # Remove leading slash if present to ensure proper joining
    path = path.lstrip('/')
    return os.path.join(WORKSPACE_ROOT, path)

def ensure_relative_path(path: str) -> str:
    """
    Ensure a path is relative to workspace root.
    
    Args:
        path (str): Path that may be absolute or relative
        
    Returns:
        str: Relative path from workspace root
    """
    return to_relative_path(path)

def sanitize_name(name: str) -> str:
    """
    Sanitize a name for use in directory paths.
    
    Converts to lowercase, replaces spaces with hyphens, and removes special characters
    except hyphens and underscores.
    
    Args:
        name (str): The name to sanitize
        
    Returns:
        str: Sanitized name suitable for directory paths
        
    Examples:
        "My Experiment" -> "my-experiment"
        "Test_123!" -> "test_123"
        "Deep Q-Learning" -> "deep-q-learning"
    """
    if not name:
        return "unnamed"
    
    # Convert to lowercase
    sanitized = name.lower()
    
    # Replace spaces with hyphens
    sanitized = re.sub(r'\s+', '-', sanitized)
    
    # Remove all characters except alphanumeric (including unicode), hyphens, and underscores
    sanitized = re.sub(r'[^\w\-]', '', sanitized)
    
    # Remove consecutive hyphens (but preserve underscores)
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens/underscores
    sanitized = sanitized.strip('-_')
    
    # Ensure we have something left
    if not sanitized:
        return "unnamed"
    
    # Limit length to avoid filesystem issues
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
        # Remove trailing hyphens/underscores after truncation
        sanitized = sanitized.rstrip('-_')
    
    return sanitized

def _get_experiment_name(experiment_id: str) -> str:
    """
    Get experiment name by ID. 
    
    Args:
        experiment_id (str): The experiment ID
        
    Returns:
        str: The experiment name, or "unknown" if not found
    """
    try:
        # Import here to avoid circular imports
        from db import experiments
        exp = experiments.find_one({"_id": experiment_id})
        return exp.get("name", "unknown") if exp else "unknown"
    except Exception:
        return "unknown"

def _get_revision_name(revision_id: str) -> str:
    """
    Get revision name by ID.
    
    Args:
        revision_id (str): The revision ID
        
    Returns:
        str: The revision name, or "unknown" if not found
    """
    try:
        # Import here to avoid circular imports
        from db import revisions
        rev = revisions.find_one({"_id": revision_id})
        return rev.get("name", "unknown") if rev else "unknown"
    except Exception:
        return "unknown"

def new_file(directory, filename, content):
    """
    Create a new file with the given content in the specified directory.
    
    Args:
        directory (str): Directory path where the file should be created (can be relative or absolute)
        filename (str): Name of the file to create
        content (str): Content to write to the file
        
    Returns:
        str: Absolute path to the created file
        
    Raises:
        OSError: If there's an error creating directories or writing the file
    """
    try:
        # Ensure directory has workspace prefix
        abs_directory = ensure_workspace_path(directory)
        # Ensure directory exists
        os.makedirs(abs_directory, exist_ok=True)
        
        # Full file path
        file_path = os.path.join(abs_directory, filename)
        # Write content to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return file_path
    except OSError as e:
        raise OSError(f"Failed to create file {os.path.join(abs_directory, filename)}: {e}") from e

def read_file(file_path):
    """
    Read the content of a file.
    
    Args:
        file_path (str): Path to the file to read (can be relative or absolute)
        
    Returns:
        str: Content of the file
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If there's an error reading the file
    """
    # Ensure file path has workspace prefix
    abs_file_path = ensure_workspace_path(file_path)
    
    if not os.path.exists(abs_file_path):
        raise FileNotFoundError(f"File not found: {abs_file_path}")
    
    with open(abs_file_path, "r", encoding="utf-8") as f:
        return f.read()

def delete_file(file_path):
    """
    Delete a single file.
    
    Args:
        file_path (str): Path to the file to delete
        
    Returns:
        bool: True if file was deleted, False if file didn't exist
    """
    if not file_path or not os.path.exists(file_path):
        return False
    
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
            return True
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
            return True
    except OSError as e:
        print(f"Error deleting {file_path}: {e}")
        return False
    
    return False

def delete_files(file_paths):
    """
    Delete multiple files or directories.
    
    Args:
        file_paths (list): List of file/directory paths to delete
        
    Returns:
        dict: Summary of deletion results
    """
    if not file_paths:
        return {"deleted": 0, "errors": 0, "skipped": 0}
    
    results = {"deleted": 0, "errors": 0, "skipped": 0}
    
    for file_path in file_paths:
        if not file_path:  # Skip None or empty paths
            results["skipped"] += 1
            continue
            
        if delete_file(file_path):
            results["deleted"] += 1
        else:
            results["errors"] += 1
    
    return results

def ensure_experiment_structure(experiment_id, experiment_name=None):
    """
    Create the directory structure for an experiment.
    
    Args:
        experiment_id (str): ID of the experiment
        experiment_name (str, optional): Name of the experiment. If not provided, will lookup from database.
        
    Returns:
        str: Path to the experiment directory
    """
    if experiment_name is None:
        experiment_name = _get_experiment_name(experiment_id)
    
    sanitized_name = sanitize_name(experiment_name)
    exp_dir_name = f"{sanitized_name}_{experiment_id}"
    exp_dir = os.path.join(paths.EXPERIMENTS_DIR, exp_dir_name)
    os.makedirs(exp_dir, exist_ok=True)
    return exp_dir

def ensure_revision_structure(experiment_id, revision_id, experiment_name=None, revision_name=None):
    """
    Create the directory structure for a revision.
    
    Args:
        experiment_id (str): ID of the experiment
        revision_id (str): ID of the revision
        experiment_name (str, optional): Name of the experiment. If not provided, will lookup from database.
        revision_name (str, optional): Name of the revision. If not provided, will lookup from database.
        
    Returns:
        str: Path to the revision directory
    """
    if experiment_name is None:
        experiment_name = _get_experiment_name(experiment_id)
    if revision_name is None:
        revision_name = _get_revision_name(revision_id)
    
    sanitized_exp_name = sanitize_name(experiment_name)
    sanitized_rev_name = sanitize_name(revision_name)
    exp_dir_name = f"{sanitized_exp_name}_{experiment_id}"
    rev_dir_name = f"{sanitized_rev_name}_{revision_id}"
    
    rev_dir = os.path.join(paths.EXPERIMENTS_DIR, exp_dir_name, "revisions", rev_dir_name)
    os.makedirs(rev_dir, exist_ok=True)
    return rev_dir

def ensure_run_structure(experiment_id, revision_id, run_id, experiment_name=None, revision_name=None):
    """
    Create the directory structure for a run.
    
    Args:
        experiment_id (str): ID of the experiment
        revision_id (str): ID of the revision
        run_id (str): ID of the run
        experiment_name (str, optional): Name of the experiment. If not provided, will lookup from database.
        revision_name (str, optional): Name of the revision. If not provided, will lookup from database.
        
    Returns:
        str: Path to the run directory
    """
    if experiment_name is None:
        experiment_name = _get_experiment_name(experiment_id)
    if revision_name is None:
        revision_name = _get_revision_name(revision_id)
    
    sanitized_exp_name = sanitize_name(experiment_name)
    sanitized_rev_name = sanitize_name(revision_name)
    exp_dir_name = f"{sanitized_exp_name}_{experiment_id}"
    rev_dir_name = f"{sanitized_rev_name}_{revision_id}"
    
    run_dir = os.path.join(paths.EXPERIMENTS_DIR, exp_dir_name, "revisions", rev_dir_name, "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir

def get_tensorboard_dir(experiment_id, revision_id, run_id, experiment_name=None, revision_name=None):
    """
    Get the TensorBoard/results log directory for a run following the new structure.
    
    Args:
        experiment_id (str): ID of the experiment
        revision_id (str): ID of the revision  
        run_id (str): ID of the run
        experiment_name (str, optional): Name of the experiment. If not provided, will lookup from database.
        revision_name (str, optional): Name of the revision. If not provided, will lookup from database.
        
    Returns:
        str: Path to the results directory within the run structure
    """
    if experiment_name is None:
        experiment_name = _get_experiment_name(experiment_id)
    if revision_name is None:
        revision_name = _get_revision_name(revision_id)
    
    sanitized_exp_name = sanitize_name(experiment_name)
    sanitized_rev_name = sanitize_name(revision_name)
    exp_dir_name = f"{sanitized_exp_name}_{experiment_id}"
    rev_dir_name = f"{sanitized_rev_name}_{revision_id}"
    
    results_dir = os.path.join(paths.EXPERIMENTS_DIR, exp_dir_name, "revisions", rev_dir_name, "runs", run_id, "results")
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def get_revision_path(experiment_id, revision_id, experiment_name=None, revision_name=None):
    """
    Get the Revision path according to the new structure.
    
    Args:
        experiment_id (str): ID of the experiment
        revision_id (str): ID of the revision
        experiment_name (str, optional): Name of the experiment. If not provided, will lookup from database.
        revision_name (str, optional): Name of the revision. If not provided, will lookup from database.
        
    Returns:
        str: Relative revision path from workspace root
    """
    if experiment_name is None:
        experiment_name = _get_experiment_name(experiment_id)
    if revision_name is None:
        revision_name = _get_revision_name(revision_id)
    
    sanitized_exp_name = sanitize_name(experiment_name)
    sanitized_rev_name = sanitize_name(revision_name)
    exp_dir_name = f"{sanitized_exp_name}_{experiment_id}"
    rev_dir_name = f"{sanitized_rev_name}_{revision_id}"
    
    return f"experiments/{exp_dir_name}/revisions/{rev_dir_name}"

class LogStreamer:
    """Unified log file streaming utility with tailing and status checking"""
    
    def __init__(self, log_path: str, status_checker: Optional[Callable[[], bool]] = None):
        """
        Initialize log streamer.
        
        Args:
            log_path (str): Path to the log file
            status_checker (callable, optional): Function that returns True if streaming should continue
        """
        self.log_path = log_path
        self.status_checker = status_checker
    
    def tail_lines(self, max_lines: int = 100) -> List[str]:
        """
        Read the last N lines from the log file.
        
        Args:
            max_lines (int): Maximum number of lines to return
            
        Returns:
            List[str]: Last lines from the file
        """
        try:
            if not os.path.exists(self.log_path):
                return []
            
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                return [line.rstrip() for line in lines[-max_lines:]]
        except Exception:
            return []
    
    def stream_generator(self, max_timeout: int = 60) -> Generator[str, None, None]:
        """
        Generator that yields log content as it's written.
        
        Args:
            max_timeout (int): Maximum timeout iterations before stopping
            
        Yields:
            str: Log content chunks
        """
        if not self.log_path or not os.path.exists(self.log_path):
            yield "Error: Log file not available\n"
            return
        
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                # Send existing content first
                content = f.read()
                if content:
                    yield content
                
                # Then tail for new content
                where = f.tell()
                timeout_count = 0
                
                while timeout_count < max_timeout:
                    f.seek(where)
                    line = f.readline()
                    if line:
                        yield line
                        where = f.tell()
                        timeout_count = 0  # Reset timeout
                    else:
                        time.sleep(1)
                        timeout_count += 1
                        
                        # Check if streaming should continue
                        if self.status_checker and not self.status_checker():
                            break
        except Exception as e:
            yield f"Error reading log file: {str(e)}\n"
    
    async def stream_websocket(self, websocket, wait_for_file: bool = True):
        """
        Stream log content to a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            wait_for_file (bool): Whether to wait for log file to exist
        """
        try:
            # Wait for log file to exist if requested
            if wait_for_file:
                while not os.path.exists(self.log_path):
                    await websocket.send_text("Waiting for logs...")
                    time.sleep(1)
            
            if not os.path.exists(self.log_path):
                await websocket.send_text("Error: Log file not available")
                return
            
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                # Send existing content
                content = f.read()
                if content:
                    await websocket.send_text(content)
                
                # Tail for new content
                where = f.tell()
                while True:
                    f.seek(where)
                    line = f.readline()
                    if line:
                        await websocket.send_text(line)
                        where = f.tell()
                    else:
                        time.sleep(0.5)
                        
                        # Check if streaming should continue
                        if self.status_checker and not self.status_checker():
                            await websocket.send_text("\n=== Run completed ===")
                            break
        except Exception as e:
            await websocket.send_text(f"Error: {str(e)}")