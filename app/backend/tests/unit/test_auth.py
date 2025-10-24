"""
Unit tests for authentication module.

Tests password hashing, token creation, and validation.
"""

import pytest
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError

from auth import hash_password, verify_password, create_access_token


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_creates_hash(self):
        """Test that hash_password creates a valid hash."""
        password = "test_password_123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 20  # Argon2 hashes are long
        assert hashed.startswith("$argon2")

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "my_secure_password"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_password_different_each_time(self):
        """Test that same password produces different hashes (salt)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


@pytest.mark.unit
class TestTokenCreation:
    """Test JWT token creation and validation."""

    def test_create_access_token_basic(self):
        """Test basic token creation."""
        email = "test@example.com"
        token = create_access_token(email)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long

    def test_create_access_token_contains_subject(self):
        """Test that token contains the subject (email)."""
        email = "user@example.com"
        token = create_access_token(email)

        # Decode without verification to check payload
        secret = os.getenv("JWT_SECRET", "devsecret")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        assert payload["sub"] == email

    def test_create_access_token_has_expiration(self):
        """Test that token has expiration time."""
        email = "user@example.com"
        token = create_access_token(email, expires_minutes=60)

        secret = os.getenv("JWT_SECRET", "devsecret")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        assert "exp" in payload
        exp_time = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()

        # Should expire in approximately 60 minutes
        diff = (exp_time - now).total_seconds()
        assert 3500 < diff < 3700  # ~60 minutes (with tolerance)

    def test_create_access_token_custom_expiration(self):
        """Test token with custom expiration."""
        email = "user@example.com"
        token = create_access_token(email, expires_minutes=30)

        secret = os.getenv("JWT_SECRET", "devsecret")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        exp_time = datetime.utcfromtimestamp(payload["exp"])
        now = datetime.utcnow()
        diff = (exp_time - now).total_seconds()

        # Should expire in approximately 30 minutes
        assert 1700 < diff < 1900


@pytest.mark.unit
class TestTokenValidation:
    """Test token validation and decoding."""

    def test_valid_token_can_be_decoded(self):
        """Test that valid token can be decoded."""
        email = "test@example.com"
        token = create_access_token(email)

        secret = os.getenv("JWT_SECRET", "devsecret")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        assert payload["sub"] == email

    def test_expired_token_raises_error(self):
        """Test that expired token raises JWTError."""
        email = "test@example.com"
        secret = os.getenv("JWT_SECRET", "devsecret")

        # Create already-expired token
        exp = datetime.utcnow() - timedelta(minutes=5)
        expired_token = jwt.encode({"sub": email, "exp": exp}, secret, algorithm="HS256")

        with pytest.raises(JWTError):
            jwt.decode(expired_token, secret, algorithms=["HS256"])

    def test_invalid_token_raises_error(self):
        """Test that invalid token raises JWTError."""
        secret = os.getenv("JWT_SECRET", "devsecret")
        invalid_token = "not.a.valid.token"

        with pytest.raises(JWTError):
            jwt.decode(invalid_token, secret, algorithms=["HS256"])

    def test_token_with_wrong_secret_fails(self):
        """Test that token with wrong secret cannot be decoded."""
        email = "test@example.com"
        token = create_access_token(email)

        wrong_secret = "wrong_secret_key"

        with pytest.raises(JWTError):
            jwt.decode(token, wrong_secret, algorithms=["HS256"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
