import os
import zipfile
import tarfile
import bz2
import gzip
import shutil
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from fastapi import UploadFile

logger = logging.getLogger(__name__)

WORKSPACE = os.getenv("WORKSPACE", "/workspace")
ENVS_DIR = f"{WORKSPACE}/envs"

# Supported compression formats
SUPPORTED_FORMATS = {
    '.zip': 'zip',
    '.tar.gz': 'tar.gz', 
    '.tgz': 'tgz',
    '.tar.bz2': 'bz2',
    '.tar': 'tar'
}

class EnvExtractionError(Exception):
    """Exception raised when environment extraction fails"""
    pass

def ensure_envs_directory():
    """Ensure the environments directory exists"""
    os.makedirs(ENVS_DIR, exist_ok=True)

def get_file_format(filename: str) -> Optional[str]:
    """Determine the compression format from filename"""
    filename_lower = filename.lower()
    
    # Check multi-part extensions first
    if filename_lower.endswith('.tar.gz'):
        return 'tar.gz'
    elif filename_lower.endswith('.tar.bz2'):
        return 'bz2'
    
    # Check single extensions
    for ext, format_type in SUPPORTED_FORMATS.items():
        if filename_lower.endswith(ext):
            return format_type
    
    return None

def create_env_directory(version: int, env_id: str, name: str) -> str:
    """Create environment directory with naming pattern <version>_<id>_<name>"""
    ensure_envs_directory()
    dir_name = f"{version}_{env_id}_{name}"
    env_base_dir = os.path.join(ENVS_DIR, dir_name)
    env_extract_dir = os.path.join(env_base_dir, "env")
    
    os.makedirs(env_base_dir, exist_ok=True)
    os.makedirs(env_extract_dir, exist_ok=True)
    
    return env_base_dir

def save_compressed_file(upload_file: UploadFile, env_base_dir: str) -> str:
    """Save the uploaded compressed file to the environment directory"""
    compressed_file_path = os.path.join(env_base_dir, upload_file.filename)
    
    try:
        with open(compressed_file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        
        logger.info(f"Saved compressed file: {compressed_file_path}")
        return compressed_file_path
        
    except Exception as e:
        logger.error(f"Failed to save compressed file: {e}")
        raise EnvExtractionError(f"Failed to save compressed file: {e}")

def extract_compressed_file(compressed_file_path: str, extract_to_dir: str, file_format: str) -> None:
    """Extract compressed file to specified directory, handling single-folder archives"""
    try:
        logger.info(f"Extracting {file_format} file: {compressed_file_path} to {extract_to_dir}")
        
        # Create a temporary extraction directory
        temp_extract_dir = os.path.join(extract_to_dir, "_temp_extract")
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        # Extract to temporary directory first
        if file_format == 'zip':
            with zipfile.ZipFile(compressed_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
                
        elif file_format in ['tar.gz', 'tgz']:
            with tarfile.open(compressed_file_path, 'r:gz') as tar_ref:
                tar_ref.extractall(temp_extract_dir)
                
        elif file_format == 'bz2':
            with tarfile.open(compressed_file_path, 'r:bz2') as tar_ref:
                tar_ref.extractall(temp_extract_dir)
                
        elif file_format == 'tar':
            with tarfile.open(compressed_file_path, 'r') as tar_ref:
                tar_ref.extractall(temp_extract_dir)
        else:
            raise EnvExtractionError(f"Unsupported file format: {file_format}")
        
        # Check if extraction resulted in a single folder or multiple files/folders
        temp_contents = os.listdir(temp_extract_dir)
        
        if len(temp_contents) == 1 and os.path.isdir(os.path.join(temp_extract_dir, temp_contents[0])):
            # Single folder case - move contents of that folder to final destination
            single_folder_path = os.path.join(temp_extract_dir, temp_contents[0])
            logger.info(f"Found single container folder: {temp_contents[0]}, moving contents to {extract_to_dir}")
            
            # Move all contents from the single folder to the final destination
            for item in os.listdir(single_folder_path):
                src = os.path.join(single_folder_path, item)
                dst = os.path.join(extract_to_dir, item)
                shutil.move(src, dst)
        else:
            # Multiple files/folders case - move everything to final destination
            logger.info(f"Found {len(temp_contents)} items at root level, moving to {extract_to_dir}")
            
            # Move all contents to final destination
            for item in temp_contents:
                src = os.path.join(temp_extract_dir, item)
                dst = os.path.join(extract_to_dir, item)
                shutil.move(src, dst)
        
        # Clean up temporary directory
        shutil.rmtree(temp_extract_dir)
            
        logger.info(f"Successfully extracted {file_format} file")
        
    except Exception as e:
        logger.error(f"Failed to extract {file_format} file: {e}")
        # Clean up temp directory on failure
        try:
            if 'temp_extract_dir' in locals() and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
        except:
            pass
        raise EnvExtractionError(f"Failed to extract {file_format} file: {e}")

def find_environment_executable(env_dir: str) -> Optional[str]:
    """Find the main executable file within the extracted environment directory and return relative path"""
    try:
        # Common executable patterns for Unity ML-Agents environments
        executable_patterns = [
            "*.exe",           # Windows executables
            "*.x86_64",        # Linux executables  
            "*.x86",           # Linux 32-bit
            "*",               # Any executable file (last resort)
        ]
        
        env_path = Path(env_dir)
        print("A")
        print(env_path)
        # Look for executables in the root of env directory first
        for pattern in executable_patterns[:-1]:  # Exclude the catch-all pattern
            matches = list(env_path.glob(pattern))
            if matches:
                executable = matches[0]  # Take the first match
                if executable.is_file(): # and os.access(executable, os.X_OK):
                    # Set execution permissions
                    try:
                        os.chmod(str(executable), 0o755)
                        logger.info(f"Set execution permissions (755) for: {executable}")
                    except Exception as e:
                        logger.warning(f"Failed to set permissions for {executable}: {e}")
                    
                    # Return relative path from env_dir
                    relative_path = os.path.relpath(str(executable), env_dir)
                    logger.info(f"Found executable: {executable}, relative path: {relative_path}")
                    return relative_path
        
        # Look for executables in subdirectories
        for root, dirs, files in os.walk(env_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Check if file is executable and matches patterns
                if True: #os.access(file_path, os.X_OK):
                    # Prioritize files that look like Unity builds
                    if (file.endswith('.exe') or file.endswith('.x86_64') or 
                        file.endswith('.x86') or 'unity' in file.lower()):
                        # Set execution permissions
                        try:
                            os.chmod(file_path, 0o755)
                            logger.info(f"Set execution permissions (755) for: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to set permissions for {file_path}: {e}")
                        
                        # Return relative path from env_dir
                        relative_path = os.path.relpath(file_path, env_dir)
                        logger.info(f"Found executable in subdirectory: {file_path}, relative path: {relative_path}")
                        return relative_path
        
        # If no clear executable found, return None
        logger.warning(f"No clear executable found in {env_dir}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding executable in {env_dir}: {e}")
        return None

def process_environment_upload(upload_file: UploadFile, version: int, env_id: str, name: str) -> Tuple[str, str, str, str, str]:
    """
    Process uploaded environment file: save, extract, and find executable
    
    Returns:
        Tuple[env_path, executable_file, compressed_file_path, original_filename, file_format]
    """
    try:
        # Validate file format
        file_format = get_file_format(upload_file.filename)
        if not file_format:
            supported = ", ".join(SUPPORTED_FORMATS.keys())
            raise EnvExtractionError(f"Unsupported file format. Supported formats: {supported}")
        
        # Create directory structure
        env_base_dir = create_env_directory(version, env_id, name)
        env_extract_dir = os.path.join(env_base_dir, "env")
        
        # Reset file pointer to beginning
        upload_file.file.seek(0)
        
        # Save compressed file
        compressed_file_path = save_compressed_file(upload_file, env_base_dir)
        
        # Extract compressed file
        extract_compressed_file(compressed_file_path, env_extract_dir, file_format)
        
        # Find executable
        executable_file = find_environment_executable(env_extract_dir)
        
        logger.info(f"Successfully processed environment upload: {upload_file.filename}")
        
        return (
            env_extract_dir,                     # env_path (directory)
            executable_file,                     # executable_file (relative filename or None)
            compressed_file_path,                # compressed_file_path  
            upload_file.filename,                # original_filename
            file_format                          # file_format
        )
        
    except Exception as e:
        logger.error(f"Failed to process environment upload: {e}")
        # Cleanup on failure
        try:
            if 'env_base_dir' in locals() and os.path.exists(env_base_dir):
                shutil.rmtree(env_base_dir)
        except:
            pass
        raise

def cleanup_environment(env_id: str, version: int, name: str) -> bool:
    """Remove environment directory and all its contents"""
    try:
        dir_name = f"{version}_{env_id}_{name}"
        env_base_dir = os.path.join(ENVS_DIR, dir_name)
        
        if os.path.exists(env_base_dir):
            shutil.rmtree(env_base_dir)
            logger.info(f"Cleaned up environment directory: {env_base_dir}")
            return True
        else:
            logger.warning(f"Environment directory not found: {env_base_dir}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to cleanup environment directory: {e}")
        return False

def get_environment_info(env_path: str) -> dict:
    """Get information about an extracted environment"""
    try:
        info = {
            "exists": os.path.exists(env_path),
            "is_file": os.path.isfile(env_path),
            "is_directory": os.path.isdir(env_path),
            "is_executable": False,
            "size_mb": 0
        }
        
        if info["exists"]:
            if info["is_file"]:
                info["is_executable"] = os.access(env_path, os.X_OK)
                info["size_mb"] = round(os.path.getsize(env_path) / (1024 * 1024), 2)
            elif info["is_directory"]:
                # Calculate directory size
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(env_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except:
                            continue
                info["size_mb"] = round(total_size / (1024 * 1024), 2)
        
        return info
        
    except Exception as e:
        logger.error(f"Error getting environment info: {e}")
        return {"exists": False, "error": str(e)}