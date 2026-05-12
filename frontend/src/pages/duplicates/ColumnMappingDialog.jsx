import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
  Box, Typography, Stack, Alert, MenuItem, TextField,
} from '@mui/material';
import LinkOutlinedIcon from '@mui/icons-material/LinkOutlined';

/**
 * Pops up when a library scan returns ``missing_columns``. The rule
 * expects e.g. ``country`` but the dataset uses ``entity_country_code`` —
 * this dialog lets the user pick which actual column plays which role.
 *
 * Props:
 *   open                 boolean
 *   onClose              () => void
 *   onConfirm(mapping)   user submitted — { ruleCol: datasetCol }
 *   ruleLabel            human-readable rule label
 *   ruleColumns          list of column names the rule expects
 *   missingColumns       subset of ruleColumns that aren't in the dataset
 *   availableColumns     all columns in the current dataset
 *   suggestedMapping     server-side best-guess pre-fill
 */
export default function ColumnMappingDialog({
  open,
  onClose,
  onConfirm,
  ruleLabel,
  ruleColumns = [],
  missingColumns = [],
  availableColumns = [],
  suggestedMapping = {},
}) {
  const [mapping, setMapping] = useState({});

  useEffect(() => {
    if (open) {
      const initial = {};
      for (const c of ruleColumns) {
        initial[c] = suggestedMapping[c] || (availableColumns.includes(c) ? c : '');
      }
      setMapping(initial);
    }
  }, [open, ruleColumns, suggestedMapping, availableColumns]);

  const setOne = (ruleCol, value) =>
    setMapping((m) => ({ ...m, [ruleCol]: value }));

  const allMapped = ruleColumns.every((c) => mapping[c]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1.25}>
          <LinkOutlinedIcon sx={{ color: '#6A28A8' }} />
          <Typography sx={{ fontFamily: "'Montserrat', sans-serif", fontWeight: 700, fontSize: 18 }}>
            Map rule columns to your dataset
          </Typography>
        </Stack>
        <Typography sx={{ fontSize: 12.5, color: '#8A8A8A', mt: 0.5 }}>
          {ruleLabel ? `Rule: ${ruleLabel}` : 'Library rule'}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Alert severity="info" sx={{ mb: 2 }}>
          The rule expects these columns; your dataset uses different names.
          Pick the matching column on your side for each one.
          {' '}
          <b>{missingColumns.length}</b> column{missingColumns.length === 1 ? '' : 's'} need mapping.
        </Alert>

        <Stack spacing={2}>
          {ruleColumns.map((ruleCol) => {
            const isMissing = missingColumns.includes(ruleCol);
            return (
              <Box
                key={ruleCol}
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto 1fr',
                  alignItems: 'center',
                  gap: 1.5,
                  px: 1.5,
                  py: 1.25,
                  border: '1px solid',
                  borderColor: isMissing ? '#FCF3E2' : '#E7E6E6',
                  bgcolor: isMissing ? '#FCFAF1' : '#FBFAFC',
                  borderRadius: 1.25,
                }}
              >
                <Box>
                  <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#8A8A8A', textTransform: 'uppercase' }}>
                    Rule column
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: 'ui-monospace, Menlo, monospace',
                      fontSize: 13,
                      fontWeight: 600,
                      color: '#1A1A1A',
                    }}
                  >
                    {ruleCol}
                  </Typography>
                </Box>
                <Box sx={{ color: '#8A8A8A', fontSize: 18, fontWeight: 700 }}>→</Box>
                <TextField
                  select
                  size="small"
                  value={mapping[ruleCol] || ''}
                  onChange={(e) => setOne(ruleCol, e.target.value)}
                  fullWidth
                  label="Your column"
                >
                  <MenuItem value="">
                    <em>— pick a column —</em>
                  </MenuItem>
                  {availableColumns.map((c) => (
                    <MenuItem key={c} value={c} sx={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
                      {c}
                    </MenuItem>
                  ))}
                </TextField>
              </Box>
            );
          })}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!allMapped}
          onClick={() => onConfirm(mapping)}
        >
          Run with this mapping
        </Button>
      </DialogActions>
    </Dialog>
  );
}
