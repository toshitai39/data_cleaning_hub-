import { useEffect, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Alert, Button, Stack,
  Accordion, AccordionSummary, AccordionDetails,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Divider,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';

function MetricCard({ label, value }) {
  return (
    <Paper sx={{ p: 2, textAlign: 'center' }}>
      <Typography variant="caption" color="text.secondary"
        sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Typography>
      <Typography variant="h6" sx={{ fontWeight: 700, color: 'primary.main' }}>{value}</Typography>
    </Paper>
  );
}

export default function DataStatus({ filename, onClearAll, onLoadDifferent }) {
  const [info, setInfo] = useState(null);
  const [preview, setPreview] = useState([]);
  const [columns, setColumns] = useState([]);
  const [summary, setSummary] = useState([]);
  const [qualityScore, setQualityScore] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/data/file-info').then((r) => setInfo(r.data)).catch(() => {}),
      api.get('/data/preview', { params: { page: 1, page_size: 100 } })
        .then((r) => { setPreview(r.data.rows); setColumns(r.data.columns); })
        .catch(() => {}),
      api.get('/data/column-summary').then((r) => setSummary(r.data)).catch(() => {}),
      api.get('/profile/dashboard').then((r) => setQualityScore(r.data?.quality_score)).catch(() => {}),
    ]);
  }, []);

  const memoryMb = info && info.size_bytes ? (info.size_bytes / 1024 / 1024).toFixed(1) : '0.0';
  const rows = info?.rows || 0;
  const cols = info?.columns || 0;

  return (
    <Box>
      <Alert severity="success" sx={{ mb: 2 }}>
        <b>{filename}</b> loaded successfully
      </Alert>

      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}><MetricCard label="Rows" value={rows.toLocaleString()} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Columns" value={cols} /></Grid>
        <Grid item xs={6} md={3}><MetricCard label="Memory" value={`${memoryMb} MB`} /></Grid>
        <Grid item xs={6} md={3}>
          <MetricCard label={qualityScore == null ? 'Status' : 'Quality Score'}
            value={qualityScore == null ? 'Ready' : `${qualityScore.toFixed(0)}/100`} />
        </Grid>
      </Grid>

      <Alert severity="success" sx={{ mb: 2 }}>
        Data is ready. Explore other tabs for analysis.
      </Alert>

      <Accordion sx={{ mb: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Data Preview (First 100 rows)</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 300 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {columns.map((c) => (
                    <TableCell key={c} sx={{ fontWeight: 600 }}>{c}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {preview.map((row, i) => (
                  <TableRow key={i}>
                    {columns.map((c) => (
                      <TableCell key={c} sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                        {row[c] == null ? '' : String(row[c])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Column Summary</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Column</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Non-Null</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Null %</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Unique</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {summary.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell>{r.Column}</TableCell>
                    <TableCell>{r.Type}</TableCell>
                    <TableCell>{r['Non-Null']}</TableCell>
                    <TableCell>{r['Null %']}</TableCell>
                    <TableCell>{r.Unique}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </AccordionDetails>
      </Accordion>

      <Divider sx={{ my: 2 }} />
      <Grid container spacing={1.5}>
        <Grid item xs={12} sm={6}>
          <Button fullWidth variant="outlined" onClick={onLoadDifferent}>Load Different File</Button>
        </Grid>
        <Grid item xs={12} sm={6}>
          <Button fullWidth variant="outlined" color="error" onClick={onClearAll}>Clear All Data</Button>
        </Grid>
      </Grid>
    </Box>
  );
}
