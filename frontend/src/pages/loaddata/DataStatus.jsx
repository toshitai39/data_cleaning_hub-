import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Paper, Typography, Alert, Button, Divider,
  Accordion, AccordionSummary, AccordionDetails,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TablePagination, TextField, InputAdornment, Chip,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import api from '../../api.js';
import ColumnsOfInterest from './ColumnsOfInterest.jsx';

function MetricCard({ label, value }) {
  return (
    <Paper sx={{ p: 2, textAlign: 'center' }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textTransform: 'uppercase', letterSpacing: 0.6 }}
      >
        {label}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 700, color: 'primary.main' }}>
        {value}
      </Typography>
    </Paper>
  );
}

export default function DataStatus({ filename, onClearAll, onLoadDifferent }) {
  const [info, setInfo] = useState(null);
  const [preview, setPreview] = useState([]);
  const [columns, setColumns] = useState([]);
  const [summary, setSummary] = useState([]);
  const [qualityScore, setQualityScore] = useState(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

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
  const totalRows = info?.rows || 0;
  const totalCols = info?.columns || 0;

  const filteredPreview = useMemo(() => {
    if (!search.trim()) return preview;
    const q = search.toLowerCase();
    return preview.filter((row) =>
      columns.some((c) => String(row[c] ?? '').toLowerCase().includes(q)),
    );
  }, [preview, columns, search]);

  const pagedPreview = useMemo(
    () => filteredPreview.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage),
    [filteredPreview, page, rowsPerPage],
  );

  return (
    <Box>
      <Alert severity="success" sx={{ mb: 2 }}>
        <b>{filename}</b> loaded successfully
      </Alert>

      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>
          <MetricCard label="Rows" value={totalRows.toLocaleString()} />
        </Grid>
        <Grid item xs={6} md={3}>
          <MetricCard label="Columns" value={totalCols} />
        </Grid>
        <Grid item xs={6} md={3}>
          <MetricCard label="Memory" value={`${memoryMb} MB`} />
        </Grid>
        <Grid item xs={6} md={3}>
          <MetricCard
            label={qualityScore == null ? 'Status' : 'Quality score'}
            value={qualityScore == null ? 'Ready' : `${qualityScore.toFixed(0)}/100`}
          />
        </Grid>
      </Grid>

      <ColumnsOfInterest />

      <Paper variant="outlined" sx={{ mb: 2, overflow: 'hidden' }}>
        <Box
          sx={{
            px: 2,
            py: 1.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 1.5,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: 'rgba(91,26,120,0.03)',
          }}
        >
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              Data preview
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
              <Chip size="small" label={`First ${preview.length} rows`} />
              <Chip size="small" label={`${columns.length} columns`} />
              {search && (
                <Chip
                  size="small"
                  color="primary"
                  label={`${filteredPreview.length} match${filteredPreview.length === 1 ? '' : 'es'}`}
                />
              )}
            </Box>
          </Box>
          <TextField
            size="small"
            placeholder="Filter rows…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
            sx={{ minWidth: 260 }}
          />
        </Box>
        <TableContainer sx={{ maxHeight: 520 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell
                  sx={{
                    fontWeight: 700,
                    bgcolor: 'rgba(91,26,120,0.06)',
                    width: 56,
                    position: 'sticky',
                    left: 0,
                    zIndex: 3,
                  }}
                >
                  #
                </TableCell>
                {columns.map((c) => (
                  <TableCell
                    key={c}
                    sx={{
                      fontWeight: 700,
                      bgcolor: 'rgba(91,26,120,0.06)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {c}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {pagedPreview.length === 0 && (
                <TableRow>
                  <TableCell colSpan={columns.length + 1} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    No rows match the filter.
                  </TableCell>
                </TableRow>
              )}
              {pagedPreview.map((row, i) => {
                const rowIdx = page * rowsPerPage + i;
                return (
                  <TableRow key={rowIdx} hover>
                    <TableCell
                      sx={{
                        color: 'text.secondary',
                        fontSize: '0.75rem',
                        position: 'sticky',
                        left: 0,
                        bgcolor: 'background.paper',
                      }}
                    >
                      {rowIdx + 1}
                    </TableCell>
                    {columns.map((c) => {
                      const val = row[c];
                      const display = val == null ? '' : String(val);
                      return (
                        <TableCell
                          key={c}
                          title={display}
                          sx={{
                            fontFamily: 'monospace',
                            fontSize: '0.78rem',
                            maxWidth: 260,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            color: val == null || display === '' ? 'text.disabled' : 'text.primary',
                          }}
                        >
                          {display === '' ? '—' : display}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={filteredPreview.length}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => { setRowsPerPage(Number(e.target.value)); setPage(0); }}
          rowsPerPageOptions={[10, 25, 50, 100]}
        />
      </Paper>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography>Column summary</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Column</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Non-null</TableCell>
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
          <Button fullWidth variant="outlined" onClick={onLoadDifferent}>Load different file</Button>
        </Grid>
        <Grid item xs={12} sm={6}>
          <Button fullWidth variant="outlined" color="error" onClick={onClearAll}>Clear all data</Button>
        </Grid>
      </Grid>
    </Box>
  );
}
