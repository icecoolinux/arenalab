'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { get, put } from "@/api/api-client";

export default function Settings() {
  const router = useRouter();
  const [settings, setSettings] = useState({
    openai_api_key: '',
    anthropic_api_key: '',
    openai_model: 'gpt-4o-mini',
    anthropic_model: 'claude-3-5-sonnet-20241022',
    llm_provider: 'openai'
  });
  const [originalSettings, setOriginalSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    try {
      setLoading(true);
      setError('');
      const data = await get('/api/settings');
      const loadedSettings = {
        openai_api_key: data.openai_api_key || '',
        anthropic_api_key: data.anthropic_api_key || '',
        openai_model: data.openai_model || 'gpt-4o-mini',
        anthropic_model: data.anthropic_model || 'claude-3-5-sonnet-20241022',
        llm_provider: data.llm_provider || 'openai'
      };
      setSettings(loadedSettings);
      setOriginalSettings(loadedSettings);
    } catch (e) {
      setError(`Error loading settings: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(e) {
    e.preventDefault();
    try {
      setSaving(true);
      setError('');
      setSuccess('');

      await put('/api/settings', settings);
      setSuccess('Settings saved successfully!');

      // Reload to get masked values
      setTimeout(() => {
        loadSettings();
        setSuccess('');
      }, 1500);
    } catch (e) {
      setError(`Error saving settings: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  function handleProviderChange(provider) {
    setSettings(prev => ({
      ...prev,
      llm_provider: provider
    }));
  }

  function handleApiKeyChange(value) {
    setSettings(prev => ({
      ...prev,
      [`${prev.llm_provider}_api_key`]: value
    }));
  }

  function handleModelChange(value) {
    setSettings(prev => ({
      ...prev,
      [`${prev.llm_provider}_model`]: value
    }));
  }

  function handleCancel() {
    if (originalSettings) {
      setSettings(originalSettings);
    }
    router.back();
  }

  function hasChanges() {
    if (!originalSettings) return false;
    return JSON.stringify(settings) !== JSON.stringify(originalSettings);
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-lg">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">Settings</h1>
        <p className="text-gray-400 text-sm">
          Configure application settings and API credentials
        </p>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-500 text-red-300 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-900/30 border border-green-500 text-green-300 px-4 py-3 rounded-lg mb-6">
          {success}
        </div>
      )}

      <form onSubmit={handleSave} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
        <div>
          <label className="block text-sm font-medium mb-2">
            Provider
          </label>
          <select
            value={settings.llm_provider}
            onChange={(e) => handleProviderChange(e.target.value)}
            className="input w-full"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium">
            {settings.llm_provider === 'openai' ? 'OpenAI' : 'Anthropic'} API Key
          </label>
          <p className="text-gray-500" style={{ fontSize: '11px', marginTop: '4px', marginBottom: '4px' }}>
            {settings.llm_provider === 'openai' ? 'Used for OpenAI models' : 'Used for Claude models'}
          </p>
          <input
            type="text"
            value={settings[`${settings.llm_provider}_api_key`]}
            onChange={(e) => handleApiKeyChange(e.target.value)}
            className="input w-full"
            placeholder={settings.llm_provider === 'openai' ? 'sk-...' : 'sk-ant-...'}
          />
        </div>

        <div>
          <label className="block text-sm font-medium">
            {settings.llm_provider === 'openai' ? 'OpenAI' : 'Anthropic'} Model
          </label>
          <p className="text-gray-500" style={{ fontSize: '11px', marginTop: '4px', marginBottom: '4px' }}>
            {settings.llm_provider === 'openai'
              ? 'Model to use for OpenAI API calls (e.g., gpt-4o-mini, gpt-4o, gpt-4-turbo)'
              : 'Model to use for Anthropic API calls (e.g., claude-3-5-sonnet-20241022, claude-3-opus-20240229)'}
          </p>
          <input
            type="text"
            value={settings[`${settings.llm_provider}_model`]}
            onChange={(e) => handleModelChange(e.target.value)}
            className="input w-full"
            placeholder={settings.llm_provider === 'openai' ? 'gpt-4o-mini' : 'claude-3-5-sonnet-20241022'}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', paddingTop: '16px' }}>
          <button
            type="button"
            onClick={handleCancel}
            className="btn"
            style={{ borderColor: '#6b7280', color: '#9ca3af' }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !hasChanges()}
            className="btn"
            style={{
              borderColor: hasChanges() && !saving ? '#3b82f6' : '#374151',
              color: hasChanges() && !saving ? '#60a5fa' : '#6b7280',
              cursor: hasChanges() && !saving ? 'pointer' : 'not-allowed'
            }}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </form>
    </div>
  );
}
