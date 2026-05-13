import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Typography, Alert, Button, Divider,
  Accordion, AccordionSummary, AccordionDetails,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TablePagination, TextField, InputAdornment, Chip,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchIcon from '@mui/icons-material/Search';
import TableChartOutlinedIcon from '@mui/icons-material/TableChartOutlined';
import ViewColumnOutlinedIcon from '@mui/icons-material/ViewColumnOutlined';
import api from '../../api.js';
import StatCard from '../../components/StatCard.jsx';
import ContentCard from '../../components/ContentCard.jsx';
import SectionTitle from '../../components/SectionTitle.jsx';
import ColumnsOfInterest from './ColumnsOfInterest.jsx';

export default function DataStatus({ filename, onClearAll, onLoadDifferent }) {
  const [info, setInfo] = useState(null);
  const [preview, setPreview] = useState([]);
  const [columns, setColumns] = useState([]);
  const [summary, setSummary] = useState([]);
  const [qualityScore, setQualityScore] = useState(null);
  const [scope, setScope] = useState({ selected: 0, total: 0, explicit: false });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const refreshScope = () =>
    api
      .get('/data/columns-of-interest')
      .then((r) =>
        setScope({
          selected: (r.data.selected || []).length,
          total: (r.data.all || []).length,
          explicit: !!r.data.explicit,
        }),
      )
      .catch(() => {});

  useEffect(() => {
    Promise.all([
      api.get('/data/file-info').then((r) => setInfo(r.data)).catch(() => {}),
      api.get('/data/preview', { params: { page: 1, page_size: 100 } })
        .then((r) => { setPreview(r.data.rows); setColumns(r.data.columns); })
        .catch(() => {}),
      api.get('/data/column-summary').then((r) => setSummary(r.data)).catch(() => {}),
      api.get('/profile/dashboard').then((r) => setQualityScore(r.data?.quality_score)).catch(() => {}),
      refreshScope(),
    ]);
  }, []);

  const memoryMb = info && info.size_bytes ? (info.size_bytes / 1024 / 1024).toFixed(1) : '0.0';
  const totalRows = info?.rows || 0;
  const totalCols = info?.columns || 0;
  const scopedCols = scope.explicit ? scope.selected : (scope.total || totalCols);
  const scopeIsNarrowed = scope.explicit && scope.selected !== scope.total;

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
      <Alert severity="success" sx={{ mb: 2.5 }}>
        <b>{filename}</b> loaded successfully
      </Alert>

      <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatCard accent label="Rows" value={totalRows.toLocaleString()} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Critical data elements"
            value={scopeIsNarrowed ? `${scopedCols} / ${totalCols}` : totalCols}
            delta={scopeIsNarrowed ? `${totalCols - scopedCols} excluded` : undefined}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Memory" value={`${memoryMb} MB`} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label={qualityScore == null ? 'Status' : 'Quality score'}
            value={qualityScore == null ? 'Ready' : `${qualityScore.toFixed(0)} / 100`}
          />
        </Grid>
      </Grid>

      <ColumnsOfInterest onSaved={refreshScope} />

      <ContentCard sx={{ p: 0, mb: 2.5, overflow: 'hidden' }}>
        <Box
          sx={{
            px: 2.5,
            py: 1.75,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 1.5,
            borderBottom: '1px solid #E7E6E6',
            bgcolor: '#FBFAFC',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TableChartOutlinedIcon sx={{ fontSize: 18, color: '#6A28A8' }} />
            <Box>
              <Typography
                sx={{
                  fontFamily: "'Montserrat', sans-serif",
                  fontSize: 15,
                  fontWeight: 700,
                  color: '#1A1A1A',
                }}
              >
                Data preview
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
                <Chip size="small" label={`First ${preview.length} rows`} variant="outlined" />
                <Chip size="small" label={`${columns.length} columns`} variant="outlined" />
                {search && (
                  <Chip
                    size="small"
                    color="primary"
                    label={`${filteredPreview.length} match${filteredPreview.length === 1 ? '' : 'es'}`}
                  />
                )}
              </Box>
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
                    width: 56,
                    position: 'sticky',
                    left: 0,
                    zIndex: 3,
                  }}
                >
                  #
                </TableCell>
                {columns.map((c) => (
                  <TableCell key={c} sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                    {c}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {pagedPreview.length === 0 && (
                <TableRow>
                  <TableCell colSpan={columns.length + 1} align="center" sx={{ py: 4, color: '#8A8A8A' }}>
                    No rows match the filter.
                  </TableCell>
                </TableRow>
              )}
              {pagedPreview.map((row, i) => {
                const rowIdx = page * rowsPerPage + i;
                return (
                  <TableRow
                    key={rowIdx}
                    sx={{ '&:hover': { bgcolor: '#F7F5FA' } }}
                  >
                    <TableCell
                      sx={{
                        color: '#8A8A8A',
                        fontSize: '0.75rem',
                        fontVariantNumeric: 'tabular-nums',
                        position: 'sticky',
                        left: 0,
                        bgcolor: '#FFFFFF',
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
                            fontFamily: 'ui-monospace, Menlo, monospace',
                            fontSize: '0.78rem',
                            maxWidth: 260,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            color: val == null || display === '' ? '#8A8A8A' : '#1A1A1A',
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
          sx={{ borderTop: '1px solid #E7E6E6' }}
        />
      </ContentCard>

      <ContentCard sx={{ p: 0, mb: 2.5 }}>
        <Accordion
          disableGutters
          elevation={0}
          sx={{
            background: 'transparent',
            border: 'none',
            '&:before': { display: 'none' },
          }}
        >
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{ px: 2.5, py: 1, minHeight: 56 }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <ViewColumnOutlinedIcon sx={{ fontSize: 18, color: '#6A28A8' }} />
              <Typography
                sx={{
                  fontFamily: "'Montserrat', sans-serif",
                  fontSize: 15,
                  fontWeight: 700,
                  color: '#1A1A1A',
                }}
              >
                Critical data element summary
              </Typography>
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0, borderTop: '1px solid #E7E6E6' }}>
            <TableContainer sx={{ maxHeight: 360 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700 }}>Critical data element</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Type</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Non-null</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Null %</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Unique</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {summary.map((r, i) => (
                    <TableRow key={i} sx={{ '&:hover': { bgcolor: '#F7F5FA' } }}>
                      <TableCell sx={{ fontWeight: 500 }}>{r.Column}</TableCell>
                      <TableCell>
                        <Chip size="small" label={r.Type} variant="outlined" />
                      </TableCell>
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
      </ContentCard>

      <Divider sx={{ my: 2.5 }} />
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
