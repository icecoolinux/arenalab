'use client';
import { useState, useEffect, useCallback, useRef } from 'react';

export default function CLIFlagsEditor({ value, onChange }) {
  const [flags, setFlags] = useState({
    time_scale: 20,
    no_graphics: true,
    num_envs: 1,
    seed: -1,
    torch_device: 'auto',
    width: 84,
    height: 84,
    quality_level: 5
  });

  const [customParams, setCustomParams] = useState([]);

  const [expandedSections, setExpandedSections] = useState({
    environment: false,
    rendering: false,
    advanced: false,
    custom: false
  });

  const [initialized, setInitialized] = useState(false);
  const onChangeRef = useRef(onChange);

  // Update the ref when onChange changes
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Parse JSON value on mount and when value changes
  useEffect(() => {
    if (value && typeof value === 'string') {
      try {
        const parsed = JSON.parse(value);
        const knownFlags = {
          time_scale: parsed.time_scale || 20,
          no_graphics: parsed.no_graphics ?? true,
          num_envs: parsed.num_envs || 1,
          seed: parsed.seed ?? -1,
          torch_device: parsed.torch_device || 'auto',
          width: parsed.width || 84,
          height: parsed.height || 84,
          quality_level: parsed.quality_level || 5
        };
        setFlags(knownFlags);
        
        // Extract custom parameters
        const customKeys = Object.keys(parsed).filter(key => !Object.keys(knownFlags).includes(key));
        const customParamsData = customKeys.map(key => ({ name: key, value: String(parsed[key]) }));
        setCustomParams(customParamsData);
        
        setInitialized(true);
      } catch (e) {
        console.warn('Invalid JSON in CLI flags:', e);
        setInitialized(true);
      }
    } else {
      setInitialized(true);
    }
  }, [value]);

  // Update parent when flags or custom params change (only after initialization)
  useEffect(() => {
    if (initialized && onChangeRef.current) {
      const allParams = { ...flags };
      customParams.forEach(param => {
        if (param.name && param.value !== '') {
          // Try to parse as number if possible, otherwise keep as string
          const numValue = Number(param.value);
          allParams[param.name] = !isNaN(numValue) && param.value !== '' ? numValue : param.value;
        }
      });
      const jsonValue = JSON.stringify(allParams, null, 2);
      onChangeRef.current(jsonValue);
    }
  }, [flags, customParams, initialized]);

  const updateFlag = (key, value) => {
    setFlags(prev => ({ ...prev, [key]: value }));
  };

  const addCustomParam = () => {
    setCustomParams(prev => [...prev, { name: '', value: '' }]);
  };

  const updateCustomParam = (index, field, value) => {
    setCustomParams(prev => prev.map((param, i) => 
      i === index ? { ...param, [field]: value } : param
    ));
  };

  const removeCustomParam = (index) => {
    setCustomParams(prev => prev.filter((_, i) => i !== index));
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const InputField = ({ label, value, onChange, type = "number", min, max, step = 1 }) => (
    <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '12px' }}>
      <label style={{ fontSize: '14px', fontWeight: '500', minWidth: '140px', flex: '0 0 auto' }}>
        {label}
      </label>
      <input
        className="input"
        type={type}
        value={value}
        onChange={e => onChange(type === 'number' ? Number(e.target.value) : e.target.value)}
        min={min}
        max={max}
        step={step}
        style={{ fontSize: '14px', flex: '0 0 100px', width: '100px' }}
      />
    </div>
  );

  const ToggleField = ({ label, value, onChange, description }) => (
    <div style={{ marginBottom: '12px' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={value}
          onChange={e => onChange(e.target.checked)}
          style={{ transform: 'scale(1.2)' }}
        />
        <span style={{ fontSize: '14px', fontWeight: '500' }}>{label}</span>
      </label>
      {description && (
        <small style={{ color: '#9ca3af', display: 'block', marginTop: '2px' }}>
          {description}
        </small>
      )}
    </div>
  );

  const SectionHeader = ({ title, isExpanded, onToggle, icon }) => (
    <div
      onClick={onToggle}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '8px 12px',
        background: '#374151',
        borderRadius: '6px',
        cursor: 'pointer',
        marginBottom: '8px',
        fontSize: '14px',
        fontWeight: '600'
      }}
    >
      <span>{icon}</span>
      <span>{title}</span>
      <span style={{ marginLeft: 'auto', transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
        ▶
      </span>
    </div>
  );

  return (
    <div style={{ border: '1px solid #374151', borderRadius: '8px', padding: '16px', background: '#1f2937' }}>

      {/* Environment Parameters */}
      <SectionHeader
        title="Environment Parameters"
        icon="🌍"
        isExpanded={expandedSections.environment}
        onToggle={() => toggleSection('environment')}
      />

      {expandedSections.environment && (
        <div style={{ marginBottom: '16px', paddingLeft: '12px' }}>
          <InputField
            label="Time Scale"
            value={flags.time_scale}
            onChange={value => updateFlag('time_scale', value)}
            min={1}
            max={100}
          />

          <InputField
            label="Number of Environments"
            value={flags.num_envs}
            onChange={value => updateFlag('num_envs', value)}
            min={1}
            max={64}
          />

          <InputField
            label="Random Seed"
            value={flags.seed}
            onChange={value => updateFlag('seed', value)}
            min={-1}
            max={999999}
          />
        </div>
      )}

      {/* Rendering Parameters */}
      <SectionHeader
        title="Rendering Parameters"
        icon="🎨"
        isExpanded={expandedSections.rendering}
        onToggle={() => toggleSection('rendering')}
      />

      {expandedSections.rendering && (
        <div style={{ marginBottom: '16px', paddingLeft: '12px' }}>
          <ToggleField
            label="No Graphics"
            value={flags.no_graphics}
            onChange={value => updateFlag('no_graphics', value)}
            description="Run without graphical interface for better performance"
          />

          <InputField
            label="Width"
            value={flags.width}
            onChange={value => updateFlag('width', value)}
            min={64}
            max={1920}
          />

          <InputField
            label="Height"
            value={flags.height}
            onChange={value => updateFlag('height', value)}
            min={64}
            max={1080}
          />

          <InputField
            label="Quality Level"
            value={flags.quality_level}
            onChange={value => updateFlag('quality_level', value)}
            min={0}
            max={5}
          />
        </div>
      )}

      {/* Custom Parameters */}
      <SectionHeader
        title="Custom"
        icon="🔧"
        isExpanded={expandedSections.custom}
        onToggle={() => toggleSection('custom')}
      />
      
      {expandedSections.custom && (
        <div style={{ marginBottom: '16px', paddingLeft: '12px' }}>
          <div style={{ marginBottom: '12px' }}>
            <button
              type="button"
              onClick={addCustomParam}
              style={{
                background: '#059669',
                color: 'white',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '4px',
                fontSize: '14px',
                cursor: 'pointer'
              }}
            >
              + Add Parameter
            </button>
          </div>
          
          {customParams.map((param, index) => (
            <div key={index} style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              marginBottom: '8px',
              padding: '8px',
              background: '#374151',
              borderRadius: '4px'
            }}>
              <input
                className="input"
                placeholder="Name"
                value={param.name}
                onChange={e => updateCustomParam(index, 'name', e.target.value)}
                style={{ fontSize: '14px', flex: '1' }}
              />
              <input
                className="input"
                placeholder="Value"
                value={param.value}
                onChange={e => updateCustomParam(index, 'value', e.target.value)}
                style={{ fontSize: '14px', flex: '1' }}
              />
              <button
                type="button"
                onClick={() => removeCustomParam(index)}
                style={{
                  background: '#dc2626',
                  color: 'white',
                  border: 'none',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  cursor: 'pointer'
                }}
              >
                ✕
              </button>
            </div>
          ))}
          
          {customParams.length === 0 && (
            <p style={{ color: '#9ca3af', fontSize: '14px', fontStyle: 'italic' }}>
              No custom parameters. Click &quot;Add Parameter&quot; to add one.
            </p>
          )}
        </div>
      )}

      {/* Advanced Parameters */}
      <SectionHeader
        title="Advanced Parameters"
        icon="⚙️"
        isExpanded={expandedSections.advanced}
        onToggle={() => toggleSection('advanced')}
      />

      {expandedSections.advanced && (
        <div style={{ marginBottom: '16px', paddingLeft: '12px' }}>
          <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label style={{ fontSize: '14px', fontWeight: '500', minWidth: '140px', flex: '0 0 auto' }}>
              Torch Device
            </label>
            <select
              className="input"
              value={flags.torch_device}
              onChange={e => updateFlag('torch_device', e.target.value)}
              style={{ fontSize: '14px', flex: '0 0 100px', width: '100px' }}
            >
              <option value="auto">Auto</option>
              <option value="cpu">CPU</option>
              <option value="cuda">CUDA</option>
            </select>
          </div>
        </div>
      )}

      {/* JSON Output */}
      <div style={{
        background: '#0b0f14',
        border: '1px solid #374151',
        borderRadius: '6px',
        padding: '12px',
        fontSize: '12px',
        fontFamily: 'monospace',
        marginTop: '16px'
      }}>
        <strong>JSON Output:</strong>
        <pre style={{ margin: '8px 0 0 0', whiteSpace: 'pre-wrap' }}>
          {JSON.stringify({
            ...flags,
            ...Object.fromEntries(
              customParams
                .filter(p => p.name && p.value !== '')
                .map(p => {
                  const numValue = Number(p.value);
                  return [p.name, !isNaN(numValue) && p.value !== '' ? numValue : p.value];
                })
            )
          }, null, 2)}
        </pre>
      </div>
    </div>
  );
}