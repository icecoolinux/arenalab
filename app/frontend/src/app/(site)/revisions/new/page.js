'use client';
import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { get, post, getWorkspaceFile } from "@/api/api-client";
import Link from 'next/link';
import YamlEditor from '@/components/YamlEditor';
import CLIFlagsEditor from '@/components/CLIFlagsEditor';

function NewRevisionForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const experimentId = searchParams.get('experiment_id');
  const parentRevisionId = searchParams.get('parent_revision_id');
  const parentRunId = searchParams.get('parent_run_id');
  
  // Determine creation context
  const isPromotionFromRevision = !!parentRevisionId;
  const isPromotionFromRun = !!parentRunId;
  const isNewFromExperiment = !!experimentId && !parentRevisionId && !parentRunId;

  const [experiments, setExperiments] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [parentRevision, setParentRevision] = useState(null);
  const [parentRun, setParentRun] = useState(null);
  const [form, setForm] = useState({
    experiment_id: experimentId || '',
    name: '',
    description: '',
    parent_revision_id: parentRevisionId || '',
    parent_run_id: parentRunId || '',
    yaml: '',
    cli_flags: '{}',
    environment_id: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [yamlExpanded, setYamlExpanded] = useState(false);

  useEffect(() => {
    loadData();
  }, []);


  async function loadData() {
    try {
      const [experimentsData, environmentsData] = await Promise.all([
        get('/api/experiments'),
        get('/api/environments')
      ]);
      
      setExperiments(experimentsData);
      setEnvironments(environmentsData);

      // Load parent data if promoting from revision or run
      if (parentRevisionId) {
        const parentRevData = await get(`/api/revisions/${parentRevisionId}`);
        setParentRevision(parentRevData);
        
        // Load YAML from parent revision
        const yamlContent = parentRevData.yaml_path ? 
          await getWorkspaceFile(parentRevData.yaml_path).catch(() => getDefaultYaml()) : 
          getDefaultYaml();
        
        setForm(prev => ({
          ...prev,
          experiment_id: parentRevData.experiment_id,
          environment_id: parentRevData.environment_id,
          name: `${parentRevData.name} - New Revision`,
          yaml: yamlContent,
          cli_flags: JSON.stringify(parentRevData.cli_flags || {}, null, 2)
        }));
      } else if (parentRunId) {
        const parentRunData = await get(`/api/runs/${parentRunId}`);
        setParentRun(parentRunData);
        
        // Load revision data for environment and other settings
        const parentRevData = await get(`/api/revisions/${parentRunData.revision_id}`);
        setParentRevision(parentRevData);
        
        setForm(prev => ({
          ...prev,
          experiment_id: parentRunData.experiment_id,
          environment_id: parentRevData.environment_id,
          name: `Run ${parentRunData._id.slice(-8)} - New Revision`,
          yaml: parentRunData.yaml_snapshot || getDefaultYaml(),
          cli_flags: JSON.stringify(parentRunData.cli_flags || {}, null, 2)
        }));
      } else if (experimentId) {
        const experiment = experimentsData.find(e => e._id === experimentId);
        if (experiment) {
          setForm(prev => ({
            ...prev,
            experiment_id: experimentId,
            name: `${experiment.name} - Revision`,
            yaml: getDefaultYaml()
          }));
        }
      } else {
        setForm(prev => ({ ...prev, yaml: getDefaultYaml() }));
      }
    } catch (e) {
      setError(`Error loading data: ${e.message}`);
    }
  }


  function getDefaultYaml() {
    return `behaviors:
  YourBehaviorName:
    trainer_type: ppo
    hyperparameters:
      batch_size: 64
      buffer_size: 2048
      learning_rate: 3.0e-4
      beta: 5.0e-3
      epsilon: 0.2
      lambd: 0.95
      num_epoch: 3
    network_settings:
      hidden_units: 128
      num_layers: 2
    reward_signals:
      extrinsic:
        gamma: 0.99
        strength: 1.0
    max_steps: 500000
    time_horizon: 64
    summary_freq: 10000
`;
  }

  async function createRevision(e) {
    e.preventDefault();
    if (!form.experiment_id || !form.name.trim() || !form.yaml.trim() || !form.environment_id) {
      setError('Experiment, name, YAML configuration, and environment are required');
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
        created_at: new Date().toISOString()
      };

      const result = await post('/api/revisions', body);
      router.push(`/revisions/${result._id}`);
    } catch (e) {
      setError(`Error creating revision: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }


  const selectedExperiment = experiments.find(e => e._id === form.experiment_id);

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2>New Revision</h2>
          <Link href="/revisions" className="btn" style={{ border: '1px solid #6b7280' }}>
            Cancel
          </Link>
        </div>

        {selectedExperiment && (
          <div style={{ 
            background: '#374151', 
            padding: '12px', 
            borderRadius: '6px', 
            marginBottom: '16px',
            fontSize: '14px'
          }}>
            <strong>Experiment:</strong> {selectedExperiment.name}
            {selectedExperiment.description && (
              <>
                <br />
                <strong>Description:</strong> {selectedExperiment.description}
              </>
            )}
          </div>
        )}

        {(isPromotionFromRevision && parentRevision) && (
          <div style={{ 
            background: '#065f46', 
            padding: '12px', 
            borderRadius: '6px', 
            marginBottom: '16px',
            fontSize: '14px'
          }}>
            <strong>🔄 Promoting from Revision:</strong> v{parentRevision.version} - {parentRevision.name}
            <br />
            <strong>Description:</strong> {parentRevision.description || 'No description'}
          </div>
        )}

        {(isPromotionFromRun && parentRun && parentRevision) && (
          <div style={{
            background: '#065f46',
            padding: '12px',
            borderRadius: '6px',
            marginBottom: '16px',
            fontSize: '14px'
          }}>
            <strong>🚀 Promoting from Run:</strong> {parentRun._id.slice(-8)}
            <br />
            <strong>Base revision:</strong> v{parentRevision.version} - {parentRevision.name}
            <br />
            <strong>Status:</strong> {parentRun.status}
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

        <form onSubmit={createRevision}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                Experiment *
              </label>
              <select
                className="input"
                value={form.experiment_id}
                onChange={e => setForm({...form, experiment_id: e.target.value})}
                disabled={isPromotionFromRevision || isPromotionFromRun}
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
                Unity Environment *
              </label>
              <select
                className="input"
                value={form.environment_id}
                onChange={e => setForm({...form, environment_id: e.target.value})}
                required
              >
                <option value="">Select an environment</option>
                {environments.map(env => (
                  <option key={env._id} value={env._id}>
                    {env.name} (v{env.version})
                  </option>
                ))}
              </select>
              {environments.length === 0 && (
                <small style={{ color: '#f59e0b' }}>
                  No environments registered. <Link href="/environments">Create one here</Link>
                </small>
              )}
            </div>
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
              Revision Name *
            </label>
            <input
              className="input"
              value={form.name}
              onChange={e => setForm({...form, name: e.target.value})}
              placeholder="Descriptive name for this revision"
              required
            />
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
              placeholder="Describe the changes or features of this revision"
            />
          </div>



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
              height={yamlExpanded ? `${Math.max(600, form.yaml.split('\n').length * 18)}px` : "400px"}
              required
            />
            <small style={{ color: '#9ca3af' }}>
              Complete ML-Agents training configuration
            </small>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
              Default CLI Flags
            </label>
            <CLIFlagsEditor
              value={form.cli_flags}
              onChange={value => setForm({...form, cli_flags: value})}
            />
            <small style={{ color: '#9ca3af', display: 'block', marginTop: '8px' }}>
              Default flags for runs based on this revision
            </small>
          </div>

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <Link href="/revisions" className="btn" style={{ border: '1px solid #6b7280' }}>
              Cancel
            </Link>
            <button
              className="btn"
              type="submit"
              disabled={loading}
              style={{ border: loading ? '1px solid #6b7280' : '1px solid #10b981' }}
            >
              {loading ? 'Creating...' : 'Create Revision'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

export default function NewRevision() {
  return (
    <Suspense fallback={<div className="card">Loading...</div>}>
      <NewRevisionForm />
    </Suspense>
  );
}