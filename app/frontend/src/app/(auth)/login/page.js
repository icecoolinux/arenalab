'use client';
import { useState } from 'react';
import { login } from "@/api/api-client";
import { useRouter } from "next/navigation";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(email, password);
      router.push("/");
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div style={{
      background: '#111827',
      border: '1px solid #1f2937',
      borderRadius: '16px',
      padding: '2rem',
      width: '100%',
      maxWidth: '400px',
      boxShadow: '0 10px 25px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.05)'
    }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <div style={{
          width: '64px',
          height: '64px',
          background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
          borderRadius: '16px',
          margin: '0 auto 1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '24px',
          fontWeight: 'bold',
          color: 'white'
        }}>
          ML
        </div>
        <h1 style={{
          fontSize: '1.875rem',
          fontWeight: '700',
          color: '#f9fafb',
          margin: '0 0 0.5rem 0'
        }}>
          Welcome Back
        </h1>
        <p style={{
          color: '#9ca3af',
          fontSize: '0.875rem',
          margin: '0'
        }}>
          Sign in to your ArenaLab account
        </p>
      </div>

      {/* Form */}
      <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Email Field */}
        <div>
          <label htmlFor="email" style={{
            display: 'block',
            fontSize: '0.875rem',
            fontWeight: '500',
            color: '#f3f4f6',
            marginBottom: '0.5rem'
          }}>
            Email Address
          </label>
          <input
            id="email"
            type="email"
            required
            style={{
              width: '100%',
              padding: '0.75rem 1rem',
              fontSize: '0.875rem',
              border: '1px solid #374151',
              borderRadius: '8px',
              background: '#0f172a',
              color: '#f1f5f9',
              transition: 'all 0.2s',
              outline: 'none',
              boxSizing: 'border-box'
            }}
            onFocus={(e) => e.target.style.borderColor = '#2563eb'}
            onBlur={(e) => e.target.style.borderColor = '#374151'}
            placeholder="Enter your email"
            value={email}
            onChange={e => setEmail(e.target.value)}
          />
        </div>

        {/* Password Field */}
        <div>
          <label htmlFor="password" style={{
            display: 'block',
            fontSize: '0.875rem',
            fontWeight: '500',
            color: '#f3f4f6',
            marginBottom: '0.5rem'
          }}>
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            style={{
              width: '100%',
              padding: '0.75rem 1rem',
              fontSize: '0.875rem',
              border: '1px solid #374151',
              borderRadius: '8px',
              background: '#0f172a',
              color: '#f1f5f9',
              transition: 'all 0.2s',
              outline: 'none',
              boxSizing: 'border-box'
            }}
            onFocus={(e) => e.target.style.borderColor = '#2563eb'}
            onBlur={(e) => e.target.style.borderColor = '#374151'}
            placeholder="Enter your password"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
        </div>

        {/* Error Message */}
        {error && (
          <div style={{
            padding: '0.75rem',
            background: '#7f1d1d',
            border: '1px solid #991b1b',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '0.875rem'
          }}>
            {error}
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading}
          style={{
            width: '100%',
            padding: '0.75rem',
            fontSize: '0.875rem',
            fontWeight: '600',
            color: 'white',
            background: isLoading ? '#1e40af' : '#2563eb',
            border: 'none',
            borderRadius: '8px',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem'
          }}
          onMouseEnter={(e) => {
            if (!isLoading) {
              e.target.style.background = '#1d4ed8';
            }
          }}
          onMouseLeave={(e) => {
            if (!isLoading) {
              e.target.style.background = '#2563eb';
            }
          }}
        >
          {isLoading ? (
            <>
              <div style={{
                width: '16px',
                height: '16px',
                border: '2px solid transparent',
                borderTop: '2px solid white',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite'
              }}></div>
              Signing In...
            </>
          ) : (
            'Sign In'
          )}
        </button>
      </form>

      <style jsx>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
