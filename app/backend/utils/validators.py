"""
Shared validation utilities for Pydantic models.

This module provides reusable validators to avoid duplication across model definitions.
"""
import re
from pydantic import validator


def create_name_validator(field_name: str = 'name'):
    """
    Create a validator for name fields that ensures non-empty, trimmed strings.

    Args:
        field_name: The name of the field to validate (default: 'name')

    Returns:
        A Pydantic validator function
    """
    @validator(field_name)
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError(f'{field_name.capitalize()} cannot be empty or whitespace')
        return v.strip()
    return validate_name


def create_email_validator(field_name: str = 'email'):
    """
    Create a validator for email fields with format validation.

    Args:
        field_name: The name of the field to validate (default: 'email')

    Returns:
        A Pydantic validator function
    """
    @validator(field_name)
    def validate_email(cls, v):
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', v):
            raise ValueError('Invalid email format')
        return v.lower()
    return validate_email


def create_password_validator(field_name: str = 'password'):
    """
    Create a validator for password fields with strength requirements.

    Requirements:
    - Minimum 8 characters
    - At least one letter
    - At least one number

    Args:
        field_name: The name of the field to validate (default: 'password')

    Returns:
        A Pydantic validator function
    """
    @validator(field_name)
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        return v
    return validate_password


# Standalone validation functions that can be used directly
def validate_name_string(value: str, field_name: str = 'name') -> str:
    """
    Validate and normalize a name string.

    Args:
        value: The string to validate
        field_name: Name of the field for error messages

    Returns:
        Trimmed string

    Raises:
        ValueError: If string is empty or whitespace
    """
    if not value or not value.strip():
        raise ValueError(f'{field_name.capitalize()} cannot be empty or whitespace')
    return value.strip()


def validate_email_string(value: str) -> str:
    """
    Validate and normalize an email string.

    Args:
        value: The email string to validate

    Returns:
        Lowercase email string

    Raises:
        ValueError: If email format is invalid
    """
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', value):
        raise ValueError('Invalid email format')
    return value.lower()


def validate_password_string(value: str) -> None:
    """
    Validate password strength requirements.

    Args:
        value: The password to validate

    Raises:
        ValueError: If password doesn't meet requirements
    """
    if len(value) < 8:
        raise ValueError('Password must be at least 8 characters long')
    if not re.search(r'[A-Za-z]', value):
        raise ValueError('Password must contain at least one letter')
    if not re.search(r'[0-9]', value):
        raise ValueError('Password must contain at least one number')
