from pydantic import BaseModel, Field, validator
from typing import Union
from typing import Optional, Literal
from datetime import datetime
from enum import Enum
import re
from utils.validators import validate_name_string, validate_email_string, validate_password_string

class UserRole(str, Enum):
	USER = "user"
	ADMIN = "admin"

class ExperimentModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	name: str = Field(..., min_length=1, max_length=100, description="Experiment name")
	description: str = Field("", max_length=500, description="Experiment description")
	tags: list[str] = Field(default=[], description="List of tags")
	created_at: datetime
	updated_at: datetime
	results_text: str = Field(default="", description="Experiment results text")
	is_favorite: bool = Field(default=False, description="Whether experiment is marked as favorite")

	class Config:
		populate_by_name = True

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')
	
class ExperimentBody(BaseModel):
	name: str = Field(..., min_length=1, max_length=100, description="Experiment name")
	description: str = Field("", max_length=500, description="Experiment description")
	tags: list[str] = Field(default=[], description="List of tags")
	results_text: str = Field(default="", description="Experiment results text")
	is_favorite: bool = Field(default=False, description="Whether experiment is marked as favorite")
	enabled_plugins: list[dict] = Field(default=[], description="List of enabled plugins with settings")

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')

class RevisionModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	version: int = Field(..., ge=1, description="Revision version number")
	experiment_id: str = Field(..., description="Parent experiment ID")
	name: str = Field(..., min_length=1, max_length=100, description="Revision name")
	description: str = Field(..., max_length=500, description="Revision description")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	created_at: datetime
	yaml_path: str = Field(..., description="Path to YAML configuration")
	cli_flags: dict = Field(default={}, description="CLI flags for ML-Agents")
	environment_id: str = Field(..., description="Environment ID")
	results_text: str = Field(default="", description="Revision results text")
	is_favorite: bool = Field(default=False, description="Whether revision is marked as favorite")
	
	class Config:
		populate_by_name = True

class RevisionBody(BaseModel):
	experiment_id: str = Field(..., description="Parent experiment ID")
	name: str = Field(..., min_length=1, max_length=100, description="Revision name")
	description: str = Field(..., max_length=500, description="Revision description")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	yaml: str = Field(..., min_length=1, description="YAML configuration content")
	cli_flags: dict = Field(default={}, description="CLI flags for ML-Agents")
	environment_id: str = Field(..., description="Environment ID")
	results_text: str = Field(default="", description="Revision results text")
	is_favorite: bool = Field(default=False, description="Whether revision is marked as favorite")

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')

class RunModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	revision_id: str = Field(..., description="Revision ID")
	experiment_id: str = Field(..., description="Experiment ID")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	name: str = Field(default="", max_length=100, description="Human-readable run name")
	created_at: datetime
	started_at: Optional[datetime] = Field(None, description="Run start timestamp")
	ended_at: Optional[datetime] = Field(None, description="Run end timestamp")
	execution_count: int = Field(default=0, description="Number of times run has been executed/restarted")
	last_restarted_at: Optional[datetime] = Field(None, description="Last restart timestamp")
	yaml_path: str = Field(..., description="Path to YAML configuration")
	cli_flags: dict = Field(default={}, description="CLI flags for ML-Agents")
	tb_logdir: Optional[str] = Field(None, description="TensorBoard log directory")
	stdout_log_path: Optional[str] = Field(None, description="Stdout log file path")
	description: str = Field(..., max_length=500, description="Run description")
	results_text: str = Field(default="", description="Run results text")
	is_favorite: bool = Field(default=False, description="Whether run is marked as favorite")

	class Config:
		populate_by_name = True

class RunBody(BaseModel):
	revision_id: str = Field(..., description="Revision ID")
	experiment_id: str = Field(..., description="Experiment ID")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	name: str = Field(default="", max_length=100, description="Human-readable run name")
	yaml: str = Field(..., min_length=1, description="YAML configuration content")
	cli_flags: dict = Field(default={}, description="CLI flags for ML-Agents")
	description: str = Field(..., max_length=500, description="Run description")
	results_text: str = Field(default="", description="Run results text")
	is_favorite: bool = Field(default=False, description="Whether run is marked as favorite")
	enabled_plugins: list[dict] = Field(default=[], description="List of enabled plugins with settings")

class EnvironmentModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	version: int = Field(..., ge=1, description="Environment version number")
	name: str = Field(..., min_length=1, max_length=100, description="Environment name")
	description: str = Field(..., max_length=500, description="Environment description")
	created_at: datetime
	env_path: str = Field(..., description="Path to environment directory")
	executable_file: Optional[str] = Field(None, description="Executable filename (relative to env_path)")
	original_filename: str = Field(..., description="Original compressed file name")
	file_format: str = Field(..., description="Compressed file format (zip, tar.gz, tgz, bz2)")
	compressed_file_path: str = Field(..., description="Path to original compressed file")
	git_commit_url: Optional[str] = Field(None, description="Git commit URL for environment source code")

	class Config:
		populate_by_name = True

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')
	
class EnvironmentBody(BaseModel):
	name: str = Field(..., min_length=1, max_length=100, description="Environment name")
	description: str = Field(..., max_length=500, description="Environment description")
	git_commit_url: Optional[str] = Field(None, description="Git commit URL for environment source code")

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')

class UserModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	email: str = Field(..., description="User email address")
	name: str = Field(..., min_length=1, max_length=100, description="User full name")
	password_hash: str = Field(..., description="Hashed password")
	role: UserRole = Field(UserRole.USER, description="User role")
	created_at: datetime
	last_login: Optional[datetime] = Field(None, description="Last login timestamp")
	is_active: bool = Field(True, description="User account status")

	class Config:
		populate_by_name = True

	@validator('email')
	def validate_email(cls, v):
		return validate_email_string(v)

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')

class UserBody(BaseModel):
	email: str = Field(..., description="User email address")
	name: str = Field(..., min_length=1, max_length=100, description="User full name")
	password: str = Field(..., min_length=8, description="User password")
	role: UserRole = Field(UserRole.USER, description="User role")

	@validator('name')
	def validate_name(cls, v):
		return validate_name_string(v, 'name')

	@validator('email')
	def validate_email(cls, v):
		return validate_email_string(v)

	@validator('password')
	def validate_password(cls, v):
		validate_password_string(v)
		return v

class LoginBody(BaseModel):
	email: str = Field(..., description="User email address")
	password: str = Field(..., min_length=1, description="User password")

	@validator('email')
	def validate_email(cls, v):
		return validate_email_string(v)

class UserResponse(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	email: str = Field(..., description="User email address")
	name: str = Field(..., description="User full name")
	role: UserRole = Field(..., description="User role")
	created_at: datetime
	last_login: Optional[datetime] = Field(None, description="Last login timestamp")
	is_active: bool = Field(..., description="User account status")
	
	class Config:
		populate_by_name = True

class ExperimentResponse(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	name: str = Field(..., description="Experiment name")
	description: str = Field(..., description="Experiment description")
	tags: list[str] = Field(..., description="List of tags")
	created_at: datetime
	updated_at: datetime
	results_text: str = Field(default="", description="Experiment results text")
	is_favorite: bool = Field(default=False, description="Whether experiment is marked as favorite")
	enabled_plugins: list[dict] = Field(default=[], description="List of enabled plugins with settings")

	class Config:
		populate_by_name = True

class RevisionResponse(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	version: int = Field(..., description="Revision version number")
	experiment_id: str = Field(..., description="Parent experiment ID")
	name: str = Field(..., description="Revision name")
	description: str = Field(..., description="Revision description")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	created_at: datetime
	yaml_path: str = Field(..., description="Path to YAML configuration")
	cli_flags: dict = Field(..., description="CLI flags for ML-Agents")
	environment_id: str = Field(..., description="Environment ID")
	results_text: str = Field(default="", description="Revision results text")
	is_favorite: bool = Field(default=False, description="Whether revision is marked as favorite")
	
	class Config:
		populate_by_name = True

class RunResponse(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	revision_id: str = Field(..., description="Revision ID")
	experiment_id: str = Field(..., description="Experiment ID")
	parent_revision_id: Optional[str] = Field(None, description="Parent revision ID")
	parent_run_id: Optional[str] = Field(None, description="Parent run ID")
	name: str = Field(default="", max_length=100, description="Human-readable run name")
	created_at: datetime
	started_at: Optional[datetime] = Field(None, description="Run start timestamp")
	ended_at: Optional[datetime] = Field(None, description="Run end timestamp")
	execution_count: int = Field(default=0, description="Number of times run has been executed/restarted")
	last_restarted_at: Optional[datetime] = Field(None, description="Last restart timestamp")
	yaml_path: str = Field(..., description="Path to YAML configuration")
	cli_flags: dict = Field(..., description="CLI flags for ML-Agents")
	tb_logdir: Optional[str] = Field(None, description="TensorBoard log directory")
	stdout_log_path: Optional[str] = Field(None, description="Stdout log file path")
	description: str = Field(..., description="Run description")
	results_text: str = Field(..., description="Run results text")
	is_favorite: bool = Field(default=False, description="Whether run is marked as favorite")

	class Config:
		populate_by_name = True

class EnvironmentResponse(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	version: int = Field(..., description="Environment version number")
	name: str = Field(..., description="Environment name")
	description: str = Field(..., description="Environment description")
	created_at: datetime
	env_path: str = Field(..., description="Path to environment directory")
	executable_file: Optional[str] = Field(None, description="Executable filename (relative to env_path)")
	original_filename: str = Field(..., description="Original compressed file name")
	file_format: str = Field(..., description="Compressed file format")
	compressed_file_path: str = Field(..., description="Path to original compressed file")
	git_commit_url: Optional[str] = Field(None, description="Git commit URL for environment source code")

	class Config:
		populate_by_name = True

class LLMUsageModel(BaseModel):
	id: str = Field(..., alias="_id", description="MongoDB ObjectId")
	provider: str = Field(..., description="LLM provider (openai, anthropic)")
	model: str = Field(..., description="Model name")
	prompt_tokens: int = Field(..., description="Number of prompt tokens")
	completion_tokens: int = Field(..., description="Number of completion tokens")
	total_tokens: int = Field(..., description="Total tokens used")
	created_at: datetime = Field(..., description="Timestamp of the API call")
	context: dict = Field(default_factory=dict, description="Additional context (experiment_id, run_id, plugin_name, etc.)")
	usage_details: dict = Field(default_factory=dict, description="Provider-specific usage details")

	class Config:
		populate_by_name = True