import { useState } from 'react';
import {
  Box, Grid, Typography, Checkbox, TextField, MenuItem, Button, Stack, Chip,
} from '@mui/material';
import api from '../../api.js';
import RulesPopover from './RulesPopover.jsx';
import RGPopover from './RGPopover.jsx';
import PreviewPopover from './PreviewPopover.jsx';

const MODES = ['Clean', 'Replace', 'Extract', 'Validate', 'Case', 'Length'];
const CASES = ['UPPERCASE', 'lowercase', 'Title Case'];
const LENGTH_MODES = ['Exact', 'Minimum', 'Maximum', 'Range'];

export default function ColumnRow({ row, onConfigChange, onRefresh }) {
  const { column, sample, config, rule_count: ruleCount } = row;
  const [showRules, setShowRules] = useState(false);
  const [showRG, setShowRG] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const enabled = !!config.enabled;

  const patch = async (changes) => {
    try {
      await api.put(`/quality/config/${encodeURIComponent(column)}`, changes);
      onConfigChange?.(column, { ...config, ...changes });
    } catch (e) { /* ignore */ }
  };

  const save = async () => {
    await api.post(`/quality/save-rule/${encodeURIComponent(column)}`);
    onRefresh?.();
  };

  const run = async () => {
    await api.post(`/quality/apply-column/${encodeURIComponent(column)}`);
    onRefresh?.();
  };

  const editRule = async (idx) => {
    await api.post(`/quality/edit-rule/${encodeURIComponent(column)}/${idx}`);
    setShowRules(false);
    onRefresh?.();
  };

  const delRule = async (idx) => {
    await api.delete(`/quality/applied-rule/${encodeURIComponent(column)}/${idx}`);
    onRefresh?.();
  };

  return (
    <>
      <Grid container alignItems="center" spacing={1} sx={{
        py: 1.25,
        borderBottom: '1px solid',
        borderColor: 'divider',
        '&:hover': { bgcolor: 'action.hover' },
      }}>
        {/* On */}
        <Grid item xs={6} sm={1}>
          <Checkbox checked={enabled} onChange={(e) => patch({ enabled: e.target.checked })} size="small" />
        </Grid>
        {/* Column */}
        <Grid item xs={6} sm={2}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>{column}</Typography>
        </Grid>
        {/* Values */}
        <Grid item xs={12} sm={2}>
          <Typography variant="caption" color="text.secondary"
                      sx={{ fontFamily: 'monospace', fontSize: '0.72rem' }}>{sample}</Typography>
        </Grid>
        {/* Rules + RG */}
        <Grid item xs={12} sm={2}>
          <Stack direction="row" spacing={0.5}>
            <Button size="small" variant="outlined" disabled={ruleCount === 0}
              onClick={() => setShowRules(true)} sx={{ minWidth: 0, flex: 1 }}>
              {ruleCount > 0 ? `${ruleCount} rules` : 'No rules'}
            </Button>
            <Button size="small" variant="outlined" onClick={() => setShowRG(true)}
              sx={{ minWidth: 0 }}>RG</Button>
          </Stack>
        </Grid>
        {/* Mode */}
        <Grid item xs={6} sm={1}>
          <TextField select size="small" disabled={!enabled} fullWidth
            value={config.mode} onChange={(e) => patch({ mode: e.target.value })}
            SelectProps={{ MenuProps: { PaperProps: { sx: { maxHeight: 300 } } } }}>
            {MODES.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
          </TextField>
        </Grid>
        {/* Configuration */}
        <Grid item xs={6} sm={2}>
          {(['Clean', 'Replace', 'Extract', 'Validate'].includes(config.mode)) && (
            <Stack spacing={0.5}>
              <TextField size="small" disabled={!enabled} placeholder="Regex"
                value={config.pattern} onChange={(e) => patch({ pattern: e.target.value })} fullWidth />
              {config.mode === 'Replace' && (
                <TextField size="small" disabled={!enabled} placeholder="Text"
                  value={config.replace} onChange={(e) => patch({ replace: e.target.value })} fullWidth />
              )}
            </Stack>
          )}
          {config.mode === 'Case' && (
            <TextField select size="small" disabled={!enabled} fullWidth
              value={config.case} onChange={(e) => patch({ case: e.target.value })}>
              {CASES.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </TextField>
          )}
          {config.mode === 'Length' && (
            <Stack spacing={0.5}>
              <TextField select size="small" disabled={!enabled} fullWidth
                value={config.length_mode} onChange={(e) => patch({ length_mode: e.target.value })}>
                {LENGTH_MODES.map((l) => <MenuItem key={l} value={l}>{l}</MenuItem>)}
              </TextField>
              {config.length_mode === 'Exact' && (
                <TextField size="small" type="number" disabled={!enabled}
                  value={config.exact_length}
                  onChange={(e) => patch({ exact_length: parseInt(e.target.value || '0', 10) })}
                  inputProps={{ min: 1 }} fullWidth />
              )}
              {config.length_mode === 'Minimum' && (
                <TextField size="small" type="number" disabled={!enabled}
                  value={config.min_length}
                  onChange={(e) => patch({ min_length: parseInt(e.target.value || '0', 10) })}
                  inputProps={{ min: 0 }} fullWidth />
              )}
              {config.length_mode === 'Maximum' && (
                <TextField size="small" type="number" disabled={!enabled}
                  value={config.max_length}
                  onChange={(e) => patch({ max_length: parseInt(e.target.value || '1', 10) })}
                  inputProps={{ min: 1 }} fullWidth />
              )}
              {config.length_mode === 'Range' && (
                <Stack direction="row" spacing={0.5}>
                  <TextField size="small" type="number" disabled={!enabled} placeholder="Min"
                    value={config.min_length}
                    onChange={(e) => patch({ min_length: parseInt(e.target.value || '0', 10) })}
                    inputProps={{ min: 0 }} sx={{ flex: 1 }} />
                  <TextField size="small" type="number" disabled={!enabled} placeholder="Max"
                    value={config.max_length}
                    onChange={(e) => patch({ max_length: parseInt(e.target.value || '1', 10) })}
                    inputProps={{ min: 1 }} sx={{ flex: 1 }} />
                </Stack>
              )}
            </Stack>
          )}
        </Grid>
        {/* Preview */}
        <Grid item xs={4} sm={1}>
          <Button size="small" variant="outlined" fullWidth disabled={!enabled}
            onClick={() => setShowPreview(true)}>Preview</Button>
        </Grid>
        {/* Save */}
        <Grid item xs={4} sm={0.5} sx={{ minWidth: 60 }}>
          <Button size="small" variant="contained" fullWidth disabled={!enabled} onClick={save}>Save</Button>
        </Grid>
        {/* Run */}
        <Grid item xs={4} sm={0.5} sx={{ minWidth: 60 }}>
          <Button size="small" variant="contained" color="success" fullWidth
            disabled={!enabled || ruleCount === 0} onClick={run}>Run</Button>
        </Grid>
      </Grid>

      <RulesPopover open={showRules} onClose={() => setShowRules(false)}
        column={column} rules={config.applied_rules || []} onEdit={editRule} onDelete={delRule} />
      <RGPopover open={showRG} onClose={() => setShowRG(false)} column={column}
        onAdded={() => onRefresh?.()} />
      <PreviewPopover open={showPreview} onClose={() => setShowPreview(false)} column={column} />
    </>
  );
}
