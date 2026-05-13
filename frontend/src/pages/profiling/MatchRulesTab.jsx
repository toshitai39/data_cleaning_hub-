import { useEffect, useState } from 'react';
import {
  Box, Typography, Alert, LinearProgress, Accordion, AccordionSummary,
  AccordionDetails, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import api from '../../api.js';

const probColor = (p) => {
  if (['Strongest', 'Very Strong', 'Enterprise'].includes(p)) return { bg: '#10b981', fg: '#fff' };
  if (['Strong', 'Good'].includes(p)) return { bg: '#3b82f6', fg: '#fff' };
  return { bg: '#f59e0b', fg: '#fff' };
};

export default function MatchRulesTab() {
  const [rules, setRules] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    api.post('/profile/match-rules')
      .then((r) => setRules(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || 'Failed'));
  }, []);

  if (err) return <Alert severity="error">{err}</Alert>;
  if (!rules) return <LinearProgress />;
  if (rules.length === 0) return <Alert severity="warning">No match rules could be generated</Alert>;

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Suggested Match Rules</Typography>
      <TableContainer component={Paper} sx={{ mb: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Rule No</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Rule Type</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Critical Data Elements</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Match Probability</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Rationale</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rules.map((r) => {
              const c = probColor(r['Match Probability']);
              return (
                <TableRow key={r['Rule No']}>
                  <TableCell>{r['Rule No']}</TableCell>
                  <TableCell>{r['Rule Type']}</TableCell>
                  <TableCell>{r['Columns']}</TableCell>
                  <TableCell sx={{ bgcolor: c.bg, color: c.fg, fontWeight: 600 }}>
                    {r['Match Probability']}
                  </TableCell>
                  <TableCell>{r['Rationale']}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" gutterBottom>Rule Details</Typography>
      {rules.map((r) => (
        <Accordion key={r['Rule No']} disableGutters elevation={0}
                   sx={{ border: '1px solid', borderColor: 'divider', '&:before': { display: 'none' }, mb: 1 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{r['Rule No']}: {r['Rule Type']} Match on {r['Columns']}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="body2"><b>Probability:</b> {r['Match Probability']}</Typography>
            <Typography variant="body2"><b>Confidence Score:</b> {r['Confidence']}</Typography>
            <Typography variant="body2"><b>Rationale:</b> {r['Rationale']}</Typography>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}
