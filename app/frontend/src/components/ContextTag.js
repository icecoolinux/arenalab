'use client';

export default function ContextTag({ type, label, id }) {
  const getTagStyle = (type) => {
    switch (type) {
      case 'experiment':
        return {
          background: '#2563eb',
          color: 'white',
          icon: '🧪'
        };
      case 'revision':
        return {
          background: '#7c3aed',
          color: 'white',
          icon: '📝'
        };
      case 'run':
        return {
          background: '#059669',
          color: 'white',
          icon: '🚀'
        };
      default:
        return {
          background: '#6b7280',
          color: 'white',
          icon: '📋'
        };
    }
  };

  const style = getTagStyle(type);

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        background: style.background,
        color: style.color,
        padding: '4px 8px',
        borderRadius: '6px',
        fontSize: '12px',
        fontWeight: '600',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        fontFamily: 'monospace'
      }}
    >
      <span>{style.icon}</span>
      <span>{label}</span>
      {id && (
        <span style={{ 
          opacity: 0.8, 
          fontSize: '10px',
          marginLeft: '2px'
        }}>
          {id}
        </span>
      )}
    </span>
  );
}