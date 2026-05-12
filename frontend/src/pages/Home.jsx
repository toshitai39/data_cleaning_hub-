import { useMemo, useState } from 'react';
import {
  Box, Grid, Typography, Button, Chip, Stack, IconButton, Menu, MenuItem,
  Tooltip, Alert,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
import VerifiedOutlinedIcon from '@mui/icons-material/VerifiedOutlined';
import CloudDoneOutlinedIcon from '@mui/icons-material/CloudDoneOutlined';
import HourglassEmptyOutlinedIcon from '@mui/icons-material/HourglassEmptyOutlined';
import api from '../api.js';
import StatCard from '../components/StatCard.jsx';
import ContentCard from '../components/ContentCard.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useProject } from '../context/ProjectContext.jsx';

const STATUS_LABEL = {
  empty: { label: 'Empty', color: '#8A8A8A', bg: '#F1ECF6' },
  data_loaded: { label: 'Data loaded', color: '#2A6FDB', bg: '#E6F0FC' },
  profiled: { label: 'Profiled', color: '#6A28A8', bg: '#F4ECF9' },
  rules_generated: { label: 'Rules ready', color: '#C88A1A', bg: '#FCF3E2' },
  cleansed: { label: 'Cleansed', color: '#2F8F57', bg: '#E8F4ED' },
  exported: { label: 'Exported', color: '#2F8F57', bg: '#E8F4ED' },
  archived: { label: 'Archived', color: '#8A8A8A', bg: '#F1ECF6' },
};

function timeAgo(iso) {
  if (!iso) return '—';
  const then = new Date(iso);
  const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} d ago`;
  return then.toLocaleDateString();
}

function ProjectTile({ project, onOpen, onDelete }) {
  const [menuEl, setMenuEl] = useState(null);
  const s = STATUS_LABEL[project.status] || STATUS_LABEL.empty;
  const rows = project?.dataset?.rows;
  const cols = project?.dataset?.columns;

  return (
    <Box
      sx={{
        position: 'relative',
        bgcolor: '#FFFFFF',
        border: '1px solid #E7E6E6',
        borderRadius: 1.5,
        p: 2.5,
        cursor: 'pointer',
        transition: 'border-color 120ms, box-shadow 120ms, transform 120ms',
        '&:hover': {
          borderColor: '#6A28A8',
          boxShadow: '0 4px 14px rgba(73,32,121,0.10)',
          transform: 'translateY(-2px)',
        },
      }}
      onClick={() => onOpen(project)}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1.5 }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Chip
              size="small"
              label={project.system?.label || project.system_id}
              sx={{ height: 20, fontSize: '0.7rem', bgcolor: '#F4ECF9', color: '#6A28A8' }}
            />
            <Chip
              size="small"
              label={project.stream?.label || project.stream_id}
              variant="outlined"
              sx={{ height: 20, fontSize: '0.7rem' }}
            />
          </Stack>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 16,
              fontWeight: 700,
              color: '#1A1A1A',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={project.name}
          >
            {project.name}
          </Typography>
        </Box>
        <Tooltip title="More">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); setMenuEl(e.currentTarget); }}
          >
            <MoreVertIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Menu
          anchorEl={menuEl}
          open={Boolean(menuEl)}
          onClose={() => setMenuEl(null)}
          onClick={(e) => e.stopPropagation()}
        >
          <MenuItem onClick={() => { setMenuEl(null); onOpen(project); }}>Open</MenuItem>
          <MenuItem
            sx={{ color: 'error.main' }}
            onClick={() => { setMenuEl(null); onDelete(project); }}
          >
            Delete
          </MenuItem>
        </Menu>
      </Stack>

      <Stack direction="row" spacing={2} sx={{ mb: 1.75 }}>
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A', textTransform: 'uppercase' }}>
            Rows
          </Typography>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 20,
              fontWeight: 700,
              color: '#1A1A1A',
              lineHeight: 1.1,
            }}
          >
            {rows != null ? rows.toLocaleString() : '—'}
          </Typography>
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A', textTransform: 'uppercase' }}>
            Columns
          </Typography>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 20,
              fontWeight: 700,
              color: '#1A1A1A',
              lineHeight: 1.1,
            }}
          >
            {cols != null ? cols : '—'}
          </Typography>
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.1em', color: '#8A8A8A', textTransform: 'uppercase' }}>
            Quality
          </Typography>
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 20,
              fontWeight: 700,
              color: project.quality_score != null ? '#2F8F57' : '#8A8A8A',
              lineHeight: 1.1,
            }}
          >
            {project.quality_score != null ? `${Math.round(project.quality_score)}%` : '—'}
          </Typography>
        </Box>
      </Stack>

      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Chip
          size="small"
          label={s.label}
          sx={{ height: 22, fontSize: '0.7rem', fontWeight: 700, bgcolor: s.bg, color: s.color }}
        />
        <Typography sx={{ fontSize: 11, color: '#8A8A8A' }}>
          Updated {timeAgo(project.updated_at)}
        </Typography>
      </Stack>
    </Box>
  );
}

export default function Home({ onNavigate }) {
  const { user } = useAuth();
  const { projects, setActive, refresh, loading } = useProject();
  const [error, setError] = useState('');

  const stats = useMemo(() => {
    const total = projects.length;
    const inProgress = projects.filter((p) => !['exported', 'archived'].includes(p.status)).length;
    const exported = projects.filter((p) => p.status === 'exported').length;
    const qualities = projects.map((p) => p.quality_score).filter((q) => q != null);
    const avg = qualities.length ? Math.round(qualities.reduce((a, b) => a + b, 0) / qualities.length) : null;
    return { total, inProgress, exported, avg };
  }, [projects]);

  const handleOpen = async (project) => {
    await setActive(project);
    if (onNavigate) onNavigate('load');
  };

  const handleDelete = async (project) => {
    if (!window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/projects/${project.id}`);
      await refresh();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not delete project');
    }
  };

  const firstName = (user?.name || user?.username || '').split(' ')[0] || 'there';

  return (
    <Box>
      {/* Welcome strip */}
      <Box sx={{ mb: 3 }}>
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: { xs: 28, md: 34 },
            fontWeight: 800,
            color: '#1A1A1A',
            letterSpacing: '-0.02em',
            mb: 0.5,
          }}
        >
          Welcome back, {firstName}.
        </Typography>
        <Typography sx={{ fontSize: 15, color: '#555555' }}>
          Pick up where you left off or kick off a fresh analysis.
        </Typography>
      </Box>

      {/* Stat strip */}
      <Grid container spacing={1.5} sx={{ mb: 3 }}>
        <Grid item xs={6} md={3}>
          <StatCard accent label="Total projects" value={stats.total} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="In progress"
            value={stats.inProgress}
            delta={stats.inProgress > 0 ? 'awaiting your action' : 'all caught up'}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Avg quality"
            value={stats.avg != null ? `${stats.avg}%` : '—'}
            delta={stats.avg != null ? 'across active projects' : 'run a profile to see this'}
            deltaTone={stats.avg != null && stats.avg >= 80 ? 'up' : undefined}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Exported" value={stats.exported} delta="ready for delivery" />
        </Grid>
      </Grid>

      {/* Action row */}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        spacing={1.5}
        sx={{ mb: 2 }}
      >
        <Typography
          sx={{
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 22,
            fontWeight: 700,
            color: '#1A1A1A',
          }}
        >
          My projects
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => onNavigate && onNavigate('new')}
          sx={{ py: 1.25, px: 2.5, fontWeight: 700 }}
        >
          New analysis
        </Button>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {!loading && projects.length === 0 ? (
        <ContentCard sx={{ textAlign: 'center', py: 6 }}>
          <CloudDoneOutlinedIcon sx={{ fontSize: 56, color: '#DDD6E5', mb: 1.5 }} />
          <Typography
            sx={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              fontWeight: 700,
              color: '#1A1A1A',
              mb: 0.5,
            }}
          >
            No projects yet
          </Typography>
          <Typography sx={{ fontSize: 14, color: '#8A8A8A', mb: 2.5 }}>
            Start by creating a new analysis — pick a source system and master-data stream.
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => onNavigate && onNavigate('new')}
            sx={{ py: 1.25, px: 2.5, fontWeight: 700 }}
          >
            Create new analysis
          </Button>
        </ContentCard>
      ) : (
        <Grid container spacing={1.75}>
          {projects.map((p) => (
            <Grid item xs={12} md={6} lg={4} key={p.id}>
              <ProjectTile project={p} onOpen={handleOpen} onDelete={handleDelete} />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
