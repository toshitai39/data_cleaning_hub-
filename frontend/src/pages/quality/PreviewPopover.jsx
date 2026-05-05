import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Alert, Chip,
} from '@mui/material';
import api from '../../api.js';

export default function PreviewPopover({ open, onClose, column }) {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!open) return;
    setErr(''); setRows(null);
    api.post('/quality/preview', { column })
      .then((r) => setRows(r.data.rows))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'));
  }, [open, column]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Preview — {column}</DialogTitle>
      <DialogContent>
        {err && <Alert severity="error">{err}</Alert>}
        {rows && rows.length === 0 && <Alert severity="info">Configure first</Alert>}
        {rows && rows.length > 0 && (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Before</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>After</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{r.Before}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{r.After}</TableCell>
                    <TableCell>
                      <Chip size="small" label={r.Status}
                        color={r.Status === 'Rejected' ? 'error' : 'success'} variant="outlined" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
