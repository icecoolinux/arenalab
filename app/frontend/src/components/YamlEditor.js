'use client';
import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import githubDarkCustomTheme from './themes/github_dark_custom';

// Dynamically import AceEditor to avoid SSR issues and configure workers
const AceEditor = dynamic(
  async () => {
    const ace = await import('ace-builds/src-noconflict/ace');

    // Completely disable workers before importing anything else
    ace.default.config.set('workerPath', null);
    ace.default.config.set('loadWorkerFromBlob', false);
    ace.default.config.set('useWorker', false);

    // Import required modules
    await import('ace-builds/src-noconflict/mode-yaml');
    await import('ace-builds/src-noconflict/theme-github_dark');
    await import('ace-builds/src-noconflict/ext-language_tools');

    // Register our custom theme
    ace.define('ace/theme/github_dark_custom', ['require', 'exports', 'module', 'ace/lib/dom'], function(require, exports, module) {
      exports.isDark = githubDarkCustomTheme.isDark;
      exports.cssClass = githubDarkCustomTheme.cssClass;
      exports.cssText = githubDarkCustomTheme.cssText;

      const dom = require('ace/lib/dom');
      dom.importCssString(exports.cssText, exports.cssClass, false);
    });

    const reactAce = await import('react-ace');
    return reactAce.default;
  },
  { ssr: false }
);

export default function YamlEditor({ 
  value, 
  onChange, 
  placeholder = "# YAML Configuration",
  height = "400px",
  required = false,
  readOnly = false 
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Fallback textarea for SSR
    return (
      <textarea 
        className="input" 
        value={value} 
        onChange={e => onChange(e.target.value)}
        rows={20}
        placeholder={placeholder}
        required={required}
        readOnly={readOnly}
        style={{ 
          fontFamily: 'monospace', 
          fontSize: '12px',
          lineHeight: '1.4'
        }}
      />
    );
  }

  return (
    <AceEditor
      mode="yaml"
      theme="github_dark_custom"
      value={value}
      onChange={onChange}
      name="yaml-editor"
      width="100%"
      height={height}
      fontSize="12px"
      showPrintMargin={false}
      showGutter={true}
      highlightActiveLine={!readOnly}
      placeholder={placeholder}
      readOnly={readOnly}
      setOptions={{
        enableBasicAutocompletion: !readOnly,
        enableLiveAutocompletion: false,
        enableSnippets: false,
        showLineNumbers: true,
        tabSize: 2,
        useSoftTabs: true,
        wrap: true,
        foldStyle: 'markbegin'
      }}
      style={{
        border: '1px solid #374151',
        borderRadius: '6px',
        backgroundColor: '#24292e'
      }}
    />
  );
}