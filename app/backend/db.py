import os
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from typing import Dict, Any, Optional, List
from datetime import datetime
from bson import ObjectId


_client = None
_db = None


def get_db():
	global _client, _db
	if _db is None:
		uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
		name = os.getenv("MONGO_DB", "mlagents_lab")
		_client = MongoClient(uri)
		_db = _client[name]
		
		# Create indexes
		_db.experiments.create_index([("name", ASCENDING)], unique=False)
		_db.runs.create_index([("experiment_id", ASCENDING)])
		_db.users.create_index([("email", ASCENDING)], unique=True)
		_db.revisions.create_index([("experiment_id", ASCENDING)])
		_db.environments.create_index([("name", ASCENDING)])
		
	return _db


class BaseCollection:
	"""Base class for MongoDB collection operations"""
	
	def __init__(self, collection_name: str):
		self.db = get_db()
		self.collection: Collection = self.db[collection_name]
	
	def find_one(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		return self.collection.find_one(filter_dict)
	
	def find_many(self, filter_dict: Dict[str, Any] = None, limit: int = None) -> List[Dict[str, Any]]:
		cursor = self.collection.find(filter_dict or {})
		if limit:
			cursor = cursor.limit(limit)
		return list(cursor)
	
	def insert_one(self, document: Dict[str, Any]) -> str:
		if "_id" not in document:
			document["_id"] = str(ObjectId())
		result = self.collection.insert_one(document)
		return str(result.inserted_id)
	
	def update_one(self, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> bool:
		result = self.collection.update_one(filter_dict, {"$set": update_dict})
		return result.modified_count > 0
	
	def delete_one(self, filter_dict: Dict[str, Any]) -> bool:
		result = self.collection.delete_one(filter_dict)
		return result.deleted_count > 0
	
	def count_documents(self, filter_dict: Dict[str, Any] = None) -> int:
		return self.collection.count_documents(filter_dict or {})


class UsersCollection(BaseCollection):
	"""Users collection operations"""
	
	def __init__(self):
		super().__init__("users")
	
	def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
		return self.find_one({"email": email})
	
	def create_user(self, email: str, name: str, password_hash: str, role: str = "user") -> str:
		user_doc = {
			"email": email,
			"name": name,
			"password_hash": password_hash,
			"role": role,
			"created_at": datetime.utcnow(),
			"last_login": None,
			"is_active": True
		}
		return self.insert_one(user_doc)
	
	def update_last_login(self, user_id: str) -> bool:
		return self.update_one(
			{"_id": user_id}, 
			{"last_login": datetime.utcnow()}
		)


class ExperimentsCollection(BaseCollection):
	"""Experiments collection operations"""
	
	def __init__(self):
		super().__init__("experiments")
	
	def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
		return self.find_one({"name": name})
	
	def create_experiment(self, name: str, description: str = "", tags: List[str] = None, enabled_plugins: List[dict] = None) -> str:
		exp_doc = {
			"name": name,
			"description": description,
			"tags": tags or [],
			"enabled_plugins": enabled_plugins or [],
			"created_at": datetime.utcnow(),
			"updated_at": datetime.utcnow(),
			"is_favorite": False
		}
		return self.insert_one(exp_doc)
	
	def toggle_favorite(self, experiment_id: str) -> bool:
		"""Toggle the favorite status of an experiment"""
		experiment = self.find_one({"_id": experiment_id})
		if not experiment:
			return False
		new_status = not experiment.get("is_favorite", False)
		return self.update_one({"_id": experiment_id}, {"is_favorite": new_status})


class RunsCollection(BaseCollection):
	"""Runs collection operations"""
	
	def __init__(self):
		super().__init__("runs")
	
	def find_by_experiment_id(self, experiment_id: str) -> List[Dict[str, Any]]:
		return self.find_many({"experiment_id": experiment_id})
	
	def create_run(self, revision_id: str, experiment_id: str, 
				   parent_revision_id: str, parent_run_id: str,
				   yaml_path: str, description: str = "", 
				   cli_flags: Dict[str, Any] = None) -> str:
		run_doc = {
			"revision_id": revision_id,
			"experiment_id": experiment_id,
			"parent_revision_id": parent_revision_id,
			"parent_run_id": parent_run_id,
			"created_at": datetime.utcnow(),
			"started_at": None,
			"ended_at": None,
			"yaml_path": yaml_path,
			"cli_flags": cli_flags or {},
			"tb_logdir": None,
			"stdout_log_path": None,
			"description": description,
			"results_text": "",
			"is_favorite": False
		}
		return self.insert_one(run_doc)
	
	def update_run_status(self, run_id: str, status_updates: Dict[str, Any]) -> bool:
		if "started_at" in status_updates or "ended_at" in status_updates:
			for key in ["started_at", "ended_at"]:
				if key in status_updates and status_updates[key] is None:
					status_updates[key] = datetime.utcnow()
		return self.update_one({"_id": run_id}, status_updates)
	
	def toggle_favorite(self, run_id: str) -> bool:
		"""Toggle the favorite status of a run"""
		run = self.find_one({"_id": run_id})
		if not run:
			return False
		new_status = not run.get("is_favorite", False)
		return self.update_one({"_id": run_id}, {"is_favorite": new_status})


class RevisionsCollection(BaseCollection):
	"""Revisions collection operations"""
	
	def __init__(self):
		super().__init__("revisions")
	
	def find_by_experiment_id(self, experiment_id: str) -> List[Dict[str, Any]]:
		return self.find_many({"experiment_id": experiment_id})
	
	def create_revision(self, experiment_id: str, name: str, description: str,
						parent_revision_id: str, parent_run_id: str,
						yaml_path: str, environment_id: str,
						cli_flags: Dict[str, Any] = None) -> str:
		# Get next version number
		last_revision = self.collection.find_one(
			{"experiment_id": experiment_id}, 
			sort=[("version", -1)]
		)
		version = (last_revision["version"] + 1) if last_revision else 1
		
		revision_doc = {
			"version": version,
			"experiment_id": experiment_id,
			"name": name,
			"description": description,
			"parent_revision_id": parent_revision_id,
			"parent_run_id": parent_run_id,
			"created_at": datetime.utcnow(),
			"yaml_path": yaml_path,
			"cli_flags": cli_flags or {},
			"environment_id": environment_id,
			"is_favorite": False
		}
		return self.insert_one(revision_doc)
	
	def toggle_favorite(self, revision_id: str) -> bool:
		"""Toggle the favorite status of a revision"""
		revision = self.find_one({"_id": revision_id})
		if not revision:
			return False
		new_status = not revision.get("is_favorite", False)
		return self.update_one({"_id": revision_id}, {"is_favorite": new_status})


class EnvironmentsCollection(BaseCollection):
	"""Environments collection operations"""
	
	def __init__(self):
		super().__init__("environments")
	
	def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
		return self.find_one({"name": name})
	
	def create_environment(self, name: str, description: str, file_info: dict = None, env_path: str = None, git_commit_url: str = None) -> str:
		# Get next version number for this name
		last_env = self.collection.find_one(
			{"name": name}, 
			sort=[("version", -1)]
		)
		version = (last_env["version"] + 1) if last_env else 1
		
		env_doc = {
			"version": version,
			"name": name,
			"description": description,
			"created_at": datetime.utcnow(),
			"env_path": env_path or "",
			"original_filename": file_info.get("original_filename", "") if file_info else "",
			"file_format": file_info.get("file_format", "") if file_info else "",
			"compressed_file_path": file_info.get("compressed_file_path", "") if file_info else "",
			"git_commit_url": git_commit_url
		}
		return self.insert_one(env_doc)
	
	def update_environment_paths(self, env_id: str, env_path: str, executable_file: str, 
								 compressed_file_path: str, original_filename: str, file_format: str) -> bool:
		"""Update environment paths after successful file processing"""
		update_data = {
			"env_path": env_path,
			"executable_file": executable_file,
			"compressed_file_path": compressed_file_path,
			"original_filename": original_filename,
			"file_format": file_format
		}
		return self.update_one({"_id": env_id}, update_data)


class SettingsCollection(BaseCollection):
	"""Settings collection operations"""
	
	def __init__(self):
		super().__init__("settings")
	
	def get_global_settings(self) -> Dict[str, Any]:
		settings = self.find_one({"_id": "global"})
		if not settings:
			# Create default settings
			default_settings = {
				"_id": "global",
				"non_critical_config": {}
			}
			self.insert_one(default_settings)
			return default_settings
		return settings
	
	def update_global_settings(self, payload: Dict[str, Any]) -> bool:
		# Use upsert to create if doesn't exist
		result = self.collection.update_one(
			{"_id": "global"}, 
			{"$set": payload}, 
			upsert=True
		)
		return result.upserted_id is not None or result.modified_count > 0


# Collection instances for easy access
users = UsersCollection()
experiments = ExperimentsCollection()
runs = RunsCollection()
revisions = RevisionsCollection()
environments = EnvironmentsCollection()
settings = SettingsCollection()

# Plugin collections will be added dynamically when plugin system initializes
# This avoids circular imports while keeping the plugin system separate