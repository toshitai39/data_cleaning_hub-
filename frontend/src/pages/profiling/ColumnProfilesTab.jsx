import { useEffect, useMemo, useState } from 'react';
import {
  Box, Grid, Stack, TextField, MenuItem, Typography, Accordion,
  AccordionSummary, AccordionDetails, LinearProgress, Alert,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';

const RISK_DOT = { Low: '🟢', Medium: '🟡', High: '🔴' };

export default function ColumnProfilesTab() {
  const [cols, setCols] = useState(null);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');
  const [dtypeFilter, setDtypeFilter] = useState('All');
  const [sortBy, setSortBy] = useState('Name');

  useEffect(() => {
    api.get('/profile/columns')
      .then((r) => setCols(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'));
  }, []);

  const filtered = useMemo(() => {
    if (!cols) return [];
    let out = cols;
    if (search) {
      const q = search.toLowerCase();
      out = out.filter((c) => c.column.toLowerCase().includes(q));
    }
    if (dtypeFilter === 'Numeric') {
      out = out.filter((c) => /int|float/.test(c.dtype));
    } else if (dtypeFilter === 'Text') {
      out = out.filter((c) => c.dtype === 'object');
    } else if (dtypeFilter === 'Date') {
      out = out.filter((c) => /date/.test(c.dtype));
    } else if (dtypeFilter === 'High Risk') {
      out = out.filter((c) => c.risk_level === 'High');
    }
    if (sortBy === 'Null %') out = [...out].sort((a, b) => b.null_percentage - a.null_percentage);
    else if (sortBy === 'Uniqueness') out = [...out].sort((a, b) => b.unique_percentage - a.unique_percentage);
    else if (sortBy === 'Risk') out = [...out].sort((a, b) => b.risk_score - a.risk_score);
    return out;
  }, [cols, search, dtypeFilter, sortBy]);

  if (err) return <Alert severity="error">{err}</Alert>;
  if (!cols) return <LinearProgress />;

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch" mb={2}>
        <TextField
          label="Search columns"
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 3 }}
        />
        <TextField select size="small" label="Type" value={dtypeFilter}
          onChange={(e) => setDtypeFilter(e.target.value)} sx={{ flex: 1, minWidth: 140 }}>
          {['All', 'Numeric', 'Text', 'Date', 'High Risk'].map((t) => (
            <MenuItem key={t} value={t}>{t}</MenuItem>
          ))}
        </TextField>
        <TextField select size="small" label="Sort" value={sortBy}
          onChange={(e) => setSortBy(e.target.value)} sx={{ flex: 1, minWidth: 140 }}>
          {['Name', 'Null %', 'Uniqueness', 'Risk'].map((t) => (
            <MenuItem key={t} value={t}>{t}</MenuItem>
          ))}
        </TextField>
      </Stack>

      <Typography variant="body2" color="text.secondary" mb={1}>
        Showing {filtered.length} of {cols.length} columns
      </Typography>

      <Grid container spacing={2}>
        {filtered.map((c) => {
          const quality = (100 - c.null_percentage).toFixed(0);
          return (
            <Grid item xs={12} md={6} key={c.column}>
              <Accordion disableGutters elevation={0}
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, '&:before': { display: 'none' } }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography sx={{ fontWeight: 600 }}>
                    {c.column} | {c.dtype} | Quality: {quality}%
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Grid container spacing={1.5}>
                    <Grid item xs={6} md={3}>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>Volume</Typography>
                      <Typography variant="body2">Rows: {c.total_rows.toLocaleString()}</Typography>
                      <Typography variant="body2">Non-null: {c.non_null_count.toLocaleString()}</Typography>
                      <Typography variant="body2">Null: {c.null_count.toLocaleString()} ({c.null_percentage.toFixed(1)}%)</Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>Uniqueness</Typography>
                      <Typography variant="body2">Unique: {c.unique_count.toLocaleString()}</Typography>
                      <Typography variant="body2">Duplicates: {c.duplicate_count.toLocaleString()}</Typography>
                      <Typography variant="body2">Unique %: {c.unique_percentage.toFixed(1)}%</Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>Length</Typography>
                      <Typography variant="body2">Min: {c.min_length || 'N/A'}</Typography>
                      <Typography variant="body2">Max: {c.max_length || 'N/A'}</Typography>
                      <Typography variant="body2">Avg: {c.avg_length.toFixed(1)}</Typography>
                    </Grid>
                    <Grid item xs={6} md={3}>
                      <Typography variant="caption" sx={{ fontWeight: 700 }}>Risk</Typography>
                      <Typography variant="body2">Level: {RISK_DOT[c.risk_level] || ''} {c.risk_level}</Typography>
                      <Typography variant="body2">Score: {c.risk_score}/100</Typography>
                    </Grid>

                    {c.duplicate_count > 0 && c.duplicate_count_values && (
                      <Grid item xs={12}>
                        <Typography variant="caption" sx={{ fontWeight: 700 }}>Duplicate Count Values</Typography>
                        <Typography variant="body2" color="text.secondary"
                                    sx={{ fontFamily: 'monospace', fontSize: '0.78rem', wordBreak: 'break-word' }}>
                          {c.duplicate_count_values}
                        </Typography>
                      </Grid>
                    )}
                    {c.duplicate_groups?.length > 0 && (
                      <Grid item xs={12}>
                        <Typography variant="caption" sx={{ fontWeight: 700 }}>
                          Duplicates ({c.duplicate_groups.length} groups)
                        </Typography>
                        {c.duplicate_groups.slice(0, 5).map((g, i) => (
                          <Typography key={i} variant="body2">
                            • Value '{(g.value || '').slice(0, 30)}' appears {g.count} times ({g.percentage}%)
                          </Typography>
                        ))}
                      </Grid>
                    )}
                  </Grid>
                </AccordionDetails>
              </Accordion>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}
