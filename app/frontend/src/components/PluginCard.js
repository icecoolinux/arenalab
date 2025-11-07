'use client';

/**
 * Reusable plugin card component for displaying and configuring plugins.
 * Uses plugin metadata from the backend to avoid hardcoding plugin-specific information.
 */
export default function PluginCard({
  plugin,
  isSelected,
  onToggle,
  pluginSettings = {},
  onSettingChange
}) {
  return (
    <div
      style={{
        border: `2px solid ${isSelected ? '#60a5fa' : '#374151'}`,
        borderRadius: '8px',
        padding: '16px',
        backgroundColor: '#1f2937',
        transition: 'all 0.2s ease',
        cursor: 'pointer'
      }}
      onClick={() => onToggle(plugin.name)}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <input
          type="checkbox"
          id={`plugin-${plugin.name}`}
          checked={isSelected}
          onChange={() => {}}
          style={{
            cursor: 'pointer',
            width: '18px',
            height: '18px',
            flexShrink: 0
          }}
        />
        <div style={{ flex: 1 }} onClick={(e) => e.stopPropagation()}>
          <label
            htmlFor={`plugin-${plugin.name}`}
            style={{
              fontWeight: '600',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '15px',
              color: isSelected ? '#93c5fd' : '#e5e7eb'
            }}
          >
            <span style={{ fontSize: '18px' }}>
              {plugin.icon || '⚙️'}
            </span>
            {plugin.name}
          </label>
          <p style={{
            margin: '6px 0 0 0',
            fontSize: '13px',
            color: '#9ca3af',
            lineHeight: '1.5'
          }}>
            {plugin.description}
          </p>

          {isSelected && plugin.settings_schema && Object.keys(plugin.settings_schema).length > 0 && (
            <div style={{
              marginTop: '16px',
              padding: '14px',
              backgroundColor: '#111827',
              borderRadius: '6px',
              border: '1px solid #374151'
            }}>
              <div style={{
                fontWeight: '600',
                marginBottom: '12px',
                fontSize: '13px',
                color: '#e5e7eb',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <span>⚙️</span> Configuration
              </div>
              <div style={{ display: 'grid', gap: '12px' }}>
                {Object.entries(plugin.settings_schema).map(([key, spec]) => (
                  <div key={key}>
                    {spec.type === 'boolean' ? (
                      // Boolean inputs: checkbox inline with label
                      <>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                          <input
                            type="checkbox"
                            id={`setting-${plugin.name}-${key}`}
                            checked={pluginSettings[key] ?? spec.default ?? false}
                            onChange={e => onSettingChange(key, e.target.checked)}
                            style={{
                              cursor: 'pointer',
                              width: '16px',
                              height: '16px',
                              marginTop: '2px',
                              flexShrink: 0
                            }}
                          />
                          <label
                            htmlFor={`setting-${plugin.name}-${key}`}
                            style={{
                              fontSize: '12px',
                              color: '#d1d5db',
                              fontWeight: '500',
                              cursor: 'pointer',
                              flex: 1
                            }}
                          >
                            {spec.label || key}
                            {spec.default !== undefined && (
                              <span style={{ color: '#6b7280', fontWeight: 'normal' }}>
                                {' '}(default: {String(spec.default)})
                              </span>
                            )}
                          </label>
                        </div>
                        {spec.description && (
                          <p style={{
                            fontSize: '11px',
                            color: '#6b7280',
                            marginTop: '4px',
                            marginBottom: '0',
                            marginLeft: '24px',
                            lineHeight: '1.4'
                          }}>
                            {spec.description}
                          </p>
                        )}
                      </>
                    ) : (
                      // Other input types: label above input
                      <>
                        <label style={{
                          display: 'block',
                          fontSize: '12px',
                          color: '#d1d5db',
                          marginBottom: '6px',
                          fontWeight: '500'
                        }}>
                          {spec.label || key}
                          {spec.default !== undefined && (
                            <span style={{ color: '#6b7280', fontWeight: 'normal' }}>
                              {' '}(default: {String(spec.default)})
                            </span>
                          )}
                        </label>
                        {spec.description && (
                          <p style={{
                            fontSize: '11px',
                            color: '#6b7280',
                            marginBottom: '6px',
                            marginTop: '-3px',
                            lineHeight: '1.4'
                          }}>
                            {spec.description}
                          </p>
                        )}
                        {spec.type === 'int' || spec.type === 'float' ? (
                          <input
                            type="number"
                            className="input"
                            value={pluginSettings[key] ?? spec.default ?? ''}
                            onChange={e => onSettingChange(key,
                              spec.type === 'int' ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0
                            )}
                            min={spec.min}
                            max={spec.max}
                            style={{
                              fontSize: '13px',
                              padding: '8px',
                              maxWidth: '200px'
                            }}
                          />
                        ) : (
                          <input
                            type="text"
                            className="input"
                            value={pluginSettings[key] ?? spec.default ?? ''}
                            onChange={e => onSettingChange(key, e.target.value)}
                            style={{
                              fontSize: '13px',
                              padding: '8px'
                            }}
                          />
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
