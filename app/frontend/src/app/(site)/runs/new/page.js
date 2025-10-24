'use client';
import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { get, post, getWorkspaceFile } from "@/api/api-client";
import Link from 'next/link';
import YamlEditor from '@/components/YamlEditor';
import CLIFlagsEditor from '@/components/CLIFlagsEditor';
import PluginCard from '@/components/PluginCard';

function NewRunForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const revisionId = searchParams.get('revision_id');
  const sourceRunId = searchParams.get('source');

  const [experiments, setExperiments] = useState([]);
  const [revisions, setRevisions] = useState([]);
  const [selectedRevision, setSelectedRevision] = useState(null);
  const [form, setForm] = useState({
    experiment_id: '',
    revision_id: revisionId || '',
    yaml: '',
    cli_flags: '{}',
    description: '',
    results_text: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [yamlExpanded, setYamlExpanded] = useState(false);
  const [createMode, setCreateMode] = useState('create-and-run'); // 'create-only' or 'create-and-run'
  const [sourceRun, setSourceRun] = useState(null);
  const [plugins, setPlugins] = useState([]);
  const [selectedPlugins, setSelectedPlugins] = useState([]);
  const [pluginSettings, setPluginSettings] = useState({});

  useEffect(() => {
    loadData();
    loadPlugins();
  }, []);

  useEffect(() => {
    if (sourceRunId) {
      loadSourceRunData();
    }
  }, [sourceRunId]);

  useEffect(() => {
    if (form.experiment_id) {
      loadRevisions(form.experiment_id);
    }
  }, [form.experiment_id]);

  useEffect(() => {
    if (form.revision_id) {
      loadRevisionData(form.revision_id);
    }
  }, [form.revision_id]);

  async function loadData() {
    try {
      const [experimentsData, revisionsData] = await Promise.all([
        get('/api/experiments'),
        get('/api/revisions')
      ]);
      
      setExperiments(experimentsData);
      setRevisions(revisionsData);

      if (revisionId) {
        const revision = revisionsData.find(r => r._id === revisionId);
        if (revision) {
          setForm(prev => ({
            ...prev,
            experiment_id: revision.experiment_id,
            revision_id: revisionId
          }));
        }
      }
    } catch (e) {
      setError(`Error loading data: ${e.message}`);
    }
  }

  async function loadRevisions(experimentId) {
    try {
      const revisionsData = await get('/api/revisions', { 
        query: { experiment_id: experimentId } 
      });
      setRevisions(revisionsData);
    } catch (e) {
      console.error('Error loading revisions:', e);
    }
  }

  async function loadRevisionData(revisionId) {
    try {
      const revision = await get(`/api/revisions/${revisionId}`);
      setSelectedRevision(revision);
      
      const yamlContent = revision.yaml_path ? 
        await getWorkspaceFile(revision.yaml_path).catch(() => '') : '';
      
      setForm(prev => ({
        ...prev,
        yaml: yamlContent || '# ML-Agents YAML Configuration\n',
        cli_flags: JSON.stringify(revision.cli_flags || {}, null, 2)
      }));
    } catch (e) {
      console.error('Error loading revision data:', e);
    }
  }

  async function loadPlugins() {
    try {
      const res = await get('/api/plugins?scope=run');
      setPlugins(res.plugins || []);
    } catch (e) {
      console.error('Error loading plugins:', e.message);
    }
  }

  async function loadSourceRunData() {
    try {
      const runData = await get(`/api/runs/${sourceRunId}`);
      setSourceRun(runData);

      // Load the YAML content from the source run
      const yamlContent = runData.yaml_path ?
        await getWorkspaceFile(runData.yaml_path).catch(() => '') : '';

      // Pre-populate the form with source run data
      setForm(prev => ({
        ...prev,
        experiment_id: runData.experiment_id,
        revision_id: runData.revision_id,
        yaml: yamlContent || '# ML-Agents YAML Configuration\n',
        cli_flags: JSON.stringify(runData.cli_flags || {}, null, 2),
        description: `Based on run ${runData._id.slice(-8)}`,
        results_text: ''
      }));
    } catch (e) {
      console.error('Error loading source run data:', e);
      setError(`Error loading source run: ${e.message}`);
    }
  }

  async function createRun(e) {
    e.preventDefault();
    if (!form.experiment_id || !form.revision_id || !form.yaml.trim()) {
      setError('Experiment, revision, and YAML configuration are required');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      let parsedFlags = {};
      if (form.cli_flags.trim()) {
        try {
          parsedFlags = JSON.parse(form.cli_flags);
        } catch (e) {
          setError('Invalid JSON in CLI flags');
          return;
        }
      }

      const body = {
        ...form,
        cli_flags: parsedFlags,
        enabled_plugins: selectedPlugins.map(pluginName => ({
          name: pluginName,
          enabled: true,
          settings: pluginSettings[pluginName] || {},
          enabled_at: new Date().toISOString()
        }))
      };

      // Add auto_start parameter based on create mode
      const queryParams = createMode === 'create-only' ? '?auto_start=false' : '';
      const result = await post(`/api/runs${queryParams}`, body);
      router.push(`/runs/${result._id}`);
    } catch (e) {
      setError(`Error creating run: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  const filteredRevisions = revisions.filter(r =>
    !form.experiment_id || r.experiment_id === form.experiment_id
  );

  function togglePlugin(pluginName) {
    if (selectedPlugins.includes(pluginName)) {
      setSelectedPlugins(selectedPlugins.filter(p => p !== pluginName));
      const newSettings = { ...pluginSettings };
      delete newSettings[pluginName];
      setPluginSettings(newSettings);
    } else {
      setSelectedPlugins([...selectedPlugins, pluginName]);
      // Initialize with default settings
      const plugin = plugins.find(p => p.name === pluginName);
      if (plugin && plugin.settings_schema) {
        const defaultSettings = {};
        Object.entries(plugin.settings_schema).forEach(([key, spec]) => {
          if (spec.default !== undefined) {
            defaultSettings[key] = spec.default;
          }
        });
        setPluginSettings({
          ...pluginSettings,
          [pluginName]: defaultSettings
        });
      }
    }
  }

  function updatePluginSetting(pluginName, settingKey, value) {
    setPluginSettings({
      ...pluginSettings,
      [pluginName]: {
        ...pluginSettings[pluginName],
        [settingKey]: value
      }
    });
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2>New Run</h2>
          <Link href="/runs" className="btn" style={{ border: '1px solid #6b7280' }}>
            Cancel
          </Link>
        </div>

        {sourceRun && (
          <div style={{ 
            background: '#374151', 
            border: '1px solid #6366f1',
            padding: '12px', 
            borderRadius: '8px', 
            marginBottom: '16px',
            fontSize: '14px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '16px' }}>📋</span>
              <div>
                <strong>Duplicating run:</strong> {sourceRun._id.slice(-8)}
                <br />
                <small style={{ color: '#9ca3af' }}>
                  You can modify any field before creating the new run
                </small>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div style={{ 
            background: '#dc2626', 
            color: 'white', 
            padding: '12px', 
            borderRadius: '8px', 
            marginBottom: '16px' 
          }}>
            {error}
          </div>
        )}

        <form onSubmit={createRun}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                Experiment *
              </label>
              <select
                className="input"
                value={form.experiment_id}
                onChange={e => setForm({...form, experiment_id: e.target.value, revision_id: ''})}
                required
              >
                <option value="">Select an experiment</option>
                {experiments.map(exp => (
                  <option key={exp._id} value={exp._id}>
                    {exp.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                Revision *
              </label>
              <select
                className="input"
                value={form.revision_id}
                onChange={e => setForm({...form, revision_id: e.target.value})}
                required
                disabled={!form.experiment_id}
              >
                <option value="">Select a revision</option>
                {filteredRevisions.map(rev => (
                  <option key={rev._id} value={rev._id}>
                    v{rev.version} - {rev.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {selectedRevision && (
            <div style={{ 
              background: '#374151', 
              padding: '12px', 
              borderRadius: '6px',
              marginBottom: '16px',
              fontSize: '12px'
            }}>
              <strong>Selected revision:</strong> v{selectedRevision.version} - {selectedRevision.name}
              <br />
              {selectedRevision.description && (
                <>
                  <strong>Description:</strong> {selectedRevision.description}
                </>
              )}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <label style={{ fontWeight: 'bold', margin: 0 }}>
                YAML Configuration *
              </label>
              <button
                type="button"
                className="btn"
                onClick={() => setYamlExpanded(!yamlExpanded)}
                style={{
                  border: '1px solid #374151',
                  fontSize: '12px',
                  padding: '6px 12px'
                }}
              >
                {yamlExpanded ? '⌃ Collapse' : '⌄ Expand'}
              </button>
            </div>
            <YamlEditor
              value={form.yaml}
              onChange={value => setForm({...form, yaml: value})}
              placeholder="# ML-Agents YAML Configuration"
              height={yamlExpanded ? `${Math.max(600, form.yaml.split('\n').length * 18)}px` : "300px"}
              required
            />
            <small style={{ color: '#9ca3af' }}>
              YAML configuration for ML-Agents training
            </small>
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
              CLI Flags
            </label>
            <CLIFlagsEditor
              value={form.cli_flags}
              onChange={value => setForm({...form, cli_flags: value})}
            />
            <small style={{ color: '#9ca3af', display: 'block', marginTop: '8px' }}>
              Flags for the mlagents-learn command
            </small>
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
              Description
            </label>
            <textarea
              className="input"
              value={form.description}
              onChange={e => setForm({...form, description: e.target.value})}
              rows={3}
              placeholder="Description of this run (optional)"
            />
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
              Results Notes
            </label>
            <textarea
              className="input"
              value={form.results_text}
              onChange={e => setForm({...form, results_text: e.target.value})}
              rows={3}
              placeholder="Space for notes about expected results (optional)"
            />
          </div>

          {/* Plugin Selection */}
          {plugins.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <div style={{
                marginBottom: '16px',
                paddingBottom: '12px',
                borderBottom: '2px solid #374151'
              }}>
                <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px', fontSize: '16px' }}>
                  <span style={{ fontSize: '20px' }}>🔌</span>
                  Run Plugins
                </h4>
                <p style={{
                  margin: '4px 0 0 0',
                  fontSize: '13px',
                  color: '#9ca3af'
                }}>
                  Optional automation tools for this specific run
                </p>
              </div>

              <div style={{ display: 'grid', gap: '12px' }}>
                {plugins.map(plugin => (
                  <PluginCard
                    key={plugin.name}
                    plugin={plugin}
                    isSelected={selectedPlugins.includes(plugin.name)}
                    onToggle={togglePlugin}
                    pluginSettings={pluginSettings[plugin.name] || {}}
                    onSettingChange={(key, value) => updatePluginSetting(plugin.name, key, value)}
                  />
                ))}
              </div>

              {selectedPlugins.length > 0 && (
                <div style={{
                  marginTop: '16px',
                  padding: '12px 16px',
                  backgroundColor: '#1e3a5f',
                  borderRadius: '8px',
                  border: '2px solid #60a5fa'
                }}>
                  <div style={{
                    fontSize: '13px',
                    color: '#93c5fd',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontWeight: '500'
                  }}>
                    <span style={{ fontSize: '16px' }}>✓</span>
                    {selectedPlugins.length} plugin{selectedPlugins.length > 1 ? 's' : ''} enabled:
                    <span style={{ color: '#bfdbfe' }}>{selectedPlugins.join(', ')}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
              Creation Mode
            </label>
            <div style={{ display: 'flex', gap: '16px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="createMode"
                  value="create-and-run"
                  checked={createMode === 'create-and-run'}
                  onChange={e => setCreateMode(e.target.value)}
                />
                <div>
                  <div style={{ fontWeight: 'bold', fontSize: '14px' }}>Create and Run</div>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>Creates the run and starts immediately</div>
                </div>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="createMode"
                  value="create-only"
                  checked={createMode === 'create-only'}
                  onChange={e => setCreateMode(e.target.value)}
                />
                <div>
                  <div style={{ fontWeight: 'bold', fontSize: '14px' }}>Create Only</div>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>Creates the run without starting (immutable)</div>
                </div>
              </label>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <Link href="/runs" className="btn" style={{ border: '1px solid #6b7280' }}>
              Cancel
            </Link>
            <button
              className="btn"
              type="submit"
              disabled={loading}
              style={{ border: loading ? '1px solid #6b7280' : '1px solid #10b981' }}
            >
              {loading
                ? (createMode === 'create-only' ? 'Creating...' : 'Creating and running...')
                : (createMode === 'create-only' ? 'Create Run' : 'Create and Run')
              }
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

export default function NewRun() {
  return (
    <Suspense fallback={<div className="card">Loading...</div>}>
      <NewRunForm />
    </Suspense>
  );
}